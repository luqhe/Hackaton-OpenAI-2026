from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AlertSeverity(StrEnum):
    SEV0 = "SEV0"
    SEV1 = "SEV1"
    SEV2 = "SEV2"
    SEV3 = "SEV3"


class AlertRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^PILOT-ALERT-[A-Z0-9-]+$")
    metric: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    operator: Literal["GT", "GTE", "LT", "LTE"]
    threshold: float
    severity: AlertSeverity
    consecutive_windows: int = Field(ge=1, le=12)
    action: str = Field(min_length=3, max_length=160)


class TriggeredAlert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    metric: str
    severity: AlertSeverity
    observed_value: float
    threshold: float
    action: str


def load_alert_rules(path: Path) -> list[AlertRule]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported pilot alert schema")
    return [AlertRule.model_validate(rule) for rule in payload.get("rules", [])]


def _matches(rule: AlertRule, value: float) -> bool:
    return {
        "GT": value > rule.threshold,
        "GTE": value >= rule.threshold,
        "LT": value < rule.threshold,
        "LTE": value <= rule.threshold,
    }[rule.operator]


def evaluate_alerts(rules: list[AlertRule], metric_windows: list[dict[str, float]]) -> list[TriggeredAlert]:
    """Evaluate aggregate technical metrics; observed content must never be passed here."""
    triggered: list[TriggeredAlert] = []
    for rule in rules:
        if len(metric_windows) < rule.consecutive_windows:
            continue
        recent = metric_windows[-rule.consecutive_windows :]
        values = [window.get(rule.metric) for window in recent]
        if any(value is None for value in values):
            continue
        numeric_values = [float(value) for value in values if value is not None]
        if not all(_matches(rule, value) for value in numeric_values):
            continue
        triggered.append(
            TriggeredAlert(
                id=rule.id,
                metric=rule.metric,
                severity=rule.severity,
                observed_value=numeric_values[-1],
                threshold=rule.threshold,
                action=rule.action,
            )
        )
    return triggered
