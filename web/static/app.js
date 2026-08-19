const app = document.querySelector("#app");
const pageTitle = document.querySelector("#page-title");
const pageEyebrow = document.querySelector("#page-eyebrow");
const toast = document.querySelector("#toast");
const protectionStatus = document.querySelector("#protection-status");
const protectionLabel = protectionStatus.querySelector(".protection-label");
let productCapabilities = null;
let currentProtectionState = "inactive";
const onboardingState = {
  familyId: null,
  childId: null,
  pairing: null,
  device: null,
};

const labels = {
  DANGEROUS_CONTACT: "Contato potencialmente perigoso",
  ADULT_CONTENT: "Conteúdo adulto",
  HATE_SPEECH: "Discurso de ódio",
  OTHER: "Outro sinal",
  BLOCKED: "Bloqueado",
  DETECTED: "Detectado",
  UNLOCK_REQUESTED: "Revisão solicitada",
  UNLOCKED: "Desbloqueado",
  KEPT_BLOCKED: "Bloqueio mantido",
};

const policyDescriptions = {
  ADULT_CONTENT: "Nudez e conteúdo sexual explícito",
  HATE_SPEECH: "Linguagem discriminatória e desumanizante",
  DANGEROUS_CONTACT: "Pedidos progressivos de informações pessoais",
  OTHER: "Sinais ainda não classificados",
};

const categoryExplanations = {
  DANGEROUS_CONTACT:
    "A conversa reuniu pedidos de idade, escola, perfil social, fotos ou localização. Em conjunto, esses pedidos podem indicar uma tentativa de obter informações pessoais.",
  ADULT_CONTENT:
    "Foi identificado conteúdo sexual explícito que precisa ser revisado por um responsável.",
  HATE_SPEECH:
    "Foram identificadas mensagens com linguagem discriminatória ou desumanizante.",
  OTHER:
    "Foi identificado um sinal que precisa ser revisado por um responsável.",
};

const evidenceDescriptions = {
  age: "Pedido de idade ao longo da conversa",
  school: "Pedido do nome da escola",
  social: "Pedido de perfil em rede social",
  instagram: "Pedido de perfil em rede social",
  photo: "Pedido de foto pessoal",
  location: "Pedido de localização",
};

