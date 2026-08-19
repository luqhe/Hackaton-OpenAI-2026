const app = document.querySelector("#app");
const pageTitle = document.querySelector("#page-title");
const pageEyebrow = document.querySelector("#page-eyebrow");
const toast = document.querySelector("#toast");
const protectionStatus = document.querySelector("#protection-status");
const protectionLabel = protectionStatus.querySelector(".protection-label");
let productCapabilities = null;

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

function updateCapabilityStatus(capabilities) {
  const observationActive = capabilities.real_screen_observation;
  protectionStatus.classList.toggle("simulated", !observationActive);
  protectionLabel.textContent = observationActive
    ? "Proteção ativa"
    : "Dados simulados";
}

function formatDuration(totalSeconds) {
  const seconds = Number(totalSeconds || 0);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return hours ? `${hours}h ${minutes}min` : `${minutes}min`;
}

function formatDate(value) {
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
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
    api("/daily-report"),
    api("/devices/device-demo"),
  ]);
  const latest = incidents.length
    ? incidents.slice(0, 5).map(incidentRow).join("")
    : `<div class="empty"><div class="empty-mark">✓</div><h3>Nenhum incidente hoje</h3><p>${productCapabilities.real_screen_observation ? "Nenhum evento de risco foi identificado até agora." : "Nenhum incidente foi registrado nesta simulação."}</p></div>`;
  const deviceStatus = productCapabilities.real_screen_observation
    ? `<strong>● Protegido</strong><span>Análise no dispositivo ativa</span>`
    : `<strong>◌ Dados simulados</strong><span>Nenhuma tela real está sendo observada</span>`;
  const observationLabel = productCapabilities.real_screen_observation
    ? "Mudanças analisadas"
    : "Eventos analisados";
  const observationDetail = productCapabilities.real_screen_observation
    ? "Mudanças relevantes processadas no dispositivo"
    : "Dados recebidos nesta sessão";
  const interventionDetail =
    report.interventions === 1
      ? "1 intervenção realizada"
      : `${report.interventions} intervenções realizadas`;
  app.innerHTML = `
    <div class="card profile-strip">
      <div class="avatar">L</div>
      <div class="profile-copy"><h2>Lucas</h2><p>${escapeHtml(device.name)} · ${escapeHtml(device.platform)}</p></div>
      <div class="device-state">${deviceStatus}</div>
    </div>
    <div class="section-heading"><h2>Hoje</h2><span></span></div>
    <div class="grid metrics">
      <div class="card metric" data-tone="calm"><span class="metric-label">Tempo de tela</span><strong class="metric-value">${formatDuration(report.total_seconds)}</strong><span class="metric-detail">Uso agregado no dispositivo</span></div>
      <div class="card metric" data-tone="attention"><span class="metric-label">Incidentes de segurança</span><strong class="metric-value">${report.incident_count}</strong><span class="metric-detail">${interventionDetail}</span></div>
      <div class="card metric" data-tone="info"><span class="metric-label">${observationLabel}</span><strong class="metric-value">${report.screen_changes}</strong><span class="metric-detail">${observationDetail}</span></div>
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
        </div>
      </div>
    </div>`;
}

async function incidentDetail(id) {
  setPage("Revisar incidente", "SEGURANÇA DE LUCAS", "dashboard");
  const incident = await api(`/incidents/${encodeURIComponent(id)}`);
  const canDecide = ["BLOCKED", "UNLOCK_REQUESTED"].includes(incident.status);
  app.innerHTML = `
    <a class="detail-back" href="/">← Voltar para a visão geral</a>
    <article class="card incident-hero">
      <div class="hero-line">
        <div><p class="eyebrow">INCIDENTE DE ALTA PRIORIDADE</p><h2>${escapeHtml(labels[incident.category] || incident.category)}</h2></div>
        <span class="status ${incident.status.toLowerCase()}">${escapeHtml(labels[incident.status] || incident.status)}</span>
      </div>
      <p class="lead">${escapeHtml(explanationFor(incident))}</p>
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
      </section>
      <aside class="decision-column">
        <div class="section-heading"><h2>Decisão da família</h2></div>
        <div class="card card-pad decision-panel" role="region" aria-label="Decisão da família">
          ${incident.child_explanation ? `<p class="eyebrow">EXPLICAÇÃO DE LUCAS</p><p>${escapeHtml(incident.child_explanation)}</p>` : `<p class="lead">Lucas ainda não enviou uma explicação para este bloqueio.</p>`}
          <p class="decision-hint">Revise os sinais antes de enviar uma decisão ao dispositivo.</p>
          <div class="action-bar">
            <button class="button secondary" id="unlock" ${canDecide ? "" : "disabled"}>Desbloquear aplicativo</button>
            <button class="button danger-solid" id="keep" ${canDecide ? "" : "disabled"}>Manter bloqueado</button>
          </div>
        </div>
      </aside>
      ${incident.screenshot_urls.length ? `<section class="evidence-panel"><div class="section-heading"><h2>Evidência selecionada</h2><span>Evidência mínima</span></div><div class="card card-pad">${incident.screenshot_urls.map((url, index) => `<iframe class="evidence-frame" src="${escapeHtml(url)}" title="Evidência ${index + 1}" loading="lazy" sandbox></iframe>`).join("")}</div></section>` : ""}
    </div>`;
  document.querySelector("#unlock")?.addEventListener("click", async () => {
    await api(`/incidents/${encodeURIComponent(id)}/unlock`, {
      method: "POST",
    });
    notify("Solicitação de desbloqueio enviada.");
    await incidentDetail(id);
  });
  document.querySelector("#keep")?.addEventListener("click", async () => {
    await api(`/incidents/${encodeURIComponent(id)}/keep-blocked`, {
      method: "POST",
    });
    notify("O bloqueio foi mantido.");
    await incidentDetail(id);
  });
}

