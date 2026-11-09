import json

import pytest

from app.camera_probe import probe_camera_source
from app.models import SourceType


class _FakeProc:
    def __init__(self, returncode, stdout=b"", stderr=b""):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self):
        return self._stdout, self._stderr

    def kill(self):
        pass


@pytest.mark.asyncio
async def test_success_with_resolution(monkeypatch):
    payload = json.dumps({"streams": [{"width": 1920, "height": 1080}]}).encode()

    async def fake_exec(*args, **kwargs):
        return _FakeProc(0, stdout=payload)

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    result = await probe_camera_source("ffprobe", SourceType.rtsp, "rtsp://x/1")
    assert result.ok is True
    assert result.resolution == "1920x1080"


@pytest.mark.asyncio
async def test_success_without_parseable_streams(monkeypatch):
    async def fake_exec(*args, **kwargs):
        return _FakeProc(0, stdout=b"not json")

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    result = await probe_camera_source("ffprobe", SourceType.rtsp, "rtsp://x/1")
    assert result.ok is True
    assert result.resolution is None


@pytest.mark.asyncio
async def test_no_video_stream_found(monkeypatch):
    payload = json.dumps({"streams": []}).encode()

    async def fake_exec(*args, **kwargs):
        return _FakeProc(0, stdout=payload)

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    result = await probe_camera_source("ffprobe", SourceType.rtsp, "rtsp://x/1")
    assert result.ok is False
    assert "aucune image" in result.detail.lower()


@pytest.mark.asyncio
async def test_ffprobe_failure_surfaces_last_stderr_line(monkeypatch):
    stderr = b"some warning\nConnection timed out\n"

    async def fake_exec(*args, **kwargs):
        return _FakeProc(1, stderr=stderr)

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    result = await probe_camera_source("ffprobe", SourceType.rtsp, "rtsp://x/1")
    assert result.ok is False
    assert result.detail == "Connection timed out"


@pytest.mark.asyncio
async def test_binary_missing(monkeypatch):
    async def fake_exec(*args, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    result = await probe_camera_source("ffprobe-introuvable", SourceType.rtsp, "rtsp://x/1")
    assert result.ok is False
    assert "introuvable" in result.detail


@pytest.mark.asyncio
async def test_timeout(monkeypatch):
    import asyncio

    class _HangingProc(_FakeProc):
        async def communicate(self):
            raise asyncio.TimeoutError()

    async def fake_exec(*args, **kwargs):
        return _HangingProc(None)

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    result = await probe_camera_source("ffprobe", SourceType.rtsp, "rtsp://x/1")
    assert result.ok is False
    assert "delai" in result.detail.lower() or "délai" in result.detail.lower()
