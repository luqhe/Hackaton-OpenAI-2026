from __future__ import annotations

import json
import re
import subprocess
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path

import pytest

from guardian_core.family_transparency import (
    AgeBand,
    CapabilityAvailability,
    Heartbeat,
    ProtectionStatus,
    SharedDataKind,
    SharedDataRecord,
    build_capability_disclosures,
    build_transparency_snapshot,
    evaluate_protection,
    normalize_age_band,
)

ROOT = Path(__file__).resolve().parents[1]


def run_javascript(source: str) -> object:
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", source],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


class SemanticHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.elements: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements.append((tag, dict(attrs)))


def test_capability_disclosures_never_turn_a_plan_into_an_action() -> None:
    disclosures = build_capability_disclosures(
        {
            "fixture_analysis": True,
            "real_screen_observation": False,
            "local_ocr": False,
            "camera": False,
        },
        planned={"real_screen_observation", "local_ocr"},
    )

    by_key = {item.key: item for item in disclosures}
    assert by_key["fixture_analysis"].availability is CapabilityAvailability.IMPLEMENTED
    assert by_key["fixture_analysis"].action_enabled is True
    assert by_key["real_screen_observation"].availability is CapabilityAvailability.PLANNED
    assert by_key["real_screen_observation"].action_enabled is False
    assert by_key["local_ocr"].availability is CapabilityAvailability.PLANNED
    assert by_key["camera"].availability is CapabilityAvailability.UNAVAILABLE
    assert by_key["camera"].action_enabled is False


def test_capability_disclosures_ignore_backend_metadata_fields() -> None:
    disclosures = build_capability_disclosures(
        {
            "environment": "test",
            "notes": ["not a user-facing capability"],
            "fixture_analysis": True,
        }
    )

    assert [item.key for item in disclosures] == ["fixture_analysis"]


@pytest.mark.parametrize(
    ("heartbeat", "expected"),
    [
        (Heartbeat(received_at=datetime(2026, 8, 19, 15, 58, tzinfo=UTC)), ProtectionStatus.ACTIVE),
        (Heartbeat(received_at=datetime(2026, 8, 19, 15, 54, tzinfo=UTC)), ProtectionStatus.STALE),
        (
            Heartbeat(
                received_at=datetime(2026, 8, 19, 15, 58, tzinfo=UTC),
                error_code="observer_unavailable",
            ),
            ProtectionStatus.ERROR,
        ),
        (
            Heartbeat(received_at=datetime(2026, 8, 19, 15, 58, tzinfo=UTC), permissions_valid=False),
            ProtectionStatus.PERMISSION_REQUIRED,
        ),
    ],
)
def test_only_a_recent_healthy_heartbeat_can_be_active(
    heartbeat: Heartbeat, expected: ProtectionStatus
) -> None:
    state = evaluate_protection(
        {"real_screen_observation": True},
        heartbeat,
        now=datetime(2026, 8, 19, 16, 0, tzinfo=UTC),
        stale_after=timedelta(minutes=3),
    )

    assert state.status is expected
    assert state.is_active is (expected is ProtectionStatus.ACTIVE)


def test_a_fresh_demo_device_does_not_claim_active_protection() -> None:
    state = evaluate_protection(
        {"real_screen_observation": False},
        Heartbeat(received_at=datetime(2026, 8, 19, 15, 59, tzinfo=UTC)),
        now=datetime(2026, 8, 19, 16, 0, tzinfo=UTC),
    )

    assert state.status is ProtectionStatus.DEMO
    assert state.is_active is False


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("6-9", AgeBand.YOUNGER),
        ("10-12", AgeBand.PRETEEN),
        ("13-17", AgeBand.TEEN),
        ("unexpected", AgeBand.GENERAL),
        (None, AgeBand.GENERAL),
    ],
)
def test_age_band_has_a_calm_general_fallback(value: str | None, expected: AgeBand) -> None:
    assert normalize_age_band(value) is expected


