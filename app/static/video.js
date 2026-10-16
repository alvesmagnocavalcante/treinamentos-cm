"use strict";

(() => {
  const video = document.getElementById("lesson-video");
  if (!video) return;
  const controls = document.getElementById("video-controls");
  const play = document.getElementById("video-play");
  const progress = document.getElementById("video-progress");
  const time = document.getElementById("video-time");
  const mute = document.getElementById("video-mute");
  const fullscreen = document.getElementById("video-fullscreen");
  const error = document.getElementById("video-error");
  const card = video.closest(".lesson-card");

  const formatTime = seconds => {
    const value = Math.floor(Number.isFinite(seconds) ? seconds : 0);
    return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, "0")}`;
  };

  function update() {
    const ready = Number.isFinite(video.duration) && video.duration > 0;
    play.disabled = Boolean(video.error);
    play.textContent = video.paused ? "▶" : "Ⅱ";
    play.setAttribute("aria-label", video.paused ? "Reproduzir vídeo" : "Pausar vídeo");
    progress.disabled = !ready;
    progress.value = ready ? String(video.currentTime / video.duration * 100) : "0";
    progress.setAttribute("aria-valuetext", `${formatTime(video.currentTime)} de ${formatTime(video.duration)}`);
    time.textContent = formatTime(video.currentTime);
    mute.querySelector("[data-volume-on]").hidden = video.muted;
    mute.querySelector("[data-volume-off]").hidden = !video.muted;
    mute.setAttribute("aria-label", video.muted ? "Ativar som" : "Silenciar vídeo");
    mute.title = video.muted ? "Ativar som" : "Silenciar vídeo";
    mute.setAttribute("aria-pressed", String(video.muted));
  }

  play.addEventListener("click", async () => {
    error.hidden = true;
    if (!video.paused) {
      video.pause();
      return;
    }
    try {
      await video.play();
    } catch {
      error.textContent = "Não foi possível iniciar. Tente novamente ou use Abrir vídeo.";
      error.hidden = false;
    }
  });
  progress.addEventListener("input", () => {
    if (Number.isFinite(video.duration)) video.currentTime = Number(progress.value) / 100 * video.duration;
  });
  mute.addEventListener("click", () => { video.muted = !video.muted; });
  fullscreen.addEventListener("click", async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else if (card.requestFullscreen) await card.requestFullscreen();
      else if (video.webkitEnterFullscreen) video.webkitEnterFullscreen();
    } catch {
      error.textContent = "Tela cheia indisponível neste navegador.";
      error.hidden = false;
    }
  });
  if (!card.requestFullscreen && !video.webkitEnterFullscreen) fullscreen.hidden = true;
  document.addEventListener("fullscreenchange", () => {
    const expanded = document.fullscreenElement === card;
    const label = expanded ? "Sair da tela cheia" : "Tela cheia";
    fullscreen.setAttribute("aria-label", label);
    fullscreen.title = label;
  });
  for (const event of ["loadedmetadata", "timeupdate", "play", "pause", "ended", "volumechange", "durationchange"]) {
    video.addEventListener(event, update);
  }
  video.addEventListener("error", () => {
    error.hidden = false;
    update();
  });
  video.controls = false;
  controls.hidden = false;
  if (video.error) error.hidden = false;
  update();
})();
