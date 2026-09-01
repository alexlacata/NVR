"""End-to-end smoke test: runs real ffmpeg against a synthetic test source and
checks that both the recording segments and the HLS live playlist actually
get produced on disk. Requires the `ffmpeg` binary; skipped if absent.
"""
import asyncio
import shutil
import time

import pytest

from app.config import Settings
from app.ffmpeg_manager import StreamManager
from app.models import Camera, SourceType

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


@pytest.mark.asyncio
async def test_record_and_live_pipeline_produce_files(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        segment_seconds=5,
        hls_segment_seconds=2,
        hls_list_size=4,
    )
    settings.ensure_dirs()
    manager = StreamManager(settings)
    camera = Camera(
        id="demo",
        name="Demo",
        source_type=SourceType.test,
        url="test:pattern",
        enabled=True,
        record=True,
    )
    await manager.reconcile([camera])
    try:
        deadline = time.time() + 25
        hls_playlist = settings.hls_dir / "demo" / "stream.m3u8"
        rec_dir = settings.recordings_dir / "demo"
        while time.time() < deadline:
            if hls_playlist.exists() and any(rec_dir.glob("*.mp4")):
                break
            await asyncio.sleep(1)
        status = manager.status("demo")
        assert hls_playlist.exists(), f"HLS playlist missing, status={status}"
        assert hls_playlist.read_text().strip(), "HLS playlist is empty"
        segments = list((settings.hls_dir / "demo").glob("*.ts"))
        assert segments, "no HLS .ts segments produced"
        recordings = list(rec_dir.glob("*.mp4"))
        assert recordings, f"no recording produced, status={status}"
        assert status.state == "running", status
    finally:
        await manager.stop_all()