function observationCapabilityItems(capabilities) {
  return [
    capabilities.real_screen_observation
      ? "Captura da tela real — disponível"
      : "Tela do dispositivo — não acessada",
    capabilities.local_ocr
      ? "Leitura local de texto — disponível"
      : "Texto de outros aplicativos — não acessado",
    capabilities.system_audio
      ? "Áudio do sistema — disponível"
      : "Áudio do sistema — não acessado",
    capabilities.microphone
      ? "Microfone — disponível"
      : "Microfone — não acessado",
    capabilities.camera ? "Câmera — disponível" : "Câmera — não acessada",
  ];
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function applicationName(value) {
  return value === "Guardian Demo Chat" ? "Chat simulado" : value;
}

function explanationFor(incident) {
  return categoryExplanations[incident.category] || incident.explanation;
}

function evidenceDescription(value) {
  const text = String(value ?? "");
  const key = text
    .replace(/^Progressive request detected:\s*/i, "")
    .trim()
    .toLowerCase();
  return evidenceDescriptions[key] || text;
}

async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (!response.ok) {
    let message = "Não foi possível concluir a operação.";
    try {
      message = (await response.json()).detail || message;
    } catch {}
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}

function notify(message) {
  toast.textContent = message;
  toast.hidden = false;
  window.clearTimeout(notify.timer);
  notify.timer = window.setTimeout(() => {
    toast.hidden = true;
  }, 3200);
}

function setPage(title, eyebrow, route) {
  document.title = `${title} · Guardian`;
  pageTitle.textContent = title;
  pageEyebrow.textContent = eyebrow;
  document.querySelectorAll(".nav a").forEach((link) => {
    const isActive = link.dataset.route === route;
    link.classList.toggle("active", isActive);
    if (isActive) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
}

function updateCapabilityStatus(capabilities, protectionState) {
  currentProtectionState = protectionState;
  const observationActive =
    capabilities.real_screen_observation && protectionState === "active";
  protectionStatus.classList.toggle("simulated", !observationActive);
  const labelsByState = {
    active: "Proteção ativa",
    stale: "Conexão desatualizada",
    error: "Agente com falha",
    permission_required: "Permissão necessária",
    inactive: "Aguardando o agente",
    demo: "Dados simulados",
  };
  protectionLabel.textContent = observationActive
    ? labelsByState.active
    : labelsByState[protectionState] || labelsByState.inactive;
}

function formatDate(value) {
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function dailySafetyReportPath(childId) {
  const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  const date = new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone,
  }).format(new Date());
  const query = new URLSearchParams({ date, timezone: timeZone });
  return `/family/children/${encodeURIComponent(childId)}/daily-safety-report?${query}`;
}

function safetyMetric(report, key) {
  return Number(report.metrics?.[key] || 0);
}

function incidentRow(incident) {
  return `
    <a class="incident-row" href="/incidents/${encodeURIComponent(incident.id)}">
      <span class="risk-icon" aria-hidden="true">!</span>
      <div>
        <strong>${escapeHtml(labels[incident.category] || incident.category)}</strong>
        <p>${escapeHtml(applicationName(incident.application))} · ${formatDate(incident.occurred_at)}</p>
      </div>
      <span class="status ${incident.status.toLowerCase()}">${escapeHtml(labels[incident.status] || incident.status)}</span>
    </a>`;
}

async function dashboard() {
  setPage("Visão geral", "FAMÍLIA FERREIRA", "dashboard");
  const [incidents, report, device] = await Promise.all([
    api("/incidents"),
    api(dailySafetyReportPath("child-demo")),
    api("/devices/device-demo"),
  ]);
  const latest = incidents.length
    ? incidents.slice(0, 5).map(incidentRow).join("")
    : `<div class="empty"><div class="empty-mark">✓</div><h3>Nenhum incidente hoje</h3><p>${productCapabilities.real_screen_observation ? "Nenhum evento de risco foi identificado até agora." : "Nenhum incidente foi registrado nesta simulação."}</p></div>`;
  const deviceStatus =
    currentProtectionState === "active"
      ? `<strong>● Protegido</strong><span>Análise no dispositivo ativa</span>`
      : `<strong>◌ ${escapeHtml(protectionLabel.textContent)}</strong><span>Proteção não confirmada por heartbeat</span>`;
  const reportState =
    report.data_status === "AVAILABLE"
      ? "Sessões recebidas"
      : report.data_status === "SYNC_PENDING"
        ? "Sincronização pendente"
        : "Sem sessões recebidas";
  app.innerHTML = `
    <div class="card profile-strip">
      <div class="avatar">L</div>
      <div class="profile-copy"><h2>Lucas</h2><p>${escapeHtml(device.name)} · ${escapeHtml(device.platform)}</p></div>
      <div class="device-state">${deviceStatus}</div>
    </div>
    <div class="section-heading"><h2>Hoje</h2><span></span></div>
    <div class="grid metrics">
      <div class="card metric" data-tone="calm"><span class="metric-label">Eventos de risco</span><strong class="metric-value">${safetyMetric(report, "risk_events")}</strong><span class="metric-detail">Contagem de segurança, sem nota de produtividade</span></div>
      <div class="card metric" data-tone="attention"><span class="metric-label">Intervenções da política</span><strong class="metric-value">${safetyMetric(report, "policy_interventions")}</strong><span class="metric-detail">Decisões determinísticas da família</span></div>
      <div class="card metric" data-tone="info"><span class="metric-label">Dados do relatório</span><strong class="metric-value metric-value--status">${escapeHtml(reportState)}</strong><span class="metric-detail">Sessões reportadas pelo observer; autenticação do dispositivo depende da Etapa 2</span></div>
    </div>
    <div class="grid two">
      <div>
        <div class="section-heading"><h2>Atividade de proteção</h2><a href="/child">Ver relatório diário →</a></div>
        <div class="card incident-list">${latest}</div>
      </div>
      <div>
        <div class="section-heading"><h2>Como o Guardian decide</h2></div>
        <div class="card insight">
          <p class="eyebrow">ANÁLISE DE INCIDENTES</p>
          <h2>O contexto vem antes da intervenção.</h2>
          <p>O Guardian considera a conversa recente e as regras definidas pela família. Nesta sessão, os dados são simulados e nenhuma tela real está sendo observada.</p>
          <ul class="capability-summary">${observationCapabilityItems(
            productCapabilities,
          )
            .map((item) => `<li>${escapeHtml(item)}</li>`)
            .join("")}</ul>
        </div>
      </div>
    </div>`;
}

async function incidentDetail(id) {
  setPage("Revisar incidente", "SEGURANÇA DE LUCAS", "dashboard");
  const [incident, experience] = await Promise.all([
    api(`/incidents/${encodeURIComponent(id)}`),
    api(`/incidents/${encodeURIComponent(id)}/experience`),
  ]);
  const canDecide =
    !experience.family_decision &&
    ["BLOCKED", "UNLOCK_REQUESTED"].includes(incident.status);
  const timeline = experience.timeline
    .map(
      (event) => `
        <li>
          <span>${formatDate(event.occurred_at)}</span>
          <strong>${escapeHtml(labels[event.kind] || event.kind.replaceAll("_", " "))}</strong>
        </li>`,
    )
    .join("");
  const decisionStatus = experience.family_decision
    ? `<p class="decision-state"><strong>Decisão registrada:</strong> ${experience.family_decision.outcome === "UNLOCK" ? "desbloquear" : "manter bloqueado"}.</p>`
    : `<p class="lead">Revise a explicação e escolha uma ação. O classificador não executa comandos.</p>`;
  const unlockStatus = experience.unlock
    ? `<p class="command-state"><strong>Prévia do protocolo de execução:</strong> ${escapeHtml(experience.unlock.status)}${experience.unlock.failure_code ? ` · ${escapeHtml(experience.unlock.failure_code)}` : ""}. A integração autenticada com o agente depende da Etapa 2.</p>`
    : "";
  app.innerHTML = `
    <a class="detail-back" href="/">← Voltar para a visão geral</a>
    <article class="card incident-hero">
      <div class="hero-line">
        <div><p class="eyebrow">INCIDENTE DE ALTA PRIORIDADE</p><h2>${escapeHtml(labels[incident.category] || incident.category)}</h2></div>
        <span class="status ${incident.status.toLowerCase()}">${escapeHtml(labels[incident.status] || incident.status)}</span>
      </div>
      <p class="lead">${escapeHtml(explanationFor(incident))}</p>
      <div class="explanation-separation">
        <div><span>Classificação</span><strong>${escapeHtml(experience.assessment.classifier_version)}</strong><p>Identificou sinais e confiança. Não controla o dispositivo.</p></div>
        <div><span>Política familiar</span><strong>${escapeHtml(experience.policy.policy_version)}</strong><p>${escapeHtml(experience.policy.rule)}</p></div>
      </div>
      <div class="facts">
        <div class="fact"><span>Aplicativo</span><strong>${escapeHtml(applicationName(incident.application))}</strong></div>
        <div class="fact"><span>Direção</span><strong>${incident.direction === "CHILD_AS_TARGET" ? "Lucas como alvo" : escapeHtml(incident.direction)}</strong></div>
        <div class="fact"><span>Confiança</span><strong>${Math.round(incident.confidence * 100)}%</strong></div>
        <div class="fact"><span>Horário</span><strong>${formatDate(incident.occurred_at)}</strong></div>
      </div>
    </article>
    <div class="incident-review-grid">
      <section class="signals-panel">
        <div class="section-heading"><h2>Sinais relevantes</h2></div>
        <div class="card card-pad">
          <ul class="evidence-list">${incident.evidence.map((item) => `<li>${escapeHtml(evidenceDescription(item))}</li>`).join("")}</ul>
        </div>
        <div class="section-heading"><h2>Linha do tempo</h2></div>
        <div class="card card-pad"><ol class="timeline-list">${timeline}</ol></div>
      </section>
      <aside class="decision-column">
        <div class="section-heading"><h2>Decisão da família</h2></div>
        <div class="card card-pad decision-panel" role="region" aria-label="Decisão da família">
          ${incident.child_explanation ? `<p class="eyebrow">EXPLICAÇÃO DE LUCAS</p><p>${escapeHtml(incident.child_explanation)}</p>` : `<p class="lead">Lucas ainda não enviou uma explicação para este bloqueio.</p>`}
          ${decisionStatus}
          ${unlockStatus}
          <p class="decision-hint">Revise os sinais antes de registrar uma decisão.</p>
          <div class="action-bar">
            <button class="button secondary" id="unlock" ${canDecide ? "" : "disabled"}>Registrar decisão de desbloquear</button>
            <button class="button danger-solid" id="keep" ${canDecide ? "" : "disabled"}>Manter bloqueado</button>
          </div>
          <a class="button text-button" href="/support?incident=${encodeURIComponent(id)}">Contestar esta classificação</a>
        </div>
      </aside>
      ${incident.screenshot_urls.length ? `<section class="evidence-panel"><div class="section-heading"><h2>Evidência selecionada</h2><span>Evidência mínima</span></div><div class="card card-pad">${incident.screenshot_urls.map((url, index) => `<iframe class="evidence-frame" src="${escapeHtml(url)}" title="Evidência ${index + 1}" loading="lazy" sandbox></iframe>`).join("")}</div></section>` : ""}
    </div>`;
  document.querySelector("#unlock")?.addEventListener("click", async () => {
    const decidedAt = new Date();
    await api(`/incidents/${encodeURIComponent(id)}/family-decisions`, {
      method: "POST",
      body: JSON.stringify({
        decision_id: `decision-${Date.now()}`,
        outcome: "UNLOCK",
        decided_at: decidedAt.toISOString(),
        command_expires_at: new Date(
          decidedAt.getTime() + 10 * 60 * 1000,
        ).toISOString(),
      }),
    });
    notify(
      "Decisão registrada nesta prévia. A execução segura pelo agente depende da Etapa 2.",
    );
    await incidentDetail(id);
  });
  document.querySelector("#keep")?.addEventListener("click", async () => {
    await api(`/incidents/${encodeURIComponent(id)}/family-decisions`, {
      method: "POST",
      body: JSON.stringify({
        decision_id: `decision-${Date.now()}`,
        outcome: "KEEP_BLOCKED",
        decided_at: new Date().toISOString(),
        command_expires_at: null,
      }),
    });
    notify("Decisão de manter o bloqueio registrada.");
    await incidentDetail(id);
  });
}

async function childPage() {
  setPage("Lucas", "PROTEÇÃO E TRANSPARÊNCIA", "child");
  const params = new URLSearchParams(location.search);
  const incidentId = params.get("incident");
  const [report, transparencyPayload, transparencyModule] = await Promise.all([
    api(dailySafetyReportPath("child-demo")),
    api("/children/child-demo/transparency"),
    import("./stage4-transparency.js"),
  ]);
  const transparencyMarkup = transparencyModule.renderChildTransparency(
    transparencyPayload,
    {
      locale: document.documentElement.lang || "pt-BR",
      timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    },
  );
  let warning = "";
  if (incidentId) {
    const [incident, experience] = await Promise.all([
      api(`/incidents/${encodeURIComponent(incidentId)}`),
      api(`/incidents/${encodeURIComponent(incidentId)}/experience`),
    ]);
    const contestationSent = experience.timeline.some(
      (event) => event.kind === "contestation_submitted",
    );
    warning = `
      <section class="card child-warning" role="alert">
        <div class="warning-heading">
          <span class="warning-icon" aria-hidden="true">!</span>
          <div><p class="eyebrow">AVISO DE SEGURANÇA</p><h2>${escapeHtml(applicationName(incident.application))} foi temporariamente bloqueado.</h2></div>
        </div>
        <p>${escapeHtml(explanationFor(incident))} Não compartilhe escola, endereço, fotos privadas ou outros dados pessoais com quem você não conhece.</p>
        ${
          contestationSent
            ? `<p role="status"><strong>Sua explicação foi enviada.</strong> O texto fica restrito ao processo de revisão e não aparece nesta tela.</p>`
            : ["BLOCKED", "UNLOCK_REQUESTED"].includes(incident.status)
              ? `
          <form class="request-form" id="unlock-form">
            <label for="explanation">Explique a situação ao seu responsável</label>
            <textarea id="explanation" minlength="3" maxlength="280" required placeholder="Ex.: Conheço essa pessoa da escola."></textarea>
            <button class="button secondary" type="submit">Solicitar revisão</button>
          </form>`
              : `<p><strong>${escapeHtml(labels[incident.status] || incident.status)}</strong></p>`
        }
      </section>`;
  }
  app.innerHTML = `
    ${warning}
    <div class="section-heading"><h2>Seu dia digital</h2></div>
    <div class="grid metrics">
      <div class="card metric" data-tone="calm"><span class="metric-label">Alertas de segurança</span><strong class="metric-value">${safetyMetric(report, "guardian_alerts")}</strong><span class="metric-detail">Alertas enviados para ajudar em uma situação</span></div>
      <div class="card metric" data-tone="attention"><span class="metric-label">Intervenções</span><strong class="metric-value">${safetyMetric(report, "policy_interventions")}</strong><span class="metric-detail">Ações previstas nas regras da família</span></div>
      <div class="card metric" data-tone="info"><span class="metric-label">Contestações</span><strong class="metric-value">${safetyMetric(report, "contestations")}</strong><span class="metric-detail">Pedidos de revisão registrados</span></div>
    </div>
    <div class="grid two">
      <section>
        <div class="section-heading"><h2>Dados recebidos</h2></div>
        <div class="card card-pad">
          <p class="lead">${report.data_status === "AVAILABLE" ? `Sessões do observer recebidas de ${report.device_ids.length} dispositivo(s).` : report.data_status === "SYNC_PENDING" ? "Há um dispositivo offline com sincronização pendente." : "Nenhuma sessão real do observer foi recebida nesta data."}</p>
          ${report.offline_sync_received ? `<p>Uma sessão capturada offline foi sincronizada sem duplicar os totais.</p>` : ""}
        </div>
      </section>
      <section>${transparencyMarkup}</section>
    </div>`;
  document
    .querySelector("#unlock-form")
    ?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const explanation = document.querySelector("#explanation").value.trim();
      await api(`/incidents/${encodeURIComponent(incidentId)}/contestations`, {
        method: "POST",
        body: JSON.stringify({
          contestation_id: `contestation-${Date.now()}`,
          reason: explanation,
        }),
      });
      notify("Sua explicação foi enviada ao responsável.");
      await childPage();
    });
}

