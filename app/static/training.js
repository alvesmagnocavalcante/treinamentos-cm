"use strict";

(() => {
  const tablist = document.getElementById("training-tabs");
  const tabs = Array.from(tablist.querySelectorAll('[role="tab"]'));
  const panels = tabs.map(tab => document.getElementById(tab.getAttribute("aria-controls")));
  const originalLabels = panels.map(panel => panel.getAttribute("aria-labelledby"));
  const mobile = window.matchMedia("(max-width: 1000px)");
  let selected = 0;

  function updatePanels() {
    tablist.hidden = !mobile.matches;
    tabs.forEach((tab, index) => {
      const active = index === selected;
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
      const panel = panels[index];
      panel.hidden = mobile.matches && !active;
      if (mobile.matches) {
        panel.setAttribute("role", "tabpanel");
        panel.setAttribute("aria-labelledby", tab.id);
      } else {
        panel.removeAttribute("role");
        if (originalLabels[index]) panel.setAttribute("aria-labelledby", originalLabels[index]);
        else panel.removeAttribute("aria-labelledby");
      }
    });
  }

  function selectTab(index) {
    selected = index;
    updatePanels();
    tablist.scrollIntoView({block: "start"});
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => selectTab(index));
    tab.addEventListener("keydown", event => {
      let next;
      if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
      else if (event.key === "ArrowLeft") next = (index + tabs.length - 1) % tabs.length;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = tabs.length - 1;
      else return;
      event.preventDefault();
      selectTab(next);
      tabs[next].focus({preventScroll: true});
    });
  });

  function updateViewport() {
    const height = window.visualViewport?.height ?? window.innerHeight;
    document.documentElement.style.setProperty("--mobile-viewport-height", `${height}px`);
    if (mobile.matches && selected === 1) {
      window.requestAnimationFrame(() => tablist.scrollIntoView({block: "start"}));
    }
  }

  mobile.addEventListener("change", () => {
    updatePanels();
    updateViewport();
  });
  window.addEventListener("resize", updateViewport, {passive: true});
  window.visualViewport?.addEventListener("resize", updateViewport, {passive: true});
  updatePanels();
  updateViewport();
})();
