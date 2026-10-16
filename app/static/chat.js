"use strict";
const form = document.getElementById("chat-form");
const chatHistory = document.getElementById("chat-history");
const messageList = document.getElementById("chat-messages");
const emptyState = document.getElementById("chat-empty");
const statusLabel = document.getElementById("chat-status");
const questionInput = form.elements.pergunta;
const sendButton = form.querySelector('button[type="submit"]');
const clearButton = document.getElementById("clear-chat");
const storageKey = `training-chat-${form.dataset.userId}-${form.dataset.trainingId}`;
let messages = [];
let busy = false;
try {
  const saved = JSON.parse(sessionStorage.getItem(storageKey) || "[]");
  if (Array.isArray(saved)) messages = saved.filter(item =>
    item && ["user", "assistant"].includes(item.role) && typeof item.text === "string"
  ).slice(-20);
} catch { /* Armazenamento indisponível: histórico permanece apenas na página. */ }

function persist() {
  messages = messages.slice(-20);
  try { sessionStorage.setItem(storageKey, JSON.stringify(messages)); } catch { /* Sem persistência. */ }
}

function render() {
  messageList.replaceChildren();
  emptyState.hidden = messages.length > 0;
  for (const message of messages) {
    const article = document.createElement("article");
    article.className = `chat-message chat-message-${message.role}`;
    const author = document.createElement("span");
    author.className = "message-author";
    author.textContent = message.role === "user" ? "Você" : "Assistente";
    const text = document.createElement("p");
    text.className = "message-text training-content";
    text.textContent = message.text;
    article.append(author, text);
    for (const source of Array.isArray(message.sources) ? message.sources : []) {
      if (!source || typeof source !== "object") continue;
      const details = document.createElement("details");
      details.className = "chat-source";
      const summary = document.createElement("summary");
      summary.textContent = `[${source.id}] ${source.documento}${source.pagina ? ` · Página ${source.pagina}` : ` · ${source.secao || "Seção"}`}`;
      const quote = document.createElement("p");
      quote.className = "training-content";
      quote.textContent = source.trecho;
      details.append(summary, quote);
      article.append(details);
    }
    messageList.append(article);
  }
  chatHistory.scrollTop = chatHistory.scrollHeight;
}

function updateComposer() {
  questionInput.style.height = "auto";
  questionInput.style.height = `${Math.min(questionInput.scrollHeight, 120)}px`;
  sendButton.disabled = busy || !questionInput.value.trim();
}

form.addEventListener("submit", async event => {
  event.preventDefault();
  const question = questionInput.value.trim();
  if (!question || busy) return;
  busy = true;
  clearButton.disabled = true;
  statusLabel.classList.remove("is-error");
  statusLabel.textContent = "Consultando os materiais…";
  messages.push({role: "user", text: question});
  persist();
  render();
  questionInput.value = "";
  updateComposer();
  try {
    const response = await fetch(`/treinamentos/${form.dataset.trainingId}/perguntar`, {
      method: "POST", headers: {"Content-Type": "application/json", "X-CSRFToken": form.elements.csrfmiddlewaretoken.value}, body: JSON.stringify({pergunta: question})
    });
    if (!response.headers.get("content-type")?.includes("application/json")) {
      throw new Error("Não foi possível consultar os materiais. Atualize a página e confira sua sessão.");
    }
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Não foi possível consultar os documentos.");
    messages.push({role: "assistant", text: data.resposta, sources: data.fontes});
    statusLabel.textContent = "";
    persist();
    render();
  } catch (error) {
    statusLabel.classList.add("is-error");
    statusLabel.textContent = error instanceof TypeError ? "Falha de conexão. Tente novamente." : error.message;
    if (!questionInput.value.trim()) questionInput.value = question;
  } finally {
    busy = false;
    clearButton.disabled = false;
    updateComposer();
    questionInput.focus({preventScroll: true});
  }
});

clearButton.addEventListener("click", () => {
  if (busy) return;
  messages = [];
  statusLabel.textContent = "";
  statusLabel.classList.remove("is-error");
  persist();
  render();
});
document.querySelectorAll("[data-question]").forEach(button => {
  button.addEventListener("click", () => {
    questionInput.value = button.dataset.question;
    updateComposer();
    questionInput.focus({preventScroll: true});
  });
});
questionInput.addEventListener("input", updateComposer);
questionInput.addEventListener("keydown", event => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    if (!sendButton.disabled) form.requestSubmit();
  }
});
render();
updateComposer();
