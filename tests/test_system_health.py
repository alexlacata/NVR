from unittest import mock

from app.system_health import (
    read_cpu_load_percent,
    read_cpu_temperature_celsius,
    read_memory_percent,
    read_system_health,
)


def test_cpu_load_percent_scales_by_core_count():
    with mock.patch("app.system_health.os.getloadavg", return_value=(2.0, 1.5, 1.0)), \
         mock.patch("app.system_health.os.cpu_count", return_value=4):
        assert read_cpu_load_percent() == 50.0


def test_cpu_load_percent_none_when_unavailable():
    with mock.patch("app.system_health.os.getloadavg", side_effect=OSError):
        assert read_cpu_load_percent() is None


def test_memory_percent_from_meminfo(tmp_path):
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(
        "MemTotal:        8000000 kB\n"
        "MemFree:         1000000 kB\n"
        "MemAvailable:    2000000 kB\n"
        "Buffers:          500000 kB\n"
    )
    assert read_memory_percent(str(meminfo)) == 75.0


def test_memory_percent_none_when_fields_missing(tmp_path):
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("SomeOtherField: 123 kB\n")
    assert read_memory_percent(str(meminfo)) is None


def test_memory_percent_none_when_file_missing(tmp_path):
    assert read_memory_percent(str(tmp_path / "does-not-exist")) is None


def test_cpu_temperature_reads_first_thermal_zone(tmp_path):
    zone_dir = tmp_path / "thermal_zone0"
    zone_dir.mkdir()
    (zone_dir / "temp").write_text("45678\n")
    assert read_cpu_temperature_celsius(str(tmp_path / "thermal_zone*/temp")) == 45.7


def test_cpu_temperature_none_when_no_zone(tmp_path):
    assert read_cpu_temperature_celsius(str(tmp_path / "thermal_zone*/temp")) is None


def test_cpu_temperature_skips_unreadable_zone_and_uses_next(tmp_path):
    bad = tmp_path / "thermal_zone0"
    bad.mkdir()
    (bad / "temp").write_text("not-a-number\n")
    good = tmp_path / "thermal_zone1"
    good.mkdir()
    (good / "temp").write_text("50000\n")
    assert read_cpu_temperature_celsius(str(tmp_path / "thermal_zone*/temp")) == 50.0


def test_read_system_health_returns_all_three_keys():
    health = read_system_health()
    assert set(health.keys()) == {"cpu_load_percent", "memory_percent", "cpu_temperature_celsius"}
