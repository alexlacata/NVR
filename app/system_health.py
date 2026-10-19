"""Lightweight CPU/RAM/temperature sampling for the dashboard's system
health display, reading straight from /proc and /sys (the same files a
heavier dependency like psutil would read on Linux) rather than adding a
new dependency for three numbers. Every reading returns None instead of
raising when it isn't available on this host (e.g. no thermal zone
exposed inside a container without hardware access) - this is a
nice-to-have status display, not something that should ever break the
dashboard or its tests on an unusual host."""
from __future__ import annotations

import glob
import os
from pathlib import Path
from typing import Optional

_THERMAL_ZONE_GLOB = "/sys/class/thermal/thermal_zone*/temp"


def read_cpu_load_percent() -> Optional[float]:
    """1-minute load average expressed as a percentage of available CPU
    capacity (load / core count * 100) so it reads consistently regardless
    of how many cores the host has - unlike the raw load average."""
    try:
        load1, _, _ = os.getloadavg()
    except OSError:  # pragma: no cover - not available on non-Unix hosts
        return None
    cpu_count = os.cpu_count() or 1
    return round(100.0 * load1 / cpu_count, 1)


def read_memory_percent(meminfo_path: str = "/proc/meminfo") -> Optional[float]:
    """Percent of RAM in use, from /proc/meminfo's MemAvailable (which
    already accounts for reclaimable cache/buffers, unlike the more naive
    MemFree)."""
    try:
        values: dict[str, int] = {}
        with open(meminfo_path, "r", encoding="utf-8") as fh:
            for line in fh:
                key, _, rest = line.partition(":")
                parts = rest.strip().split()
                if parts:
                    values[key] = int(parts[0])  # kB
        total = values.get("MemTotal")
        available = values.get("MemAvailable")
        if not total or available is None:
            return None
        return round(100.0 * (total - available) / total, 1)
    except (OSError, ValueError):
        return None


def read_cpu_temperature_celsius(thermal_zone_glob: str = _THERMAL_ZONE_GLOB) -> Optional[float]:
    """First readable thermal zone, in Celsius - covers the Raspberry Pi
    SoC sensor and most generic Linux CPU temperature sensors alike."""
    for path in sorted(glob.glob(thermal_zone_glob)):
        try:
            millidegrees = int(Path(path).read_text().strip())
        except (OSError, ValueError):
            continue
        return round(millidegrees / 1000.0, 1)
    return None


def read_system_health() -> dict:
    return {
        "cpu_load_percent": read_cpu_load_percent(),
        "memory_percent": read_memory_percent(),
        "cpu_temperature_celsius": read_cpu_temperature_celsius(),
    }
