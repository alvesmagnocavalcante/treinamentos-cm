"use strict";

(() => {
  const system = window.matchMedia("(prefers-color-scheme: dark)");
  const root = document.documentElement;
  const valid = value => ["light", "dark", "auto"].includes(value) ? value : "auto";
  let preference = "auto";
  try { preference = valid(localStorage.getItem("theme")); } catch { /* Tema funciona sem armazenamento. */ }

  function applyTheme() {
    const dark = preference === "dark" || (preference === "auto" && system.matches);
    root.dataset.theme = dark ? "dark" : "light";
    root.dataset.bsTheme = root.dataset.theme;
    document.querySelectorAll("[data-theme-toggle]").forEach(button => {
      button.hidden = false;
      button.setAttribute("aria-label", dark ? "Ativar modo claro" : "Ativar modo escuro");
      button.setAttribute("aria-pressed", String(dark));
      button.title = dark ? "Ativar modo claro" : "Ativar modo escuro";
      button.querySelector('[data-theme-icon="sun"]').hidden = !dark;
      button.querySelector('[data-theme-icon="moon"]').hidden = dark;
    });
  }

  function bindToggle() {
    document.querySelectorAll("[data-theme-toggle]").forEach(button => {
      button.addEventListener("click", () => {
        preference = root.dataset.theme === "dark" ? "light" : "dark";
        try { localStorage.setItem("theme", preference); } catch { /* Mantém a escolha nesta página. */ }
        applyTheme();
      });
    });
    applyTheme();
  }

  applyTheme();
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bindToggle);
  else bindToggle();
  system.addEventListener("change", () => { if (preference === "auto") applyTheme(); });
  window.addEventListener("storage", event => {
    if (event.key === "theme" || event.key === null) {
      preference = valid(event.newValue);
      applyTheme();
    }
  });
})();
