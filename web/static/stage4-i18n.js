const CATALOGS = {
  "pt-BR": {
    "transparency.title": "O que o Guardian mostra para você",
    "transparency.intro":
      "Aqui você pode conferir o estado atual e o que foi compartilhado.",
    "section.capabilities": "O que esta versão consegue fazer",
    "section.sharing": "O que foi compartilhado",
    "section.privacy": "Limites importantes",
    "status.heading": "Estado atual",
    "status.active": "Proteção ativa",
    "status.demo": "Demonstração local",
    "status.inactive": "Proteção não confirmada",
    "status.stale": "Informação do dispositivo desatualizada",
    "status.error": "Não foi possível confirmar o estado",
    "status.permission_required": "Uma permissão precisa ser revisada",
    "status.detail.active":
      "O dispositivo enviou uma atualização recente e as permissões estão válidas.",
    "status.detail.demo":
      "Esta versão usa apenas exemplos controlados. Ela não observa a tela real.",
    "status.detail.inactive":
      "Ainda não recebemos uma atualização confiável do dispositivo.",
    "status.detail.stale":
      "A última atualização é antiga. Isso não significa que alguém fez algo errado.",
    "status.detail.error":
      "Houve um problema técnico. Isso não significa que alguém fez algo errado.",
    "status.detail.permission_required":
      "Uma pessoa responsável pode revisar as permissões do dispositivo.",
    "capability.implemented": "Implementado",
    "capability.planned": "Planejado",
    "capability.unavailable": "Não disponível",
    "capability.fixture_analysis": "Análise de exemplos controlados",
    "capability.real_screen_observation": "Observação da tela real",
    "capability.local_ocr": "Leitura local de texto na tela",
    "capability.system_audio": "Áudio do sistema",
    "capability.microphone": "Microfone",
    "capability.camera": "Câmera",
    "capability.authentication": "Conta autenticada",
    "capability.tenant_isolation": "Separação entre famílias",
    "capability.unknown": "Capacidade informada pelo sistema",
    "sharing.count": {
      one: "{count} compartilhamento",
      other: "{count} compartilhamentos",
    },
    "sharing.empty":
      "Nenhum compartilhamento foi registrado para este período.",
    "sharing.recipient": "Compartilhado com {recipient}",
    "sharing.details": "Ver quais dados",
    "sharing.category.SAFETY_INCIDENT": "Incidente de segurança",
    "sharing.category.DAILY_SUMMARY": "Resumo diário",
    "sharing.category.unknown": "Registro de compartilhamento",
    "sharing.kind.INCIDENT_SUMMARY": "Resumo do incidente",
    "sharing.kind.MINIMUM_EVIDENCE": "Evidência mínima",
    "sharing.kind.DAILY_APP_USAGE": "Uso diário agregado por aplicativo",
    "sharing.kind.CHILD_EXPLANATION": "Explicação enviada por você",
    "sharing.kind.unknown": "Dado mínimo registrado",
    "privacy.no_live_screen":
      "O Guardian não oferece uma tela ao vivo para a família.",
    "privacy.no_hidden_monitoring":
      "Esta tela não afirma que existe observação ou coleta que ainda não foi implementada.",
    "date.unavailable": "Data indisponível",
    "age.younger.classifier":
      "O Guardian procura sinais de risco. As regras da família decidem o que acontece; a análise não controla o dispositivo.",
    "age.younger.sharing":
      "Você pode ver, com palavras simples, cada informação que foi enviada à sua família.",
    "age.preteen.classifier":
      "A análise identifica possíveis sinais de risco. Depois, regras definidas pela família decidem a ação; o classificador não controla o dispositivo.",
    "age.preteen.sharing":
      "Você pode conferir cada compartilhamento e quais tipos mínimos de dados ele incluiu.",
    "age.teen.classifier":
      "O classificador sinaliza contexto, mas não executa ações. Somente regras determinísticas e componentes autorizados podem agir no dispositivo.",
    "age.teen.sharing":
      "Este histórico registra metadados mínimos de cada compartilhamento com a pessoa responsável.",
    "age.general.classifier":
      "A análise pode sinalizar riscos. Ela nunca controla o dispositivo; regras separadas decidem qualquer ação.",
    "age.general.sharing":
      "Aqui você pode revisar, com calma, quais dados mínimos foram compartilhados.",
  },
  en: {
    "transparency.title": "What Guardian shows you",
    "transparency.intro":
      "Here you can check the current status and what was shared.",
    "section.capabilities": "What this version can do",
    "section.sharing": "What was shared",
    "section.privacy": "Important boundaries",
    "status.heading": "Current status",
    "status.active": "Protection active",
    "status.demo": "Local demonstration",
    "status.inactive": "Protection not confirmed",
    "status.stale": "Device information is out of date",
    "status.error": "The status could not be confirmed",
    "status.permission_required": "A permission needs review",
    "status.detail.active":
      "The device sent a recent update and its permissions are valid.",
    "status.detail.demo":
      "This version only uses controlled examples. It does not observe the real screen.",
    "status.detail.inactive":
      "We have not received a reliable device update yet.",
    "status.detail.stale":
      "The last update is old. This does not mean anyone did something wrong.",
    "status.detail.error":
      "There was a technical problem. This does not mean anyone did something wrong.",
    "status.detail.permission_required":
      "A family guardian can review the device permissions.",
    "capability.implemented": "Implemented",
    "capability.planned": "Planned",
    "capability.unavailable": "Not available",
    "capability.fixture_analysis": "Controlled-example analysis",
    "capability.real_screen_observation": "Real-screen observation",
    "capability.local_ocr": "Local on-screen text reading",
    "capability.system_audio": "System audio",
    "capability.microphone": "Microphone",
    "capability.camera": "Camera",
    "capability.authentication": "Authenticated account",
    "capability.tenant_isolation": "Separation between families",
    "capability.unknown": "System-reported capability",
    "sharing.count": { one: "{count} share", other: "{count} shares" },
    "sharing.empty": "No sharing was recorded for this period.",
    "sharing.recipient": "Shared with {recipient}",
    "sharing.details": "See which data",
    "sharing.category.SAFETY_INCIDENT": "Safety incident",
    "sharing.category.DAILY_SUMMARY": "Daily summary",
    "sharing.category.unknown": "Sharing record",
    "sharing.kind.INCIDENT_SUMMARY": "Incident summary",
    "sharing.kind.MINIMUM_EVIDENCE": "Minimum evidence",
    "sharing.kind.DAILY_APP_USAGE": "Aggregated daily app usage",
    "sharing.kind.CHILD_EXPLANATION": "Explanation you submitted",
    "sharing.kind.unknown": "Minimum recorded data",
    "privacy.no_live_screen":
      "Guardian does not provide the family with a live screen.",
    "privacy.no_hidden_monitoring":
      "This page does not claim observation or collection that has not been implemented.",
    "date.unavailable": "Date unavailable",
    "age.younger.classifier":
      "Guardian looks for risk signals. Family rules decide what happens; the analysis does not control the device.",
    "age.younger.sharing":
      "You can see, in simple words, each piece of information sent to your family.",
    "age.preteen.classifier":
      "The analysis identifies possible risk signals. Family rules then decide the action; the classifier does not control the device.",
    "age.preteen.sharing":
      "You can check every share and the minimum kinds of data it included.",
    "age.teen.classifier":
      "The classifier flags context but does not take action. Only deterministic rules and authorized components can act on the device.",
    "age.teen.sharing":
      "This history records minimum metadata for every share with the family guardian.",
    "age.general.classifier":
      "The analysis may flag risks. It never controls the device; separate rules decide any action.",
    "age.general.sharing":
      "Here you can calmly review which minimum data was shared.",
  },
};

