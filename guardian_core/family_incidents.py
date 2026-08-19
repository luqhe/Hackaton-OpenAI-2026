from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol


@dataclass(frozen=True)
class AssessmentExplanation:
    """Classifier output only; it cannot express or execute device control."""

    risk: str
    category: str
    confidence: float
    signals: tuple[str, ...]
    classifier_version: str


@dataclass(frozen=True)
class PolicyExplanation:
    """The separately auditable family-policy decision."""

    action: str
    rule: str
    threshold: float
    policy_version: str


@dataclass(frozen=True)
class EvidenceReference:
    evidence_id: str
    kind: str
    captured_at: datetime
    expires_at: datetime
    locator: str | None


@dataclass(frozen=True)
class EvidenceView:
    evidence_id: str
    kind: str
    captured_at: datetime
    expires_at: datetime
    state: str
    access_url: str | None


@dataclass(frozen=True)
class TimelineEvent:
    event_id: str
    kind: str
    occurred_at: datetime


@dataclass(frozen=True)
class ContestationReceipt:
    contestation_id: str
    status: str
    reason_length: int


@dataclass(frozen=True)
class NotificationPreferences:
    enabled: bool = False
    channel: str = "in_app"


@dataclass
class NotificationEnvelope:
    notification_id: str
    family_id: str
    incident_id: str
    channel: str
    message: str
    attempt_count: int
    next_attempt_at: datetime
    status: str = "pending"


@dataclass(frozen=True)
class InAppNotification:
    notification_id: str
    family_id: str
    incident_id: str
    message: str


@dataclass(frozen=True)
class FamilyDecision:
    decision_id: str
    outcome: str
    decided_at: datetime
    command_expires_at: datetime | None


@dataclass(frozen=True)
class FamilyDecisionView:
    winner_id: str
    outcome: str
    decided_at: datetime


@dataclass
class UnlockCommand:
    command_id: str
    incident_id: str
    device_id: str
    decision_id: str
    requested_at: datetime
    expires_at: datetime
    status: str = "requested"
    delivered_at: datetime | None = None
    completed_at: datetime | None = None
    failure_code: str | None = None


@dataclass(frozen=True)
class UnlockView:
    command_id: str
    status: str
    requested_at: datetime
    expires_at: datetime
    delivered_at: datetime | None
    completed_at: datetime | None
    failure_code: str | None
    execution_confirmed: bool


@dataclass(frozen=True)
class DecisionReceipt:
    winner_id: str
    outcome: str
    command_id: str | None


class NotificationAdapter(Protocol):
    def deliver(self, notification: NotificationEnvelope) -> None: ...


class NotificationOutbox:
    """Queues sanitized notices; provider I/O happens only in ``deliver_pending``."""

    _MESSAGE = "Há uma atualização de segurança para revisar."

    def __init__(self) -> None:
        self._preferences: dict[str, NotificationPreferences] = {}
        self._notifications: dict[str, NotificationEnvelope] = {}
        self._fallbacks: dict[str, InAppNotification] = {}

    def configure(self, family_id: str, preferences: NotificationPreferences) -> None:
        self._preferences[family_id] = preferences

    def unsubscribe(self, family_id: str) -> None:
        self._preferences[family_id] = NotificationPreferences(enabled=False)
        for notification in self._notifications.values():
            if notification.family_id == family_id and notification.status != "delivered":
                notification.status = "cancelled"

    def enqueue_incident(self, family_id: str, incident_id: str, *, queued_at: datetime) -> None:
        preferences = self._preferences.get(family_id, NotificationPreferences())
        if not preferences.enabled:
            return
        notification_id = f"incident:{family_id}:{incident_id}"
        if notification_id in self._notifications:
            return
        self._notifications[notification_id] = NotificationEnvelope(
            notification_id=notification_id,
            family_id=family_id,
            incident_id=incident_id,
            channel=preferences.channel,
            message=self._MESSAGE,
            attempt_count=0,
            next_attempt_at=queued_at,
        )

    def pending(self, *, now: datetime) -> tuple[NotificationEnvelope, ...]:
        return tuple(
            notification
            for notification in self._notifications.values()
            if notification.status == "pending" and notification.next_attempt_at <= now
        )

    def in_app(self, family_id: str) -> tuple[InAppNotification, ...]:
        return tuple(fallback for fallback in self._fallbacks.values() if fallback.family_id == family_id)

    def deliver_pending(self, adapters: dict[str, NotificationAdapter], *, now: datetime) -> None:
        for notification in self.pending(now=now):
            adapter = adapters.get(notification.channel)
            try:
                if adapter is None:
                    raise LookupError(f"No adapter configured for {notification.channel}")
                adapter.deliver(notification)
            except Exception:
                notification.attempt_count += 1
                delay_seconds = min(30 * (2 ** (notification.attempt_count - 1)), 900)
                notification.next_attempt_at = now + timedelta(seconds=delay_seconds)
                self._fallbacks.setdefault(
                    notification.notification_id,
                    InAppNotification(
                        notification_id=notification.notification_id,
                        family_id=notification.family_id,
                        incident_id=notification.incident_id,
                        message=self._MESSAGE,
                    ),
                )
            else:
                notification.status = "delivered"


