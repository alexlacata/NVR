"""Shared helpers for the `%Y-%m-%d_%H-%M-%S.mp4` recording segment filename
convention (written by ffmpeg's segment muxer, see app/ffmpeg_cmd.py)."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

RECORDING_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.mp4$")


def parse_recording_start(filename: str) -> Optional[datetime]:
    """Parse a segment's start time from its filename, or None if it
    doesn't match the expected pattern. Naive datetime, server-local time
    (matches ffmpeg's `-strftime 1`, which uses the local system clock)."""
    if not RECORDING_NAME_RE.match(filename):
        return None
    try:
        return datetime.strptime(filename[:-4], "%Y-%m-%d_%H-%M-%S")
    except ValueError:
        return None


def list_recording_segments(camera_dir: Path) -> list[tuple[datetime, Path]]:
    """All valid recording segments in a camera's directory, sorted by
    start time ascending."""
    out = []
    if not camera_dir.exists():
        return out
    for f in camera_dir.glob("*.mp4"):
        start = parse_recording_start(f.name)
        if start is not None:
            out.append((start, f))
    out.sort(key=lambda pair: pair[0])
    return out