def test_snapshot_exposes_minimum_share_metadata_without_device_control_claims() -> None:
    shared = SharedDataRecord(
        record_id="share-1",
        category="SAFETY_INCIDENT",
        shared_at=datetime(2026, 8, 19, 14, 30, tzinfo=UTC),
        recipient="FAMILY_GUARDIAN",
        data_kinds=(SharedDataKind.INCIDENT_SUMMARY, SharedDataKind.MINIMUM_EVIDENCE),
    )
    snapshot = build_transparency_snapshot(
        capabilities={"fixture_analysis": True, "real_screen_observation": False},
        planned={"real_screen_observation"},
        heartbeat=None,
        shared_records=[shared],
        age_band="10-12",
        now=datetime(2026, 8, 19, 16, 0, tzinfo=UTC),
    )

    assert snapshot.shared_records == (shared,)
    assert snapshot.age_band is AgeBand.PRETEEN
    assert snapshot.classifier_controls_device is False
    assert snapshot.live_screen_shared is False
    assert snapshot.protection.is_active is False


def test_shared_data_contract_rejects_live_screen_metadata() -> None:
    with pytest.raises(ValueError, match="live screen"):
        SharedDataRecord(
            record_id="share-unsafe",
            category="SAFETY_INCIDENT",
            shared_at=datetime(2026, 8, 19, 14, 30, tzinfo=UTC),
            recipient="FAMILY_GUARDIAN",
            data_kinds=("LIVE_SCREEN",),
        )


def test_i18n_catalogs_fallback_plural_timezone_and_pseudo_locale_execute_in_node() -> None:
    result = run_javascript(
        """
        import {
          ESSENTIAL_MESSAGE_KEYS,
          createI18n,
          validateCatalogs,
        } from './web/static/stage4-i18n.js';
        const pt = createI18n('pt-BR', { timeZone: 'America/Sao_Paulo' });
        const en = createI18n('en-US', { timeZone: 'UTC' });
        const fallback = createI18n('fr-FR');
        const pseudo = createI18n('qps-ploc');
        console.log(JSON.stringify({
          missing: validateCatalogs(ESSENTIAL_MESSAGE_KEYS),
          ptOne: pt.t('sharing.count', { count: 1 }),
          ptMany: pt.t('sharing.count', { count: 2 }),
          enOne: en.t('sharing.count', { count: 1 }),
          enMany: en.t('sharing.count', { count: 2 }),
          fallbackLocale: fallback.locale,
          fallbackStatus: fallback.t('status.demo'),
          saoPaulo: pt.formatDate('2026-08-19T12:30:00Z'),
          utc: en.formatDate('2026-08-19T12:30:00Z'),
          pseudo: pseudo.t('sharing.recipient', { recipient: 'Marina' }),
          normal: en.t('sharing.recipient', { recipient: 'Marina' }),
        }));
        """
    )

    assert result["missing"] == {"pt-BR": [], "en": []}
    assert result["ptOne"] == "1 compartilhamento"
    assert result["ptMany"] == "2 compartilhamentos"
    assert result["enOne"] == "1 share"
    assert result["enMany"] == "2 shares"
    assert result["fallbackLocale"] == "pt-BR"
    assert result["fallbackStatus"] == "Demonstração local"
    assert "09:30" in result["saoPaulo"]
    assert "12:30" in result["utc"]
    assert result["pseudo"].startswith("[")
    assert result["pseudo"].endswith("]")
    assert "Marina" in result["pseudo"]
    assert len(result["pseudo"]) > len(result["normal"])


def test_age_content_is_distinct_and_unknown_band_uses_general_copy() -> None:
    result = run_javascript(
        """
        import { createI18n } from './web/static/stage4-i18n.js';
        import { childLanguage } from './web/static/stage4-transparency.js';
        const i18n = createI18n('pt-BR');
        console.log(JSON.stringify({
          younger: childLanguage('6-9', i18n),
          teen: childLanguage('13-17', i18n),
          fallback: childLanguage('unknown', i18n),
          general: childLanguage('general', i18n),
        }));
        """
    )

    assert result["younger"] != result["teen"]
    assert result["fallback"] == result["general"]
    for variant in (result["younger"], result["teen"], result["fallback"]):
        assert variant["classifier"]
        assert variant["sharing"]
        assert "culpa" not in variant["classifier"].lower()


