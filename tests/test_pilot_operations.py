from pathlib import Path

from guardian_core.operations import AlertSeverity, evaluate_alerts, load_alert_rules

ROOT = Path(__file__).resolve().parents[1]


def rules():
    return load_alert_rules(ROOT / "config/pilot/alerts.v1.json")


def test_privacy_signal_pages_immediately_without_observed_content() -> None:
    triggered = evaluate_alerts(rules(), [{"cross_family_access_events": 1}])

    assert [alert.id for alert in triggered] == ["PILOT-ALERT-PRIVACY-CROSS-FAMILY"]
    assert triggered[0].severity == AlertSeverity.SEV0
    assert "SECURITY_PRIVACY" in triggered[0].action


def test_command_latency_requires_two_consecutive_bad_windows() -> None:
    one_bad_window = evaluate_alerts(rules(), [{"command_ack_latency_p95_ms": 5100}])
    recovered_window = evaluate_alerts(
        rules(),
        [
            {"command_ack_latency_p95_ms": 5100},
            {"command_ack_latency_p95_ms": 4900},
        ],
    )
    two_bad_windows = evaluate_alerts(
        rules(),
        [
            {"command_ack_latency_p95_ms": 5100},
            {"command_ack_latency_p95_ms": 5200},
        ],
    )

    assert one_bad_window == []
    assert recovered_window == []
    assert [alert.id for alert in two_bad_windows] == ["PILOT-ALERT-COMMAND-ACK-P95"]


def test_missing_metric_does_not_claim_a_trigger_or_healthy_value() -> None:
    assert evaluate_alerts(rules(), [{}, {}]) == []
