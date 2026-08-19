import { createI18n } from "./stage4-i18n.js";

const AGE_BANDS = new Set(["6-9", "10-12", "13-17", "general"]);
const STATUS_KEYS = new Set([
  "active",
  "demo",
  "inactive",
  "stale",
  "error",
  "permission_required",
]);

export function deriveProtectionStatus(
  capabilities,
  heartbeat,
  { now = new Date(), staleAfterMs = 180_000 } = {},
) {
  if (capabilities?.real_screen_observation !== true) return "demo";
  if (!heartbeat) return "inactive";
  if (heartbeat.errorCode) return "error";
  if (heartbeat.permissionsValid !== true) return "permission_required";

  const checkedAt = new Date(now).getTime();
  const heartbeatAt = new Date(heartbeat.receivedAt).getTime();
  if (!Number.isFinite(checkedAt) || !Number.isFinite(heartbeatAt))
    return "error";
  const age = checkedAt - heartbeatAt;
  if (age < -60_000) return "error";
  if (age > staleAfterMs) return "stale";
  return "active";
}

export function childLanguage(ageBand, i18n) {
  const band = AGE_BANDS.has(ageBand) ? ageBand : "general";
  const keyBand =
    band === "6-9"
      ? "younger"
      : band === "10-12"
        ? "preteen"
        : band === "13-17"
          ? "teen"
          : "general";
  return Object.freeze({
    classifier: i18n.t(`age.${keyBand}.classifier`),
    sharing: i18n.t(`age.${keyBand}.sharing`),
  });
}

export function buildTransparencyViewModel(payload, options = {}) {
  const i18n =
    options.i18n ?? createI18n(options.locale, { timeZone: options.timeZone });
  const status = deriveProtectionStatus(
    payload.capabilities,
    payload.heartbeat,
    {
      now: options.now,
      staleAfterMs: options.staleAfterMs,
    },
  );
  const planned = new Set(payload.plannedCapabilities ?? []);
  const capabilities = Object.entries(payload.capabilities ?? {})
    .filter(([, implemented]) => typeof implemented === "boolean")
    .map(([key, implemented]) => ({
      key,
      availability:
        implemented === true
          ? "implemented"
          : planned.has(key)
            ? "planned"
            : "unavailable",
    }));
  return Object.freeze({
    i18n,
    status: STATUS_KEYS.has(status) ? status : "error",
    capabilities,
    sharedRecords: Array.isArray(payload.sharedRecords)
      ? payload.sharedRecords
      : [],
    language: childLanguage(payload.ageBand, i18n),
  });
}

export function renderChildTransparency(payload, options = {}) {
  const view = buildTransparencyViewModel(payload, options);
  const { i18n } = view;
  const capabilityItems = view.capabilities
    .map((capability) => {
      const labelKey = `capability.${capability.key}`;
      const translated = i18n.t(labelKey);
      const label =
        translated === labelKey ? i18n.t("capability.unknown") : translated;
      return `<li class="stage4-capability stage4-capability--${capability.availability}">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(i18n.t(`capability.${capability.availability}`))}</strong>
      </li>`;
    })
    .join("");
  const sharingItems = view.sharedRecords
    .map((record) => renderShare(record, i18n))
    .join("");

  return `<section class="stage4-transparency" aria-labelledby="stage4-transparency-title">
    <header class="stage4-transparency__header">
      <h2 id="stage4-transparency-title">${escapeHtml(i18n.t("transparency.title"))}</h2>
      <p>${escapeHtml(i18n.t("transparency.intro"))}</p>
      <div class="stage4-status stage4-status--${view.status}" role="status" aria-live="polite" aria-atomic="true" tabindex="-1">
        <strong>${escapeHtml(i18n.t(`status.${view.status}`))}</strong>
        <span>${escapeHtml(i18n.t(`status.detail.${view.status}`))}</span>
      </div>
    </header>
    <div class="stage4-transparency__grid">
      <section aria-labelledby="stage4-capabilities-title">
        <h3 id="stage4-capabilities-title">${escapeHtml(i18n.t("section.capabilities"))}</h3>
        <p>${escapeHtml(view.language.classifier)}</p>
        <ul class="stage4-capabilities">${capabilityItems}</ul>
      </section>
      <section aria-labelledby="stage4-sharing-title">
        <h3 id="stage4-sharing-title">${escapeHtml(i18n.t("section.sharing"))}</h3>
        <p>${escapeHtml(view.language.sharing)}</p>
        <p class="stage4-sharing-count">${escapeHtml(
          i18n.t("sharing.count", { count: view.sharedRecords.length }),
        )}</p>
        ${
          sharingItems
            ? `<ol class="stage4-sharing">${sharingItems}</ol>`
            : `<p class="stage4-empty">${escapeHtml(i18n.t("sharing.empty"))}</p>`
        }
      </section>
    </div>
    <section class="stage4-boundaries" aria-labelledby="stage4-boundaries-title">
      <h3 id="stage4-boundaries-title">${escapeHtml(i18n.t("section.privacy"))}</h3>
      <ul>
        <li>${escapeHtml(i18n.t("privacy.no_live_screen"))}</li>
        <li>${escapeHtml(i18n.t("privacy.no_hidden_monitoring"))}</li>
      </ul>
    </section>
  </section>`;
}

function renderShare(record, i18n) {
  const categoryKey = `sharing.category.${record.category}`;
  const translatedCategory = i18n.t(categoryKey);
  const category =
    translatedCategory === categoryKey
      ? i18n.t("sharing.category.unknown")
      : translatedCategory;
  const dataKinds = Array.isArray(record.dataKinds) ? record.dataKinds : [];
  const kindItems = dataKinds
    .map((kind) => {
      const kindKey = `sharing.kind.${kind}`;
      const translatedKind = i18n.t(kindKey);
      return `<li>${escapeHtml(
        translatedKind === kindKey
          ? i18n.t("sharing.kind.unknown")
          : translatedKind,
      )}</li>`;
    })
    .join("");
  const isoDate = validIsoDate(record.sharedAt);
  return `<li class="stage4-share">
    <article>
      <h4>${escapeHtml(category)}</h4>
      <p>${escapeHtml(i18n.t("sharing.recipient", { recipient: record.recipient ?? "" }))}</p>
      <time datetime="${escapeHtml(isoDate)}">${escapeHtml(i18n.formatDate(record.sharedAt))}</time>
      <details>
        <summary>${escapeHtml(i18n.t("sharing.details"))}</summary>
        <ul>${kindItems}</ul>
      </details>
    </article>
  </li>`;
}

function validIsoDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toISOString();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
