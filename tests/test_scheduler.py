import pytest

from agent.scheduler import AdaptiveObservationSchedule, SuspensionDetector


def test_inactivity_backs_off_until_configured_maximum() -> None:
    schedule = AdaptiveObservationSchedule(
        minimum_seconds=10,
        maximum_seconds=40,
        backoff_factor=2,
    )

    assert schedule.report_observation(changed=False) == 20
    assert schedule.report_observation(changed=False) == 40
    assert schedule.report_observation(changed=False) == 40


def test_activity_and_wake_restore_minimum_interval() -> None:
    schedule = AdaptiveObservationSchedule(minimum_seconds=5, maximum_seconds=30)
    schedule.report_observation(changed=False)

    assert schedule.report_observation(changed=True) == 5
    schedule.report_observation(changed=False)
    assert schedule.report_wake() == 5


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"minimum_seconds": 0}, "minimum_seconds"),
        ({"minimum_seconds": 20, "maximum_seconds": 10}, "maximum_seconds"),
        ({"backoff_factor": 1}, "backoff_factor"),
    ],
)
def test_invalid_schedule_configuration_is_rejected(values, message) -> None:
    with pytest.raises(ValueError, match=message):
        AdaptiveObservationSchedule(**values)


def test_suspension_detector_distinguishes_normal_interval_from_wake() -> None:
    now = [100.0]
    detector = SuspensionDetector(grace_seconds=5, clock=lambda: now[0])

    now[0] += 10
    assert detector.check(expected_interval=10) is False
    now[0] += 120
    assert detector.check(expected_interval=10) is True
