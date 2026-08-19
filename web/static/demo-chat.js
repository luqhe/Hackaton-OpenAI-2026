const totalRequests = 4;
let revealedRequests = 0;

const chatThread = document.querySelector("#chat-thread");
const messageTemplate = document.querySelector("#risk-messages");
const revealButton = document.querySelector("#reveal-next");
const resetButton = document.querySelector("#reset-demo");
const requestCount = document.querySelector("#request-count");
const captureState = document.querySelector("#capture-state");
const presenterCopy = document.querySelector("#presenter-copy");
const fullscreenButton = document.querySelector("#toggle-fullscreen");

function updateDemoState() {
  const isComplete = revealedRequests === totalRequests;
  requestCount.textContent = `${revealedRequests} de ${totalRequests} pedidos`;
  revealButton.disabled = isComplete;
  revealButton.innerHTML = isComplete
    ? "Sequência completa"
    : `Revelar pedido ${revealedRequests + 1} <span aria-hidden="true">→</span>`;

  document.querySelectorAll("[data-progress]").forEach((item) => {
    item.classList.toggle(
      "is-visible",
      Number(item.dataset.progress) <= revealedRequests,
    );
  });

  if (isComplete) {
    captureState.classList.add("is-complete");
    captureState.querySelector("h2").textContent = "Risco completo";
    captureState.querySelector("p").textContent = "Pronto para captura";
    presenterCopy.textContent =
      "Os quatro pedidos de informação pessoal estão visíveis. A cena está pronta para o fluxo local do Guardian.";
  } else if (revealedRequests > 0) {
    captureState.classList.remove("is-complete");
    captureState.querySelector("h2").textContent =
      `Pedido ${revealedRequests} revelado`;
    captureState.querySelector("p").textContent = "Continue a progressão";
    presenterCopy.textContent =
      "O pedido novo fica marcado na conversa. Avance até os quatro sinais estarem visíveis.";
  } else {
    captureState.classList.remove("is-complete");
    captureState.querySelector("h2").textContent = "Cena segura";
    captureState.querySelector("p").textContent = "Pronta para captura";
    presenterCopy.textContent =
      "A conversa começa sem sinais de risco. Revele os pedidos um por vez para mostrar a progressão.";
  }
}

function revealNextRequest() {
  if (revealedRequests >= totalRequests) return;

  revealedRequests += 1;
  const message = messageTemplate.content
    .querySelector(`[data-step="${revealedRequests}"]`)
    .cloneNode(true);
  chatThread.append(message);
  updateDemoState();
  message.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function resetDemo() {
  revealedRequests = 0;
  document
    .querySelectorAll(".risk-message")
    .forEach((message) => message.remove());
  updateDemoState();
  chatThread.scrollTo({ top: 0, behavior: "smooth" });
  revealButton.focus();
}

async function toggleFullscreen() {
  try {
    if (document.fullscreenElement) {
      await document.exitFullscreen();
    } else {
      await document.documentElement.requestFullscreen();
    }
  } catch {
    fullscreenButton.textContent = "Tela cheia indisponível";
  }
}

revealButton.addEventListener("click", revealNextRequest);
resetButton.addEventListener("click", resetDemo);
fullscreenButton.addEventListener("click", toggleFullscreen);

document.addEventListener("fullscreenchange", () => {
  fullscreenButton.innerHTML = document.fullscreenElement
    ? '<span aria-hidden="true">×</span> Sair da tela cheia'
    : '<span aria-hidden="true">⛶</span> Tela cheia';
});

document.addEventListener("keydown", (event) => {
  if (
    event.ctrlKey ||
    event.metaKey ||
    event.altKey ||
    event.target.closest("button")
  )
    return;

  if (event.key === "ArrowRight" || event.code === "Space") {
    event.preventDefault();
    revealNextRequest();
  } else if (event.key.toLowerCase() === "r") {
    resetDemo();
  } else if (event.key.toLowerCase() === "f") {
    toggleFullscreen();
  }
});

updateDemoState();
