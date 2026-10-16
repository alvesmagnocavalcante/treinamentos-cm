"use strict";
const driveForm = document.querySelector("[data-drive-form]");
driveForm?.addEventListener("submit", () => {
  driveForm.querySelector("button").disabled = true;
  driveForm.querySelector("[data-drive-status]").textContent = "Importando documentos do Drive e indexando. Aguarde a conclusão.";
});
const uploadForm = document.querySelector("[data-upload-form]");
uploadForm?.addEventListener("submit", () => {
  uploadForm.querySelector("button").disabled = true;
  uploadForm.querySelector("[data-upload-status]").textContent = "Extraindo texto e indexando. Aguarde a conclusão.";
});
document.querySelectorAll("[data-delete-form]").forEach(form => {
  form.addEventListener("submit", event => {
    if (!window.confirm("Excluir este documento e seus trechos do índice?")) event.preventDefault();
  });
});
