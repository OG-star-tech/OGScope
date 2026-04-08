/** 侧栏 flyout 行为（自原 index.html 内联脚本迁移）/ Rail flyouts migrated from inline index template */

export function initHudRailFlyouts(): void {
  function bindRailFlyout(
    toggleId: string,
    panelId: string,
    chevronId?: string | null,
  ): { closeFlyout: () => void } | null {
    const toggle = document.getElementById(toggleId);
    const panel = document.getElementById(panelId);
    const chevron = chevronId ? document.getElementById(chevronId) : null;
    if (!toggle || !panel) return null;
    function positionFlyout() {
      if (panel.classList.contains("hidden")) return;
      const br = toggle.getBoundingClientRect();
      panel.style.top = `${br.top}px`;
      panel.style.right = `${Math.max(0, window.innerWidth - br.left + 6)}px`;
      panel.style.left = "auto";
      panel.style.maxHeight = `${Math.min(window.innerHeight - br.top - 8, window.innerHeight * 0.65)}px`;
    }
    function closeFlyout() {
      panel.classList.add("hidden");
      toggle.setAttribute("aria-expanded", "false");
      if (chevron) chevron.style.transform = "";
    }
    toggle.addEventListener("click", () => {
      panel.classList.toggle("hidden");
      const open = !panel.classList.contains("hidden");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      if (chevron) chevron.style.transform = open ? "rotate(180deg)" : "";
      if (open) requestAnimationFrame(positionFlyout);
    });
    window.addEventListener("resize", positionFlyout);
    window.addEventListener("orientationchange", () => {
      setTimeout(positionFlyout, 100);
    });
    return { closeFlyout };
  }

  const modeFlyout = bindRailFlyout("mode-rail-toggle", "mode-rail-panel", "mode-rail-chevron");
  const adjFlyout = bindRailFlyout("adj-rail-toggle", "adj-rail-panel");
  const layerFlyout = bindRailFlyout("layer-rail-toggle", "layer-rail-panel");
  const modePanel = document.getElementById("mode-rail-panel");
  if (modePanel && modeFlyout) {
    modePanel.querySelectorAll(".mode-button").forEach((btn) => {
      btn.addEventListener("click", () => {
        modeFlyout.closeFlyout();
      });
    });
  }
  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const rows: [string, string, { closeFlyout: () => void } | null][] = [
      ["mode-rail-toggle", "mode-rail-panel", modeFlyout],
      ["adj-rail-toggle", "adj-rail-panel", adjFlyout],
      ["layer-rail-toggle", "layer-rail-panel", layerFlyout],
    ];
    for (const [tid, pid, api] of rows) {
      const tEl = document.getElementById(tid);
      const pEl = document.getElementById(pid);
      if (!tEl || !pEl || !api) continue;
      if (tEl.contains(target) || pEl.contains(target)) continue;
      api.closeFlyout();
    }
  });
}
