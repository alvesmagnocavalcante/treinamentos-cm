"use strict";
const form = document.getElementById("chat-form");
const chatHistory = document.getElementById("chat-history");
const messageList = document.getElementById("chat-messages");
const emptyState = document.getElementById("chat-empty");
const statusLabel = document.getElementById("chat-status");
const typingIndicator = document.getElementById("chat-loading");
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

function assistantText(text, sources) {
  const sourceIds = new Set(sources.map(source => String(source.id)));
  return text
    .split(/^[ \t]*(?:#{1,6}[ \t]+)?(?:\*\*)?(?:fontes?|refer[eê]ncias?)(?:\*\*)?[ \t]*(?::|[-–—])/im, 1)[0]
    .replace(/\[(\d+)\]/g, (marker, id) => sourceIds.has(id) ? "" : marker)
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/[ \t]+([.,;:!?])/g, "$1")
    .replace(/[ \t]+\n/g, "\n")
    .trim();
}

function render(showLatestAnswer = false) {
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
    const sources = message.role === "assistant" && Array.isArray(message.sources)
      ? message.sources.filter(source => source && typeof source === "object") : [];
    text.textContent = message.role === "assistant" ? assistantText(message.text, sources) : message.text;
    article.append(author, text);
    messageList.append(article);
  }
  chatHistory.scrollTop = chatHistory.scrollHeight;
  if (showLatestAnswer && messageList.lastElementChild) {
    const top = messageList.lastElementChild.getBoundingClientRect().top;
    chatHistory.scrollTop += top - chatHistory.getBoundingClientRect().top - 16;
  }
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
  statusLabel.textContent = "";
  typingIndicator.hidden = false;
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
    render(true);
  } catch (error) {
    statusLabel.classList.add("is-error");
    statusLabel.textContent = error instanceof TypeError ? "Falha de conexão. Tente novamente." : error.message;
    if (!questionInput.value.trim()) questionInput.value = question;
  } finally {
    typingIndicator.hidden = true;
    busy = false;
    clearButton.disabled = false;
    updateComposer();
    if (window.matchMedia("(hover: hover) and (pointer: fine)").matches) {
      questionInput.focus({preventScroll: true});
    }
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
questionInput.addEventListener("input", updateComposer);
questionInput.addEventListener("keydown", event => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing
      && window.matchMedia("(hover: hover) and (pointer: fine)").matches) {
    event.preventDefault();
    if (!sendButton.disabled) form.requestSubmit();
  }
});
render();
updateComposer();