async function childPage() {
  setPage("Lucas", "PROTEÇÃO E TRANSPARÊNCIA", "child");
  const params = new URLSearchParams(location.search);
  const incidentId = params.get("incident");
  const report = await api("/daily-report");
  let warning = "";
  if (incidentId) {
    const incident = await api(`/incidents/${encodeURIComponent(incidentId)}`);
    warning = `
      <section class="card child-warning" role="alert">
        <div class="warning-heading">
          <span class="warning-icon" aria-hidden="true">!</span>
          <div><p class="eyebrow">AVISO DE SEGURANÇA</p><h2>${escapeHtml(applicationName(incident.application))} foi temporariamente bloqueado.</h2></div>
        </div>
        <p>${escapeHtml(explanationFor(incident))} Não compartilhe escola, endereço, fotos privadas ou outros dados pessoais com quem você não conhece.</p>
        ${
          ["BLOCKED", "UNLOCK_REQUESTED"].includes(incident.status)
            ? `
          <form class="request-form" id="unlock-form">
            <label for="explanation">Explique a situação ao seu responsável</label>
            <textarea id="explanation" minlength="3" maxlength="1000" required placeholder="Ex.: É um amigo da minha escola.">${escapeHtml(incident.child_explanation || "")}</textarea>
            <button class="button secondary" type="submit">Solicitar revisão</button>
          </form>`
            : `<p><strong>${escapeHtml(labels[incident.status] || incident.status)}</strong></p>`
        }
      </section>`;
  }
  const maxSeconds = Math.max(...report.apps.map((item) => item.seconds), 1);
  app.innerHTML = `
    ${warning}
    <div class="section-heading"><h2>Seu dia digital</h2></div>
    <div class="grid metrics">
      <div class="card metric" data-tone="calm"><span class="metric-label">Uso do dispositivo</span><strong class="metric-value">${formatDuration(report.total_seconds)}</strong><span class="metric-detail">Tempo total registrado nos aplicativos</span></div>
      <div class="card metric" data-tone="attention"><span class="metric-label">Incidentes</span><strong class="metric-value">${report.incident_count}</strong><span class="metric-detail">Eventos compartilhados com seu responsável</span></div>
      <div class="card metric" data-tone="info"><span class="metric-label">Evidências compartilhadas</span><strong class="metric-value">${report.evidence_count}</strong><span class="metric-detail">Somente evidência mínima de incidente</span></div>
    </div>
    <div class="grid two">
      <section>
        <div class="section-heading"><h2>Aplicativos hoje</h2></div>
        <div class="card card-pad">
          <div class="usage-list">${report.apps.length ? report.apps.map((item) => `<div class="usage-row"><strong>${escapeHtml(applicationName(item.app))}</strong><span class="bar"><span style="width:${Math.round((item.seconds / maxSeconds) * 100)}%"></span></span><span>${formatDuration(item.seconds)}</span></div>`).join("") : `<p class="lead">Nenhuma sessão de uso registrada hoje.</p>`}</div>
        </div>
      </section>
      <section>
        <div class="section-heading"><h2>Dados e privacidade</h2></div>
        <div class="card card-pad privacy-grid">
          <div><h3>Dados usados nesta sessão</h3><ul class="check-list"><li>Mensagens da conversa simulada</li><li>Histórico recente exibido no cenário</li><li class="no">Tela do dispositivo — não acessada</li><li class="no">Texto de outros aplicativos — não acessado</li><li class="no">Áudio do sistema — não acessado</li><li class="no">Microfone — não acessado</li><li class="no">Câmera — não acessada</li></ul></div>
          <div><h3>Seu responsável pode consultar</h3><ul class="check-list"><li>Incidentes de segurança</li><li>Uso diário por aplicativo</li><li>Evidência mínima do incidente</li><li class="no">Conteúdo completo da tela</li><li class="no">Microfone ou câmera</li></ul></div>
        </div>
      </section>
    </div>`;
  document
    .querySelector("#unlock-form")
    ?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const explanation = document.querySelector("#explanation").value.trim();
      await api(`/incidents/${encodeURIComponent(incidentId)}/request-unlock`, {
        method: "POST",
        body: JSON.stringify({ explanation }),
      });
      notify("Sua explicação foi enviada ao responsável.");
      await childPage();
    });
}

async function settingsPage() {
  setPage("Políticas de proteção", "REGRAS DA FAMÍLIA", "settings");
  const rules = await api("/children/child-demo/policy");
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
              <option value="BLOCK" ${rule.action === "BLOCK" ? "selected" : ""}>Bloquear</option>
            </select>
          </label>`,
          )
          .join("")}</div>
        <div class="action-bar"><button class="button primary" type="submit">Salvar políticas</button></div>
      </form>
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
}

async function route() {
  productCapabilities = await api("/capabilities");
  updateCapabilityStatus(productCapabilities);
  const path = location.pathname;
  if (path.startsWith("/incidents/"))
    return incidentDetail(decodeURIComponent(path.split("/").pop()));
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
