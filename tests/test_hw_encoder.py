import pytest

import app.hw_encoder as hw_encoder
from app.hw_encoder import HW_ENCODER_NAME, detect_hw_encoder


@pytest.fixture(autouse=True)
def _clear_cache():
    hw_encoder._cache.clear()
    yield
    hw_encoder._cache.clear()


class _FakeProc:
    def __init__(self, returncode):
        self.returncode = returncode

    async def wait(self):
        return self.returncode


@pytest.mark.asyncio
async def test_mode_software_never_probes(monkeypatch):
    called = False

    async def fake_exec(*args, **kwargs):
        nonlocal called
        called = True
        return _FakeProc(0)

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    result = await detect_hw_encoder("ffmpeg", mode="software")
    assert result is None
    assert called is False


@pytest.mark.asyncio
async def test_mode_forced_hw_never_probes(monkeypatch):
    called = False

    async def fake_exec(*args, **kwargs):
        nonlocal called
        called = True
        return _FakeProc(0)

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    result = await detect_hw_encoder("ffmpeg", mode="h264_v4l2m2m")
    assert result == HW_ENCODER_NAME
    assert called is False


@pytest.mark.asyncio
async def test_auto_mode_uses_hw_encoder_when_probe_succeeds(monkeypatch):
    async def fake_exec(*args, **kwargs):
        return _FakeProc(0)

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    result = await detect_hw_encoder("ffmpeg", mode="auto")
    assert result == HW_ENCODER_NAME


@pytest.mark.asyncio
async def test_auto_mode_falls_back_to_software_when_probe_fails(monkeypatch):
    async def fake_exec(*args, **kwargs):
        return _FakeProc(1)

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    result = await detect_hw_encoder("ffmpeg", mode="auto")
    assert result is None


@pytest.mark.asyncio
async def test_auto_mode_falls_back_when_binary_missing(monkeypatch):
    async def fake_exec(*args, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    result = await detect_hw_encoder("ffmpeg-introuvable", mode="auto")
    assert result is None


@pytest.mark.asyncio
async def test_unknown_mode_falls_back_to_software(monkeypatch):
    called = False

    async def fake_exec(*args, **kwargs):
        nonlocal called
        called = True
        return _FakeProc(0)

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    result = await detect_hw_encoder("ffmpeg", mode="n-importe-quoi")
    assert result is None
    assert called is False


@pytest.mark.asyncio
async def test_result_is_cached_per_binary_and_mode(monkeypatch):
    calls = 0

    async def fake_exec(*args, **kwargs):
        nonlocal calls
        calls += 1
        return _FakeProc(0)

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    await detect_hw_encoder("ffmpeg", mode="auto")
    await detect_hw_encoder("ffmpeg", mode="auto")
    assert calls == 1