async function onboardingPage() {
  setPage("Configurar família", "COMECE COM TRANSPARÊNCIA", "onboarding");
  const notice = await api("/onboarding/privacy-notice");
  if (!onboardingState.familyId) {
    app.innerHTML = `
      <div class="onboarding-layout">
        <section class="card card-pad onboarding-card">
          <p class="eyebrow">ETAPA 1 DE 4</p>
          <h2>Crie o espaço da sua família</h2>
          <p class="lead">Nesta prévia local, os dados ficam neste computador. Autenticação e isolamento entre famílias continuam planejados.</p>
          <form id="family-form" class="form-stack">
            <label for="family-email">E-mail do responsável</label>
            <input id="family-email" name="email" type="email" autocomplete="email" required placeholder="nome@exemplo.com" />
            <label for="family-name">Nome da família</label>
            <input id="family-name" name="familyName" maxlength="120" required placeholder="Família Silva" />
            <button class="button primary" type="submit">Criar família</button>
          </form>
        </section>
        <aside class="card card-pad privacy-note">
          <p class="eyebrow">AVISO ${escapeHtml(notice.version)}</p>
          <h2>Coleta mínima desde o início</h2>
          <p>Usamos nome de exibição, faixa etária, saúde técnica do Mac e evidência mínima quando uma política é acionada.</p>
          <p>Não coletamos data de nascimento exata, tela ao vivo contínua, câmera ou microfone.</p>
          <p>A retenção declarada nesta prévia é de ${notice.retention_days.incident_evidence} dias. A exclusão automática depende da camada de dados segura da Etapa 2.</p>
        </aside>
      </div>`;
    document
      .querySelector("#family-form")
      .addEventListener("submit", async (event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        const family = await api("/onboarding/families", {
          method: "POST",
          body: JSON.stringify({
            email: data.get("email"),
            family_name: data.get("familyName"),
          }),
        });
        onboardingState.familyId = family.family_id;
        notify("Família criada nesta prévia local.");
        await onboardingPage();
      });
    return;
  }

  if (!onboardingState.childId) {
    app.innerHTML = `
      <section class="card card-pad onboarding-card narrow">
        <p class="eyebrow">ETAPA 2 DE 4</p>
        <h2>Adicione uma criança</h2>
        <p class="lead">A faixa etária é suficiente para ajustar linguagem e políticas. Não pedimos a data de nascimento.</p>
        <form id="child-form" class="form-stack">
          <label for="child-name">Nome de exibição</label>
          <input id="child-name" name="displayName" maxlength="80" required />
          <label for="age-band">Faixa etária</label>
          <select id="age-band" name="ageBand" required>
            <option value="6_TO_9">6 a 9 anos</option>
            <option value="10_TO_12">10 a 12 anos</option>
            <option value="13_TO_17">13 a 17 anos</option>
          </select>
          <label class="consent-row"><input name="consent" type="checkbox" required /> <span>Li o aviso ${escapeHtml(notice.version)} e aceito a coleta mínima descrita.</span></label>
          <button class="button primary" type="submit">Adicionar criança</button>
        </form>
      </section>`;
    document
      .querySelector("#child-form")
      .addEventListener("submit", async (event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        await api(
          `/onboarding/families/${encodeURIComponent(onboardingState.familyId)}/privacy-consent`,
          {
            method: "POST",
            body: JSON.stringify({ notice_version: notice.version }),
          },
        );
        const child = await api(
          `/onboarding/families/${encodeURIComponent(onboardingState.familyId)}/children`,
          {
            method: "POST",
            body: JSON.stringify({
              display_name: data.get("displayName"),
              age_band: data.get("ageBand"),
              requested_block_categories: [],
            }),
          },
        );
        onboardingState.childId = child.child_id;
        notify("Criança adicionada com políticas conservadoras.");
        await onboardingPage();
      });
    return;
  }

  if (!onboardingState.pairing) {
    app.innerHTML = `
      <section class="card card-pad onboarding-card narrow">
        <p class="eyebrow">ETAPA 3 DE 4</p>
        <h2>Prepare o Mac</h2>
        <p class="lead">O código expira e deve ser usado somente no Mac desta criança. Permissões de gravação de tela e acessibilidade serão verificadas por heartbeat real quando o agente estiver instalado.</p>
        <form id="pairing-form" class="form-stack">
          <label for="device-name">Nome do Mac</label>
          <input id="device-name" name="deviceName" maxlength="120" required placeholder="Mac da Bia" />
          <button class="button primary" type="submit">Gerar código de pareamento</button>
        </form>
      </section>`;
    document
      .querySelector("#pairing-form")
      .addEventListener("submit", async (event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        onboardingState.pairing = await api(
          `/onboarding/families/${encodeURIComponent(onboardingState.familyId)}/children/${encodeURIComponent(onboardingState.childId)}/pairing`,
          {
            method: "POST",
            body: JSON.stringify({ device_name: data.get("deviceName") }),
          },
        );
        await onboardingPage();
      });
    return;
  }

  if (!onboardingState.device) {
    app.innerHTML = `
      <section class="card card-pad onboarding-card narrow">
        <p class="eyebrow">ETAPA 4 DE 4</p>
        <h2>Use este código no Mac</h2>
        <p class="pairing-code" aria-label="Código de pareamento">${escapeHtml(onboardingState.pairing.code)}</p>
        <p>O código vence em ${formatDate(onboardingState.pairing.expires_at)}. Nesta prévia, você pode simular o resgate local; isso não ativa observação real.</p>
        <div class="action-bar">
          <button class="button primary" id="redeem-pairing">Simular pareamento local</button>
          <button class="button secondary" id="retry-pairing">Gerar novo código</button>
        </div>
      </section>`;
    document
      .querySelector("#redeem-pairing")
      .addEventListener("click", async () => {
        onboardingState.device = await api("/onboarding/pairing/redeem", {
          method: "POST",
          body: JSON.stringify({ code: onboardingState.pairing.code }),
        });
        await onboardingPage();
      });
    document
      .querySelector("#retry-pairing")
      .addEventListener("click", async () => {
        onboardingState.pairing = await api(
          `/onboarding/pairing/${encodeURIComponent(onboardingState.pairing.pairing_id)}/retry`,
          { method: "POST" },
        );
        await onboardingPage();
      });
    return;
  }

  const protection = await api(
    `/onboarding/devices/${encodeURIComponent(onboardingState.device.device_id)}/protection`,
  );
  app.innerHTML = `
    <section class="card card-pad onboarding-card narrow">
      <p class="eyebrow">PRÉVIA LOCAL CONCLUÍDA</p>
      <h2>O Mac ainda não está protegido</h2>
      <p class="lead">Estado atual: ${escapeHtml(protection.status)}. O Guardian só mostrará “Protegido” após receber heartbeat recente do agente e confirmar todas as permissões obrigatórias.</p>
      <p>A conta, a família e o dispositivo desta prévia ficam somente na memória. Persistência e autenticação serão conectadas pela Etapa 2.</p>
      <a class="button secondary" href="/">Voltar à demonstração</a>
    </section>`;
}

