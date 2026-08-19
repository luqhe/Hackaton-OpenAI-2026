import json
from types import SimpleNamespace

import agent.diagnostics as diagnostics_module
import agent.main as agent_main
from agent.diagnostics import PerformanceMonitor, directory_size


class FakeProcess:
    def __init__(self):
        self.cpu_calls = 0

    def cpu_percent(self, interval=None):
        self.cpu_calls += 1
        return 2.5

    def memory_info(self):
        return SimpleNamespace(rss=150 * 1024 * 1024)


def test_performance_monitor_measures_all_agent_budgets(monkeypatch, tmp_path) -> None:
    (tmp_path / "capture.bin").write_bytes(b"x" * 128)
    process = FakeProcess()
    monkeypatch.setattr(
        diagnostics_module.psutil,
        "net_io_counters",
        lambda: SimpleNamespace(bytes_sent=1000, bytes_recv=2000),
    )
    monkeypatch.setattr(
        diagnostics_module.psutil,
        "sensors_battery",
        lambda: SimpleNamespace(percent=87.0, power_plugged=False),
    )

    snapshot = PerformanceMonitor(tmp_path, process=process).sample()

    assert snapshot.cpu_percent == 2.5
    assert snapshot.resident_memory_bytes == 150 * 1024 * 1024
    assert snapshot.data_directory_bytes == 128
    assert snapshot.network_bytes_sent == 1000
    assert snapshot.network_bytes_received == 2000
    assert snapshot.battery_percent == 87.0
    assert snapshot.power_plugged is False
    assert process.cpu_calls == 2


def test_directory_size_tolerates_missing_directory(tmp_path) -> None:
    assert directory_size(tmp_path / "missing") == 0


def test_diagnostics_command_prints_machine_readable_snapshots(monkeypatch, tmp_path, capsys) -> None:
    snapshots = []

    class FakeMonitor:
        def __init__(self, data_directory):
            assert data_directory == tmp_path

        def sample(self):
            cpu_percent = len(snapshots)
            snapshot = SimpleNamespace(as_json_dict=lambda: {"cpu_percent": cpu_percent})
            snapshots.append(snapshot)
            return snapshot

    monkeypatch.setattr(agent_main, "PerformanceMonitor", FakeMonitor)
    args = agent_main.build_parser().parse_args(
        ["diagnostics", "--data-directory", str(tmp_path), "--samples", "2", "--interval", "0"]
    )

    assert agent_main.run_diagnostics(args) == 0
    assert [json.loads(line) for line in capsys.readouterr().out.splitlines()] == [
        {"cpu_percent": 0},
        {"cpu_percent": 1},
    ]
