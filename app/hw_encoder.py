"""Detects whether this machine's ffmpeg can actually use the Raspberry Pi's
hardware H.264 encoder (h264_v4l2m2m, exposed by the bcm2835-codec driver on
Pi 4 and earlier) instead of the software libx264 encoder - the single
biggest CPU cost on a Pi when a stream needs re-encoding (a live-view
bitrate cap/resize, or a USB/HTTP/test source that can never be a plain
stream copy).

A compile-time feature check (ffmpeg -encoders) isn't enough: the encoder
can be compiled in but have no matching hardware - the Raspberry Pi 5
(BCM2712) dropped the video *encode* block entirely (it keeps hardware
*decode*), so a Pi 5 running the exact same ffmpeg build as a Pi 4 would
report the encoder as available and then fail every real encode. The only
reliable test is to actually run one.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger("nvr.hw_encoder")

HW_ENCODER_NAME = "h264_v4l2m2m"

# A handful of frames at a tiny resolution: enough for the driver to prove
# it can produce real output, cheap enough to run at every startup without
# meaningfully delaying it.
_PROBE_CMD_TAIL = [
    "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=5",
    "-frames:v", "5",
    "-c:v", HW_ENCODER_NAME, "-pix_fmt", "yuv420p",
    "-f", "null", "-",
]
_PROBE_TIMEOUT_SECONDS = 10

# The host's hardware/ffmpeg build doesn't change while this process is
# running, so a given (binary, mode) pair only ever needs probing once -
# cached so creating the app more than once per process (every test in the
# suite does exactly that) doesn't re-run a subprocess each time.
_cache: dict[tuple[str, str], Optional[str]] = {}


async def detect_hw_encoder(ffmpeg_binary: str, mode: str = "auto") -> Optional[str]:
    """Returns HW_ENCODER_NAME if it should be used, or None to fall back to
    software (libx264). `mode` is the NVR_HW_ENCODER setting:
    - "auto" (default): probe, use the hardware encoder only if the probe
      actually succeeds.
    - "h264_v4l2m2m": skip the probe and force it on (e.g. a setup where
      the probe itself is unreliable but the encoder is known to work).
    - "software" (or anything else unrecognized): always use libx264.
    """
    key = (ffmpeg_binary, mode)
    if key in _cache:
        return _cache[key]
    result = await _detect_uncached(ffmpeg_binary, mode)
    _cache[key] = result
    return result


async def _detect_uncached(ffmpeg_binary: str, mode: str) -> Optional[str]:
    if mode == "h264_v4l2m2m":
        return HW_ENCODER_NAME
    if mode != "auto":
        if mode != "software":
            logger.warning("NVR_HW_ENCODER=%r inconnu, bascule sur l'encodage logiciel (libx264)", mode)
        return None

    cmd = [ffmpeg_binary, "-hide_banner", "-loglevel", "error", *_PROBE_CMD_TAIL]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        returncode = await asyncio.wait_for(proc.wait(), timeout=_PROBE_TIMEOUT_SECONDS)
    except (FileNotFoundError, OSError):
        returncode = 1
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        returncode = 1

    if returncode == 0:
        logger.info("Encodeur materiel %s disponible et fonctionnel - utilise pour le re-encodage.", HW_ENCODER_NAME)
        return HW_ENCODER_NAME
    logger.info(
        "Pas d'encodeur materiel %s fonctionnel (normal sur Raspberry Pi 5, sur PC/serveur x86, "
        "ou sans module video dedie) - utilise l'encodage logiciel (libx264).",
        HW_ENCODER_NAME,
    )
    return None