async function familyPage() {
  setPage("Família e dispositivos", "ESCOPO DA FAMÍLIA", "family");
  const children = await api("/family/scope");
  const childCards = children
    .map(
      (child) => `
        <article class="card card-pad family-child">
          <div class="profile-strip compact">
            <div class="avatar">${escapeHtml(child.display_name.slice(0, 1).toUpperCase())}</div>
            <div class="profile-copy"><h2>${escapeHtml(child.display_name)}</h2><p>${child.devices.length} Mac(s) associado(s)</p></div>
          </div>
          <div class="device-list">
            ${child.devices.length ? child.devices.map((device) => `<div class="device-row"><div><strong>${escapeHtml(device.display_name)}</strong><span>${escapeHtml(device.device_id)}</span></div><span class="status detected">Status depende do heartbeat</span></div>`).join("") : `<p class="lead">Nenhum Mac associado.</p>`}
          </div>
        </article>`,
    )
    .join("");
  app.innerHTML = `
    <div class="section-heading"><h2>Crianças e Macs</h2><a href="/onboarding">Abrir prévia local de onboarding</a></div>
    <div class="family-grid">${childCards || `<div class="card card-pad"><p class="lead">Nenhuma criança cadastrada nesta família.</p><a class="button primary" href="/onboarding">Adicionar criança</a></div>`}</div>
    <p class="capability-note">Prévia local: o scoping é exercitado pelo adapter R4. Autenticação e isolamento persistente entre famílias dependem da Etapa 2.</p>`;
}

