"""Supervises the ffmpeg record/live processes for every configured camera."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.config import Settings
from app.ffmpeg_cmd import build_live_cmd, build_record_cmd
from app.models import Camera, CameraStatus

logger = logging.getLogger("nvr.ffmpeg")

MAX_BACKOFF_SECONDS = 30
STALL_CHECK_INTERVAL = 5
STARTUP_GRACE_SECONDS = 20


@dataclass
class _LegState:
    state: str = "stopped"  # stopped|starting|running|error|disabled
    last_error: Optional[str] = None
    restart_count: int = 0
    started_at: Optional[float] = None


class _Leg:
    """One supervised ffmpeg process (either the "record" or "live" leg of a camera)."""

    def __init__(self, camera_id: str, purpose: str, cmd_factory, stall_path_factory, stall_timeout: int):
        self.camera_id = camera_id
        self.purpose = purpose
        self._cmd_factory = cmd_factory
        self._stall_path_factory = stall_path_factory
        self._stall_timeout = stall_timeout
        self.info = _LegState()
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._task: Optional[asyncio.Task] = None
        self._stopping = False

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stopping = False
        self.info.state = "starting"
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopping = True
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.terminate()
            except ProcessLookupError:
                pass
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except asyncio.TimeoutError:
                if self._proc and self._proc.returncode is None:
                    self._proc.kill()
                try:
                    await asyncio.wait_for(self._task, timeout=5)
                except asyncio.TimeoutError:
                    logger.error("%s/%s: force-kill task did not settle", self.camera_id, self.purpose)
        self.info.state = "stopped"

    async def _run(self) -> None:
        backoff = 2.0
        while not self._stopping:
            self.info.state = "starting"
            cmd = self._cmd_factory()
            logger.info("%s/%s: starting: %s", self.camera_id, self.purpose, " ".join(cmd))
            try:
                self._proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
            except FileNotFoundError:
                self.info.state = "error"
                self.info.last_error = f"binaire ffmpeg introuvable ({cmd[0]})"
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
                continue
            except Exception as exc:  # pragma: no cover - defensive
                self.info.state = "error"
                self.info.last_error = str(exc)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
                continue

            self.info.state = "running"
            self.info.started_at = time.time()
            last_line = ""
            stderr_task = asyncio.create_task(self._drain_stderr())
            watchdog_task = asyncio.create_task(self._watchdog())
            try:
                returncode = await self._proc.wait()
            finally:
                watchdog_task.cancel()
                last_line = await stderr_task

            if self._stopping:
                break

            backoff = 2.0 if (time.time() - (self.info.started_at or 0)) > STARTUP_GRACE_SECONDS else backoff
            self.info.state = "error"
            self.info.last_error = last_line or f"ffmpeg s'est arrete (code {returncode})"
            self.info.restart_count += 1
            logger.warning("%s/%s: exited (%s): %s", self.camera_id, self.purpose, returncode, self.info.last_error)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)

        self.info.state = "stopped"

    async def _drain_stderr(self) -> str:
        last_line = ""
        assert self._proc and self._proc.stderr
        try:
            async for raw in self._proc.stderr:
                line = raw.decode("utf-8", "replace").strip()
                if line:
                    last_line = line
                    logger.debug("%s/%s: %s", self.camera_id, self.purpose, line)
        except Exception:  # pragma: no cover - stream can close abruptly
            pass
        return last_line

    async def _watchdog(self) -> None:
        """Kill the process if it stops producing output (stalled connection)."""
        try:
            await asyncio.sleep(STARTUP_GRACE_SECONDS)
            while True:
                await asyncio.sleep(STALL_CHECK_INTERVAL)
                path = self._stall_path_factory()
                age = _mtime_age(path)
                if age is not None and age > self._stall_timeout:
                    logger.warning(
                        "%s/%s: no output for %.0fs, restarting", self.camera_id, self.purpose, age
                    )
                    if self._proc and self._proc.returncode is None:
                        self._proc.kill()
                    return
        except asyncio.CancelledError:
            return


def _mtime_age(path: Path) -> Optional[float]:
    try:
        return time.time() - path.stat().st_mtime
    except OSError:
        return None


class StreamManager:
    """Owns the record/live ffmpeg legs for every camera, keyed by camera id."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._legs: dict[str, dict[str, _Leg]] = {}
        self._configs: dict[str, Camera] = {}

    async def reconcile(self, cameras: list[Camera]) -> None:
        """Start/stop/restart ffmpeg legs so the running state matches `cameras`."""
        desired = {c.id: c for c in cameras}

        for camera_id in list(self._legs):
            if camera_id not in desired:
                await self._stop_camera(camera_id)

        for camera in cameras:
            prev = self._configs.get(camera.id)
            if prev is not None and prev != camera:
                await self._stop_camera(camera.id)
                prev = None
            if prev is None:
                self._start_camera(camera)
            else:
                self._sync_camera_state(camera)
            self._configs[camera.id] = camera

    def _start_camera(self, camera: Camera) -> None:
        legs: dict[str, _Leg] = {}

        rec_dir = self._settings.recordings_dir / camera.id
        rec_dir.mkdir(parents=True, exist_ok=True)
        record_leg = _Leg(
            camera.id, "record",
            cmd_factory=lambda: build_record_cmd(
                self._settings.ffmpeg_binary, camera, rec_dir, self._settings.segment_seconds
            ),
            stall_path_factory=lambda: rec_dir,
            stall_timeout=max(self._settings.segment_seconds * 2, 60),
        )
        legs["record"] = record_leg

        hls_dir = self._settings.hls_dir / camera.id
        hls_dir.mkdir(parents=True, exist_ok=True)
        live_leg = _Leg(
            camera.id, "live",
            cmd_factory=lambda: build_live_cmd(
                self._settings.ffmpeg_binary, camera, hls_dir,
                self._settings.hls_segment_seconds, self._settings.hls_list_size,
            ),
            stall_path_factory=lambda: hls_dir / "stream.m3u8",
            stall_timeout=max(self._settings.hls_segment_seconds * 8, 30),
        )
        legs["live"] = live_leg

        self._legs[camera.id] = legs
        if camera.enabled:
            live_leg.start()
            if camera.record:
                record_leg.start()

    def _sync_camera_state(self, camera: Camera) -> None:
        legs = self._legs.get(camera.id)
        if not legs:
            return
        if camera.enabled:
            legs["live"].start()
            if camera.record:
                legs["record"].start()
            else:
                asyncio.create_task(legs["record"].stop())
        else:
            asyncio.create_task(legs["live"].stop())
            asyncio.create_task(legs["record"].stop())

    async def _stop_camera(self, camera_id: str) -> None:
        legs = self._legs.pop(camera_id, None)
        self._configs.pop(camera_id, None)
        if not legs:
            return
        await asyncio.gather(*(leg.stop() for leg in legs.values()))

    async def stop_all(self) -> None:
        for camera_id in list(self._legs):
            await self._stop_camera(camera_id)

    def status(self, camera_id: str) -> CameraStatus:
        legs = self._legs.get(camera_id)
        if not legs:
            return CameraStatus(id=camera_id, running=False, state="disabled")
        record_info = legs["record"].info
        live_info = legs["live"].info
        camera = self._configs.get(camera_id)
        if camera and not camera.enabled:
            state = "disabled"
        else:
            state = live_info.state
        running = state == "running"
        last_error = live_info.last_error or record_info.last_error
        started_at = None
        if live_info.started_at:
            started_at = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(live_info.started_at))
        return CameraStatus(
            id=camera_id,
            running=running,
            state=state,
            last_error=last_error,
            restart_count=record_info.restart_count + live_info.restart_count,
            started_at=started_at,
        )

    def all_status(self) -> dict[str, CameraStatus]:
        return {cid: self.status(cid) for cid in self._legs}
