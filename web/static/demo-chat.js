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
    ? "Todas as mensagens exibidas"
    : `Mostrar mensagem ${revealedRequests + 1} <span aria-hidden="true">→</span>`;

  document.querySelectorAll("[data-progress]").forEach((item) => {
    item.classList.toggle(
      "is-visible",
      Number(item.dataset.progress) <= revealedRequests,
    );
  });

  if (isComplete) {
    captureState.classList.add("is-complete");
    captureState.querySelector("h2").textContent =
      "Sinais de risco identificados";
    captureState.querySelector("p").textContent = "4 de 4 sinais presentes";
    presenterCopy.textContent =
      "A sequência reúne pedidos de idade, escola, perfil social e foto pessoal.";
  } else if (revealedRequests > 0) {
    captureState.classList.remove("is-complete");
    captureState.querySelector("h2").textContent =
      `Sinal ${revealedRequests} de ${totalRequests}`;
    captureState.querySelector("p").textContent =
      "Pedido de informação pessoal";
    presenterCopy.textContent =
      "O novo pedido fica destacado. Continue para revisar o restante da conversa.";
  } else {
    captureState.classList.remove("is-complete");
    captureState.querySelector("h2").textContent = "Sem sinais de risco";
    captureState.querySelector("p").textContent = "0 de 4 sinais identificados";
    presenterCopy.textContent =
      "Os sinais aparecem conforme a conversa simulada avança.";
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
