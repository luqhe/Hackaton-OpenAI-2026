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

const icons = {
  alert: `<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M12 3.5 21 20H3L12 3.5Z"/><path d="M12 9v5M12 17.5h.01"/></svg>`,
  check: `<svg aria-hidden="true" viewBox="0 0 24 24"><path d="m5 12.5 4.2 4.2L19 7"/></svg>`,
};

const incidentExplanations = {
  DANGEROUS_CONTACT:
    "A conversa pede progressivamente idade, escola, perfil social, fotos ou localização. Em conjunto, esses sinais podem indicar uma tentativa insegura de obter informações pessoais.",
};

const evidenceTerms = {
  age: "idade",
  school: "escola",
  social: "perfil social",
  photo: "foto",
  location: "localização",
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function incidentExplanation(incident) {
  return incidentExplanations[incident.category] || incident.explanation;
}

function formatEvidence(value) {
  const prefix = "Progressive request detected:";
  if (!value.startsWith(prefix)) return value;
  const term = value.slice(prefix.length).trim();
  return `Pedido progressivo identificado: ${evidenceTerms[term] || term}`;
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
    link.classList.toggle("active", link.dataset.route === route);
  });
}

function updateCapabilityStatus(capabilities) {
  const observationActive = capabilities.real_screen_observation;
  protectionStatus.classList.toggle("demo", !observationActive);
  protectionLabel.textContent = observationActive
    ? "Proteção ativa"
    : "Demonstração local";
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
      <span class="risk-icon">${icons.alert}</span>
      <div>
        <strong>${escapeHtml(labels[incident.category] || incident.category)}</strong>
        <p>${escapeHtml(incident.application)} · ${formatDate(incident.occurred_at)}</p>
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
    : `<div class="empty"><div class="empty-mark">${icons.check}</div><h3>Nenhum incidente hoje</h3><p>${productCapabilities.real_screen_observation ? "O Guardian continuará analisando mudanças relevantes sem armazenar continuamente a tela." : "Execute uma fixture controlada para demonstrar a análise contextual local."}</p></div>`;
  const deviceStatus = productCapabilities.real_screen_observation
    ? `<strong>● Protegido</strong><span>Observação real ativa</span>`
    : `<strong>◌ Modo de demonstração</strong><span>Entrada por fixtures controladas</span>`;
  const observationLabel = productCapabilities.real_screen_observation
    ? "Mudanças analisadas"
    : "Observações da demo";
  app.innerHTML = `
    <div class="profile-strip context-panel">
      <div class="avatar">L</div>
      <div class="profile-copy"><h2>Lucas</h2><p>${escapeHtml(device.name)} · ${escapeHtml(device.platform)}</p></div>
      <div class="device-state">${deviceStatus}</div>
    </div>
    <div class="protection-layout">
      <div>
        <div class="section-heading section-heading-primary"><div><p class="section-kicker">Prioridade</p><h2>Atividade de proteção</h2></div><a href="/child">Relatório diário →</a></div>
        <div class="surface incident-list">${latest}</div>
      </div>
      <div>
        <div class="section-heading"><h2>Como o Guardian decide</h2></div>
        <div class="insight">
          <p class="eyebrow">CONTEXTO, NÃO PALAVRAS ISOLADAS</p>
          <h2>Arquitetura preparada para entender contexto.</h2>
          <p>Demo atual: fixture + texto + histórico recente + política familiar. Captura e OCR reais são a próxima etapa.</p>
          <div class="signal-row" aria-label="Quatro sinais contextuais ativos"><span class="on"></span><span class="on"></span><span class="on"></span><span></span></div>
        </div>
      </div>
    </div>
    <div class="section-heading summary-heading"><div><p class="section-kicker">Resumo</p><h2>Hoje</h2></div></div>
    <div class="summary-panel">
      <div class="metric"><span class="metric-label">Tempo de tela</span><strong class="metric-value">${formatDuration(report.total_seconds)}</strong><span class="metric-detail">Uso agregado no dispositivo</span></div>
      <div class="metric"><span class="metric-label">Incidentes de segurança</span><strong class="metric-value">${report.incident_count}</strong><span class="metric-detail">${report.interventions} intervenções realizadas</span></div>
      <div class="metric"><span class="metric-label">${observationLabel}</span><strong class="metric-value">${report.screen_changes}</strong><span class="metric-detail">Fixtures e telemetria local do MVP</span></div>
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
      <p class="lead">${escapeHtml(incidentExplanation(incident))}</p>
      <div class="facts">
        <div class="fact"><span>Aplicativo</span><strong>${escapeHtml(incident.application)}</strong></div>
        <div class="fact"><span>Direção</span><strong>${incident.direction === "CHILD_AS_TARGET" ? "Lucas como alvo" : escapeHtml(incident.direction)}</strong></div>
        <div class="fact"><span>Confiança</span><strong>${Math.round(incident.confidence * 100)}%</strong></div>
        <div class="fact"><span>Horário</span><strong>${formatDate(incident.occurred_at)}</strong></div>
      </div>
    </article>
    <div class="grid two">
      <section>
        <div class="section-heading"><h2>Sinais relevantes</h2></div>
        <div class="card card-pad">
          <ul class="evidence-list">${incident.evidence.map((item) => `<li>${escapeHtml(formatEvidence(item))}</li>`).join("")}</ul>
        </div>
        ${incident.screenshot_urls.length ? `<div class="section-heading"><h2>Evidência selecionada</h2></div><div class="card card-pad">${incident.screenshot_urls.map((url, index) => `<iframe class="evidence-frame" src="${escapeHtml(url)}" title="Evidência ${index + 1}" sandbox></iframe>`).join("")}</div>` : ""}
      </section>
      <aside class="decision-aside">
        <div class="section-heading"><h2>Decisão da família</h2></div>
        <div class="card card-pad">
          ${incident.child_explanation ? `<p class="eyebrow">EXPLICAÇÃO DE LUCAS</p><p>${escapeHtml(incident.child_explanation)}</p>` : `<p class="lead">Lucas ainda não enviou uma explicação para este bloqueio.</p>`}
          <div class="action-bar">
            <button class="button primary" id="unlock" ${canDecide ? "" : "disabled"}>Desbloquear aplicativo</button>
            <button class="button danger" id="keep" ${canDecide ? "" : "disabled"}>Manter bloqueado</button>
          </div>
        </div>
      </aside>
    </div>`;
  document.querySelector("#unlock")?.addEventListener("click", async () => {
    await api(`/incidents/${encodeURIComponent(id)}/unlock`, {
      method: "POST",
    });
    notify("Comando de desbloqueio enviado ao dispositivo.");
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
      <section class="card child-warning">
        <p class="eyebrow">INTERVENÇÃO DO GUARDIAN</p>
        <h2>${escapeHtml(incident.application)} foi temporariamente bloqueado.</h2>
        <p>${escapeHtml(incidentExplanation(incident))} Não compartilhe escola, endereço, fotos privadas ou outros dados pessoais com quem você não conhece.</p>
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
    <div class="summary-panel">
      <div class="metric"><span class="metric-label">Uso do dispositivo</span><strong class="metric-value">${formatDuration(report.total_seconds)}</strong><span class="metric-detail">Sem julgamento de produtividade</span></div>
      <div class="metric"><span class="metric-label">Incidentes</span><strong class="metric-value">${report.incident_count}</strong><span class="metric-detail">Eventos compartilhados com seu responsável</span></div>
      <div class="metric"><span class="metric-label">Evidências compartilhadas</span><strong class="metric-value">${report.evidence_count}</strong><span class="metric-detail">Somente evidência mínima de incidente</span></div>
    </div>
    <div class="grid two">
      <section>
        <div class="section-heading"><h2>Aplicativos hoje</h2></div>
        <div class="card card-pad">
          <div class="usage-list">${report.apps.length ? report.apps.map((item) => `<div class="usage-row"><strong>${escapeHtml(item.app)}</strong><span class="bar"><span style="width:${Math.round((item.seconds / maxSeconds) * 100)}%"></span></span><span>${formatDuration(item.seconds)}</span></div>`).join("") : `<p class="lead">Nenhuma sessão de uso agregada ainda.</p>`}</div>
        </div>
      </section>
      <section>
        <div class="section-heading"><h2>O que está visível</h2></div>
        <div class="card card-pad privacy-grid">
          <div><h3>Ativo nesta versão</h3><ul class="check-list"><li>Fixtures controladas da demonstração</li><li>Texto fornecido pelas fixtures</li><li class="no">Captura da tela real — planejada</li><li class="no">OCR local — planejado</li><li class="no">Áudio do sistema — não implementado</li><li class="no">Microfone — não coletado</li><li class="no">Câmera — não coletada</li></ul></div>
          <div><h3>Seu responsável pode acessar</h3><ul class="check-list"><li>Incidentes de segurança</li><li>Uso diário por aplicativo</li><li>Evidência mínima</li><li class="no">Tela ao vivo</li><li class="no">Microfone ou câmera</li></ul></div>
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
    <div class="card card-pad">
      <p class="lead">Defina como o Guardian deve agir quando identifica um risco com confiança alta. A classificação nunca controla o dispositivo diretamente; estas regras determinísticas tomam a decisão.</p>
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

route().catch((error) => {
  console.error(error);
  app.innerHTML = `<div class="error-card">${escapeHtml(error.message)} Verifique se a API local está em execução.</div>`;
});