export const ESSENTIAL_MESSAGE_KEYS = Object.freeze([
  "transparency.title",
  "section.capabilities",
  "section.sharing",
  "status.active",
  "status.demo",
  "status.stale",
  "status.error",
  "capability.implemented",
  "capability.planned",
  "sharing.count",
  "sharing.recipient",
  "privacy.no_live_screen",
  "age.general.classifier",
]);

export function validateCatalogs(keys = ESSENTIAL_MESSAGE_KEYS) {
  return Object.fromEntries(
    Object.entries(CATALOGS).map(([locale, catalog]) => [
      locale,
      keys.filter((key) => catalog[key] === undefined),
    ]),
  );
}

export function createI18n(requestedLocale = "pt-BR", options = {}) {
  const locale = resolveLocale(requestedLocale);
  const catalogLocale = locale === "qps-ploc" ? "en" : locale;
  const catalog = CATALOGS[catalogLocale];
  const fallbackCatalog = CATALOGS["pt-BR"];
  const timeZone = validTimeZone(options.timeZone) ? options.timeZone : "UTC";
  const formatLocale = locale === "qps-ploc" ? "en" : locale;

  function translate(key, variables = {}) {
    let message = catalog[key] ?? fallbackCatalog[key] ?? key;
    if (typeof message === "object") {
      const count = Number(variables.count ?? 0);
      const plural = new Intl.PluralRules(formatLocale).select(count);
      message = message[plural] ?? message.other;
    }
    if (locale === "qps-ploc") message = pseudoLocalize(message);
    return interpolate(message, variables);
  }

  function formatDate(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return translate("date.unavailable");
    return new Intl.DateTimeFormat(formatLocale, {
      dateStyle: "medium",
      timeStyle: "short",
      hourCycle: "h23",
      timeZone,
    }).format(date);
  }

  return Object.freeze({ locale, timeZone, t: translate, formatDate });
}

export function pseudoLocalize(message) {
  const accent = {
    a: "à",
    A: "À",
    e: "ë",
    E: "Ë",
    i: "ï",
    I: "Ï",
    o: "ô",
    O: "Ô",
    u: "ü",
    U: "Ü",
  };
  const transformed = String(message)
    .split(/(\{[^}]+\})/u)
    .map((part) =>
      part.startsWith("{")
        ? part
        : [...part].map((character) => accent[character] ?? character).join(""),
    )
    .join("");
  return `[${transformed} ~~]`;
}

function resolveLocale(requestedLocale) {
  const normalized = String(requestedLocale || "").toLowerCase();
  if (normalized === "qps-ploc") return "qps-ploc";
  if (normalized === "en" || normalized.startsWith("en-")) return "en";
  if (normalized === "pt" || normalized.startsWith("pt-")) return "pt-BR";
  return "pt-BR";
}

function validTimeZone(timeZone) {
  if (!timeZone) return false;
  try {
    new Intl.DateTimeFormat("en", { timeZone }).format();
    return true;
  } catch {
    return false;
  }
}

function interpolate(message, variables) {
  return String(message).replace(/\{([a-zA-Z0-9_]+)\}/gu, (_, name) =>
    variables[name] === undefined ? `{${name}}` : String(variables[name]),
  );
}