def test_browser_view_model_ignores_nonboolean_capability_metadata() -> None:
    result = run_javascript(
        """
        import { buildTransparencyViewModel } from './web/static/stage4-transparency.js';
        const view = buildTransparencyViewModel({
          capabilities: {
            environment: 'test',
            notes: ['not a capability'],
            fixture_analysis: true,
            real_screen_observation: false,
          },
          plannedCapabilities: ['real_screen_observation'],
        }, { now: '2026-08-19T16:00:00Z' });
        console.log(JSON.stringify(view.capabilities));
        """
    )

    assert result == [
        {"key": "fixture_analysis", "availability": "implemented"},
        {"key": "real_screen_observation", "availability": "planned"},
    ]


def test_real_transparency_component_has_semantics_and_safe_status_derivation() -> None:
    result = run_javascript(
        """
        import { renderChildTransparency } from './web/static/stage4-transparency.js';
        const common = {
          capabilities: {
            fixture_analysis: true,
            real_screen_observation: true,
            local_ocr: false,
            camera: false,
          },
          plannedCapabilities: ['local_ocr'],
          ageBand: '10-12',
          sharedRecords: [{
            id: 'share-1',
            category: 'SAFETY_INCIDENT',
            sharedAt: '2026-08-19T14:30:00Z',
            recipient: 'Marina & família',
            dataKinds: ['INCIDENT_SUMMARY', 'MINIMUM_EVIDENCE'],
            rawContent: '<img src=x onerror=alert(1)>',
          }],
        };
        const stale = renderChildTransparency({
          ...common,
          heartbeat: { receivedAt: '2026-08-19T15:50:00Z', permissionsValid: true },
        }, { locale: 'pt-BR', timeZone: 'UTC', now: '2026-08-19T16:00:00Z' });
        const error = renderChildTransparency({
          ...common,
          heartbeat: {
            receivedAt: '2026-08-19T15:59:00Z',
            permissionsValid: true,
            errorCode: 'observer_unavailable',
          },
        }, { locale: 'en', timeZone: 'UTC', now: '2026-08-19T16:00:00Z' });
        console.log(JSON.stringify({ stale, error }));
        """
    )

    stale_html = result["stale"]
    error_html = result["error"]
    parsed = SemanticHTML()
    parsed.feed(stale_html)
    tags = [tag for tag, _ in parsed.elements]
    status_regions = [attrs for tag, attrs in parsed.elements if attrs.get("role") == "status"]

    assert tags.count("section") >= 3
    assert "h2" in tags and "h3" in tags
    assert "ul" in tags and "li" in tags
    assert "details" in tags and "summary" in tags
    assert "time" in tags
    assert len(status_regions) == 1
    assert status_regions[0]["aria-live"] == "polite"
    assert status_regions[0]["aria-atomic"] == "true"
    assert "Proteção ativa" not in stale_html
    assert "Protection active" not in error_html
    assert "Planejado" in stale_html
    assert "Marina &amp; família" in stale_html
    assert "<img src=x" not in stale_html
    assert "classificador" in stale_html.lower()
    assert "não controla" in stale_html.lower()


def test_component_styles_support_focus_touch_zoom_contrast_and_reduced_motion() -> None:
    css = (ROOT / "web" / "static" / "stage4-transparency.css").read_text(encoding="utf-8")

    assert re.search(r":focus-visible\s*\{[^}]*outline:\s*3px", css, re.DOTALL)
    touch_rule = re.search(r"\.stage4-transparency\s+summary\s*\{(?P<body>[^}]*)\}", css, re.DOTALL)
    assert touch_rule is not None
    assert re.search(r"min-height:\s*44px", touch_rule.group("body"))
    assert re.search(r"@media\s*\(max-width:\s*48rem\)", css)
    assert re.search(r"grid-template-columns:\s*minmax\(0,\s*1fr\)", css)
    assert re.search(r"@media\s*\(prefers-reduced-motion:\s*reduce\)", css)
    assert re.search(r"@media\s*\(prefers-contrast:\s*more\)", css)
