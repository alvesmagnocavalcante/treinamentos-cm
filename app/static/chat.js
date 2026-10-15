"use strict";
const form = document.getElementById("chat-form");
const history = document.getElementById("chat-history");
const statusLabel = document.getElementById("chat-status");
const storageKey = `training-chat-${form.dataset.trainingId}`;
let messages = [];
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
  history.replaceChildren();
  for (const message of messages) {
    const article = document.createElement("article");
    article.className = "chat-message border rounded p-3 mb-2";
    const author = document.createElement("strong");
    author.textContent = message.role === "user" ? "Você" : "Assistente";
    const text = document.createElement("p");
    text.className = "training-content mb-0 mt-1";
    text.textContent = message.text;
    article.append(author, text);
    for (const source of Array.isArray(message.sources) ? message.sources : []) {
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = `[${source.id}] ${source.documento}${source.pagina ? ` · Página ${source.pagina}` : ` · ${source.secao || "Seção"}`}`;
      const quote = document.createElement("p");
      quote.className = "training-content small mt-2";
      quote.textContent = source.trecho;
      details.append(summary, quote);
      article.append(details);
    }
    history.append(article);
  }
  history.scrollTop = history.scrollHeight;
}

form.addEventListener("submit", async event => {
  event.preventDefault();
  const question = form.elements.pergunta.value.trim();
  if (!question) return;
  const button = form.querySelector("button");
  button.disabled = true;
  statusLabel.textContent = "Consultando documentos…";
  messages.push({role: "user", text: question});
  persist();
  render();
  form.elements.pergunta.value = "";
  try {
    const response = await fetch(`/treinamentos/${form.dataset.trainingId}/perguntar`, {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({pergunta: question})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Não foi possível consultar os documentos.");
    messages.push({role: "assistant", text: data.resposta, sources: data.fontes});
    statusLabel.textContent = "";
    persist();
    render();
  } catch (error) {
    statusLabel.textContent = error instanceof TypeError ? "Falha de conexão. Tente novamente." : error.message;
  } finally {
    button.disabled = false;
    form.elements.pergunta.focus();
  }
});
document.getElementById("clear-chat").addEventListener("click", () => {
  messages = [];
  persist();
  render();
});
render();