async function supportPage() {
  setPage("Suporte e feedback", "AJUDA COM COLETA MÍNIMA", "support");
  const incidentId = new URLSearchParams(location.search).get("incident");
  app.innerHTML = `
    <section class="card card-pad onboarding-card narrow">
      <p class="eyebrow">SUPORTE</p>
      <h2>Conte o que precisa ser revisto</h2>
      <p class="lead">Não inclua conversas, capturas de tela, senhas ou outros dados pessoais. Evidência só será solicitada com consentimento separado.</p>
      <form id="support-form" class="form-stack">
        <label for="support-kind">Tipo de pedido</label>
        <select id="support-kind" name="kind"><option value="MISCLASSIFICATION" ${incidentId ? "selected" : ""}>Classificação incorreta</option><option value="SUPPORT" ${incidentId ? "" : "selected"}>Suporte técnico</option><option value="FEEDBACK">Feedback</option></select>
        <label for="support-summary">Resumo</label>
        <textarea id="support-summary" name="summary" minlength="10" maxlength="500" required></textarea>
        <button class="button primary" type="submit">Enviar pedido</button>
        <p class="form-note">${incidentId ? "Somente o identificador e a versão do classificador serão vinculados; a conversa e as evidências não serão enviadas." : "Nenhum conteúdo ou evidência será anexado automaticamente."} Nesta prévia, o caso fica somente na memória local. Encaminhamento e auditoria persistente dependem da Etapa 2.</p>
      </form>
    </section>`;
  document
    .querySelector("#support-form")
    .addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = new FormData(event.currentTarget);
      const supportCase = await api("/family/support-cases", {
        method: "POST",
        body: JSON.stringify({
          kind: data.get("kind"),
          summary: data.get("summary"),
          child_id: "child-demo",
          incident_id: incidentId,
          evidence_ids: [],
          evidence_consent: false,
        }),
      });
      app.innerHTML = `
        <section class="card card-pad onboarding-card narrow" role="status">
          <p class="eyebrow">PEDIDO RECEBIDO</p>
          <h2>Guarde o número do caso</h2>
          <p class="pairing-code case-id">${escapeHtml(supportCase.case_id)}</p>
          <p>Status: ${escapeHtml(supportCase.status)}. Nenhuma evidência foi anexada.</p>
          <button class="button secondary" id="new-support-case">Enviar outro pedido</button>
        </section>`;
      document
        .querySelector("#new-support-case")
        .addEventListener("click", supportPage);
    });
}