@dataclass(frozen=True)
class IncidentView:
    incident_id: str
    child_id: str
    device_id: str
    assessment: AssessmentExplanation
    policy: PolicyExplanation
    timeline: tuple[TimelineEvent, ...]
    evidence: tuple[EvidenceView, ...]
    family_decision: FamilyDecisionView | None
    unlock: UnlockView | None
    classifier_controls_device: bool


@dataclass
class _IncidentState:
    incident_id: str
    family_id: str
    child_id: str
    device_id: str
    assessment: AssessmentExplanation
    policy: PolicyExplanation
    evidence: tuple[EvidenceReference, ...]
    timeline: list[TimelineEvent] = field(default_factory=list)
    contestations: dict[str, str] = field(default_factory=dict)
    decisions: dict[str, FamilyDecision] = field(default_factory=dict)
    command_id: str | None = None


class FamilyIncidentService:
    def __init__(self, *, notifications: NotificationOutbox | None = None) -> None:
        self._incidents: dict[str, _IncidentState] = {}
        self._notifications = notifications or NotificationOutbox()
        self._commands: dict[str, UnlockCommand] = {}
        self._device_online: dict[str, bool] = {}

    def open_incident(
        self,
        *,
        incident_id: str,
        family_id: str,
        child_id: str,
        device_id: str,
        detected_at: datetime,
        assessment: AssessmentExplanation,
        policy: PolicyExplanation,
        evidence: tuple[EvidenceReference, ...] = (),
    ) -> None:
        self._incidents[incident_id] = _IncidentState(
            incident_id=incident_id,
            family_id=family_id,
            child_id=child_id,
            device_id=device_id,
            assessment=assessment,
            policy=policy,
            evidence=evidence,
            timeline=[TimelineEvent(f"{incident_id}:detected", "detected", detected_at)],
        )
        self.queue_guardian_notification(incident_id, queued_at=detected_at)

    def queue_guardian_notification(self, incident_id: str, *, queued_at: datetime) -> None:
        state = self._incidents[incident_id]
        self._notifications.enqueue_incident(state.family_id, incident_id, queued_at=queued_at)

    def record_event(self, incident_id: str, kind: str, occurred_at: datetime, *, event_id: str) -> None:
        self._incidents[incident_id].timeline.append(TimelineEvent(event_id, kind, occurred_at))

    def submit_contestation(
        self,
        incident_id: str,
        *,
        reason: str,
        submitted_at: datetime,
        contestation_id: str,
    ) -> ContestationReceipt:
        minimized_reason = reason.strip()
        if len(minimized_reason) > 280:
            raise ValueError("Contestation reason must contain at most 280 characters")
        if not minimized_reason:
            raise ValueError("Contestation reason cannot be empty")
        state = self._incidents[incident_id]
        existing = state.contestations.get(contestation_id)
        if existing is not None:
            if existing != minimized_reason:
                raise ValueError("Contestation id already exists with different content")
            return ContestationReceipt(
                contestation_id=contestation_id,
                status="submitted",
                reason_length=len(existing),
            )
        state.contestations[contestation_id] = minimized_reason
        state.timeline.append(TimelineEvent(contestation_id, "contestation_submitted", submitted_at))
        return ContestationReceipt(
            contestation_id=contestation_id,
            status="submitted",
            reason_length=len(minimized_reason),
        )

    def submit_guardian_decision(
        self,
        incident_id: str,
        *,
        decision_id: str,
        outcome: str,
        decided_at: datetime,
        command_expires_at: datetime | None,
    ) -> DecisionReceipt:
        if outcome not in {"UNLOCK", "KEEP_BLOCKED"}:
            raise ValueError("Unsupported family decision")
        if decided_at.tzinfo is None or decided_at.utcoffset() is None:
            raise ValueError("Family decision timestamp must include a timezone")
        if outcome == "UNLOCK" and command_expires_at is None:
            raise ValueError("Unlock decisions require command expiry")
        if command_expires_at is not None:
            if command_expires_at.tzinfo is None or command_expires_at.utcoffset() is None:
                raise ValueError("Unlock command expiry must include a timezone")
            if command_expires_at <= decided_at:
                raise ValueError("Unlock command expiry must be after the decision")
        state = self._incidents[incident_id]
        current = self._command_for(state)
        if current is not None and current.status in {"delivered", "executed", "failed"}:
            raise ValueError("Family decision is final after command delivery")

        candidate = FamilyDecision(
            decision_id=decision_id,
            outcome=outcome,
            decided_at=decided_at,
            command_expires_at=command_expires_at,
        )
        existing = state.decisions.get(decision_id)
        if existing is not None and existing != candidate:
            raise ValueError("Family decision id already exists with different content")
        if existing is None:
            state.decisions[decision_id] = candidate
            state.timeline.append(TimelineEvent(decision_id, "family_decision_submitted", decided_at))

        winner = self._winning_decision(state)
        current = self._command_for(state)
        if winner.outcome == "KEEP_BLOCKED":
            if current is not None and current.status == "requested":
                current.status = "cancelled"
            command_id = None
        else:
            if current is None or current.decision_id != winner.decision_id:
                if current is not None and current.status == "requested":
                    current.status = "cancelled"
                command_id = f"unlock:{incident_id}:{winner.decision_id}"
                command = UnlockCommand(
                    command_id=command_id,
                    incident_id=incident_id,
                    device_id=state.device_id,
                    decision_id=winner.decision_id,
                    requested_at=winner.decided_at,
                    expires_at=winner.command_expires_at,
                )
                self._commands[command_id] = command
                state.command_id = command_id
                state.timeline.append(TimelineEvent(command_id, "unlock_requested", winner.decided_at))
            else:
                command_id = current.command_id
        return DecisionReceipt(winner.decision_id, winner.outcome, command_id)

    def set_device_online(self, device_id: str, *, online: bool) -> None:
        self._device_online[device_id] = online

    def retry_unlock(
        self,
        incident_id: str,
        *,
        retry_id: str,
        requested_at: datetime,
        expires_at: datetime,
    ) -> UnlockCommand:
        if expires_at <= requested_at:
            raise ValueError("Retry expiry must be after its request time")
        state = self._incidents[incident_id]
        winner = self._winning_decision(state) if state.decisions else None
        if winner is None or winner.outcome != "UNLOCK":
            raise ValueError("Retry requires a winning family unlock decision")
        current = self._command_for(state)
        if current is None or current.status not in {"expired", "failed"}:
            raise ValueError("Only an expired or failed unlock can be retried")
        command_id = f"unlock:{incident_id}:retry:{retry_id}"
        existing = self._commands.get(command_id)
        if existing is not None:
            return existing
        command = UnlockCommand(
            command_id=command_id,
            incident_id=incident_id,
            device_id=state.device_id,
            decision_id=winner.decision_id,
            requested_at=requested_at,
            expires_at=expires_at,
        )
        self._commands[command_id] = command
        state.command_id = command_id
        state.timeline.append(TimelineEvent(command_id, "unlock_requested", requested_at))
        return command

    def poll_commands(self, device_id: str, *, now: datetime) -> tuple[UnlockCommand, ...]:
        requested = tuple(
            command
            for command in self._commands.values()
            if command.device_id == device_id and command.status == "requested"
        )
        for command in requested:
            if now >= command.expires_at:
                command.status = "expired"
                self._incidents[command.incident_id].timeline.append(
                    TimelineEvent(f"{command.command_id}:expired", "unlock_expired", now)
                )
        if not self._device_online.get(device_id, False):
            return ()
        delivered: list[UnlockCommand] = []
        for command in requested:
            if command.status != "requested":
                continue
            command.status = "delivered"
            command.delivered_at = now
            self._incidents[command.incident_id].timeline.append(
                TimelineEvent(f"{command.command_id}:delivered", "unlock_delivered", now)
            )
            delivered.append(command)
        return tuple(delivered)

    def report_command_result(
        self,
        command_id: str,
        *,
        executed: bool,
        reported_at: datetime,
        failure_code: str | None = None,
        device_id: str | None = None,
    ) -> UnlockCommand:
        command = self._commands[command_id]
        if device_id is not None and command.device_id != device_id:
            raise KeyError(command_id)
        if command.status != "delivered":
            raise ValueError("Command must be delivered before execution can be reported")
        command.status = "executed" if executed else "failed"
        command.completed_at = reported_at
        command.failure_code = None if executed else (failure_code or "execution_failed")
        kind = "unlock_executed" if executed else "unlock_failed"
        self._incidents[command.incident_id].timeline.append(
            TimelineEvent(f"{command.command_id}:{command.status}", kind, reported_at)
        )
        return command

    @staticmethod
    def _winning_decision(state: _IncidentState) -> FamilyDecision:
        return min(
            state.decisions.values(),
            key=lambda decision: (decision.decided_at, decision.decision_id),
        )

    def _command_for(self, state: _IncidentState) -> UnlockCommand | None:
        if state.command_id is None:
            return None
        return self._commands[state.command_id]

    def incident_view(self, incident_id: str, *, now: datetime) -> IncidentView:
        state = self._incidents[incident_id]
        evidence = tuple(
            EvidenceView(
                evidence_id=item.evidence_id,
                kind=item.kind,
                captured_at=item.captured_at,
                expires_at=item.expires_at,
                state=(
                    "missing"
                    if item.locator is None
                    else "expired"
                    if now >= item.expires_at
                    else "available"
                ),
                access_url=(
                    f"/api/evidence/{item.evidence_id}"
                    if item.locator is not None and now < item.expires_at
                    else None
                ),
            )
            for item in state.evidence
        )
        winning_decision = self._winning_decision(state) if state.decisions else None
        command = self._command_for(state)
        return IncidentView(
            incident_id=state.incident_id,
            child_id=state.child_id,
            device_id=state.device_id,
            assessment=state.assessment,
            policy=state.policy,
            timeline=tuple(sorted(state.timeline, key=lambda item: (item.occurred_at, item.event_id))),
            evidence=evidence,
            family_decision=(
                FamilyDecisionView(
                    winner_id=winning_decision.decision_id,
                    outcome=winning_decision.outcome,
                    decided_at=winning_decision.decided_at,
                )
                if winning_decision is not None
                else None
            ),
            unlock=(
                UnlockView(
                    command_id=command.command_id,
                    status=command.status,
                    requested_at=command.requested_at,
                    expires_at=command.expires_at,
                    delivered_at=command.delivered_at,
                    completed_at=command.completed_at,
                    failure_code=command.failure_code,
                    execution_confirmed=command.status == "executed",
                )
                if command is not None
                else None
            ),
            classifier_controls_device=False,
        )
