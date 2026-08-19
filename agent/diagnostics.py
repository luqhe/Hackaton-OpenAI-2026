from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil


@dataclass(frozen=True, slots=True)
class PerformanceSnapshot:
    observed_at: str
    cpu_percent: float
    resident_memory_bytes: int
    data_directory_bytes: int
    network_bytes_sent: int
    network_bytes_received: int
    battery_percent: float | None
    power_plugged: bool | None

    def as_json_dict(self) -> dict[str, Any]:
        return asdict(self)


def directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


class PerformanceMonitor:
    def __init__(self, data_directory: Path, *, process: Any | None = None):
        self.data_directory = data_directory
        self.process = process or psutil.Process()
        self.process.cpu_percent(interval=None)

    def sample(self) -> PerformanceSnapshot:
        network = psutil.net_io_counters()
        battery = psutil.sensors_battery()
        return PerformanceSnapshot(
            observed_at=datetime.now(UTC).isoformat(),
            cpu_percent=self.process.cpu_percent(interval=None),
            resident_memory_bytes=self.process.memory_info().rss,
            data_directory_bytes=directory_size(self.data_directory),
            network_bytes_sent=network.bytes_sent,
            network_bytes_received=network.bytes_recv,
            battery_percent=battery.percent if battery is not None else None,
            power_plugged=battery.power_plugged if battery is not None else None,
        )