async function settingsPage() {
  setPage("Políticas de proteção", "REGRAS DA FAMÍLIA", "settings");
  const [rules, familySettings] = await Promise.all([
    api("/children/child-demo/policy"),
    api("/family/settings"),
  ]);
  const channels = new Set(familySettings.notification_channels);
  app.innerHTML = `
    <div class="info-banner" role="note">
      <span class="info-icon" aria-hidden="true">i</span>
      <div><strong>Como as regras são aplicadas</strong><p>A análise indica a categoria; a regra salva abaixo define a ação no dispositivo.</p></div>
    </div>
    <div class="card card-pad">
      <p class="lead">Escolha o que deve acontecer quando um incidente é associado a cada categoria.</p>
      <div class="section-heading"><h2>Categorias</h2></div>
      <form id="policy-form">
        <div class="policy-list">${rules
          .map(
            (rule) => `
          <label class="policy-row">
            <span><strong>${escapeHtml(labels[rule.category] || rule.category)}</strong><span>${escapeHtml(policyDescriptions[rule.category] || "Regra personalizada")}</span></span>
            <select data-category="${escapeHtml(rule.category)}" aria-label="Ação para ${escapeHtml(labels[rule.category] || rule.category)}">
              <option value="ALLOW" ${rule.action === "ALLOW" ? "selected" : ""}>Permitir</option>
              <option value="ALERT" ${rule.action === "ALERT" ? "selected" : ""}>Somente alertar</option>
              <option value="BLOCK" ${rule.action === "BLOCK" ? "selected" : ""} disabled>Bloquear — requer gate aprovado</option>
            </select>
          </label>`,
          )
          .join("")}</div>
        <div class="action-bar"><button class="button primary" type="submit">Salvar políticas</button></div>
        <p class="form-note">Novos bloqueios permanecem indisponíveis até que uma categoria tenha gate de release explícito. Alertas e permissões continuam editáveis.</p>
      </form>
    </div>
    <div class="grid two settings-grid">
      <section class="card card-pad">
        <p class="eyebrow">RETENÇÃO</p>
        <h2>Defina por quanto tempo manter dados</h2>
        <p class="lead">Reduções valem para novos dados e colocam registros já vencidos na fila de exclusão da camada R2.</p>
        <form id="retention-form" class="form-stack compact-form">
          <label for="retention-evidence">Evidência mínima (1–30 dias)</label>
          <input id="retention-evidence" name="evidence" type="number" min="1" max="30" value="${familySettings.retention_days.evidence}" required />
          <label for="retention-incidents">Metadados de incidente (7–90 dias)</label>
          <input id="retention-incidents" name="incident_metadata" type="number" min="7" max="90" value="${familySettings.retention_days.incident_metadata}" required />
          <label for="retention-support">Mensagens de suporte (7–90 dias)</label>
          <input id="retention-support" name="support_message" type="number" min="7" max="90" value="${familySettings.retention_days.support_message}" required />
          <button class="button primary" type="submit">Salvar retenção</button>
        </form>
      </section>
      <section class="card card-pad">
        <p class="eyebrow">NOTIFICAÇÕES</p>
        <h2>Escolha onde receber avisos</h2>
        <p class="lead">As mensagens externas nunca incluem conteúdo sensível. O canal no app permanece como fallback seguro.</p>
        <form id="notifications-form" class="form-stack compact-form">
          <label class="consent-row"><input type="checkbox" checked disabled /><span>No app — sempre disponível</span></label>
          <label class="consent-row"><input name="channel" type="checkbox" value="email" ${channels.has("email") ? "checked" : ""} /><span>E-mail — opt-in</span></label>
          <label class="consent-row"><input name="channel" type="checkbox" value="push" ${channels.has("push") ? "checked" : ""} /><span>Push — opt-in</span></label>
          <button class="button primary" type="submit">Salvar canais</button>
        </form>
      </section>
    </div>`;
  document
    .querySelector("#policy-form")
    .addEventListener("submit", async (event) => {
      event.preventDefault();
      const updated = rules.map((rule) => ({
        ...rule,
        action: document.querySelector(`[data-category="${rule.category}"]`)
          .value,
      }));
      await api("/children/child-demo/policy", {
        method: "PUT",
        body: JSON.stringify(updated),
      });
      notify("Políticas atualizadas.");
    });
  document
    .querySelector("#retention-form")
    .addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = new FormData(event.currentTarget);
      await api("/family/settings/retention", {
        method: "PATCH",
        body: JSON.stringify({
          retention_days: {
            evidence: Number(data.get("evidence")),
            incident_metadata: Number(data.get("incident_metadata")),
            support_message: Number(data.get("support_message")),
          },
        }),
      });
      notify("Retenção atualizada para novos dados.");
    });
  document
    .querySelector("#notifications-form")
    .addEventListener("submit", async (event) => {
      event.preventDefault();
      const selected = [
        "in_app",
        ...new FormData(event.currentTarget).getAll("channel"),
      ];
      await api("/family/settings/notification-channels", {
        method: "PATCH",
        body: JSON.stringify({ channels: selected }),
      });
      notify("Canais de notificação atualizados.");
    });
}

