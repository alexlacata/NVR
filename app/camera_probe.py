"""Tests whether a camera source is actually reachable, without creating
(or touching) a camera - used by the add-camera wizard's "Tester la
connexion" step, so a wrong address/credentials/network issue surfaces
immediately with a real error message instead of being discovered later by
reading server logs after the camera was already saved.

Uses ffprobe (not ffmpeg) since this only needs to confirm a video stream
is readable, not actually transcode/record anything.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Optional

from app.ffmpeg_cmd import input_spec
from app.models import SourceType

_PROBE_TIMEOUT_SECONDS = 10


@dataclass
class ProbeResult:
    ok: bool
    resolution: Optional[str] = None
    detail: Optional[str] = None


async def probe_camera_source(ffprobe_binary: str, source_type: SourceType, url: str) -> ProbeResult:
    spec = input_spec(source_type, url)
    cmd = [
        ffprobe_binary, "-v", "error",
        *spec.pre_args, *spec.in_args,
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json",
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_PROBE_TIMEOUT_SECONDS)
    except FileNotFoundError:
        return ProbeResult(ok=False, detail=f"binaire ffprobe introuvable ({cmd[0]})")
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        return ProbeResult(
            ok=False,
            detail="Delai depasse - la camera ne repond pas (verifiez l'adresse, les identifiants et le reseau)",
        )

    if proc.returncode != 0:
        # ffprobe's last stderr line is almost always the actual reason
        # ("Connection timed out", "401 Unauthorized", "No route to
        # host"...) - surfaced as-is rather than re-categorized, since it's
        # already specific and in practice covers far more failure modes
        # than a hand-written mapping would.
        lines = [l for l in stderr.decode("utf-8", "replace").strip().splitlines() if l.strip()]
        return ProbeResult(ok=False, detail=lines[-1] if lines else f"Echec (code {proc.returncode})")

    try:
        data = json.loads(stdout.decode("utf-8", "replace"))
        streams = data.get("streams") or []
        if not streams:
            return ProbeResult(ok=False, detail="Connexion etablie, mais aucune image video trouvee sur ce flux")
        width, height = streams[0].get("width"), streams[0].get("height")
        resolution = f"{width}x{height}" if width and height else None
        return ProbeResult(ok=True, resolution=resolution)
    except json.JSONDecodeError:
        # Connected and ffprobe exited 0, just couldn't parse the summary -
        # still a genuine success, not worth failing the test over.
        return ProbeResult(ok=True)