async function route() {
  const [capabilities, transparency, transparencyModule] = await Promise.all([
    api("/capabilities"),
    api("/children/child-demo/transparency"),
    import("./stage4-transparency.js"),
  ]);
  productCapabilities = capabilities;
  updateCapabilityStatus(
    productCapabilities,
    transparencyModule.deriveProtectionStatus(
      transparency.capabilities,
      transparency.heartbeat,
    ),
  );
  const path = location.pathname;
  if (path.startsWith("/incidents/"))
    return incidentDetail(decodeURIComponent(path.split("/").pop()));
  if (path === "/onboarding") return onboardingPage();
  if (path === "/family") return familyPage();
  if (path === "/support") return supportPage();
  if (path === "/child") return childPage();
  if (path === "/settings") return settingsPage();
  return dashboard();
}

function renderError(error) {
  console.error(error);
  app.innerHTML = `
    <div class="error-card" role="alert">
      <span class="error-icon" aria-hidden="true">!</span>
      <div><h2>Não foi possível carregar esta tela</h2><p>O serviço do Guardian não respondeu. Tente novamente em instantes.</p></div>
      <button class="button secondary" id="retry-page" type="button">Tentar novamente</button>
    </div>`;
  document.querySelector("#retry-page")?.addEventListener("click", () => {
    app.innerHTML = `<div class="loading-card"><span class="spinner" aria-hidden="true"></span> Carregando proteção…</div>`;
    route().catch(renderError);
  });
}

route().catch(renderError);
