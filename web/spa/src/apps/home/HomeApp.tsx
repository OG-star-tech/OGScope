import { useEffect, useLayoutEffect, useRef } from "react";

import hudBody from "./homeHudBody.html?raw";
import { initHudRailFlyouts } from "./hudRailFlyouts";
import { HOME_LEGACY_SCRIPTS, loadScriptChain } from "./loadLegacyScripts";

/**
 * 用户首页 HUD：注入与旧 Jinja 相同的 DOM，并加载既有 vanilla 脚本链。
 * User HUD: same DOM as legacy Jinja page + existing /static/js pipeline.
 */
export function HomeApp() {
  const hostRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    host.innerHTML = "";
    const tpl = document.createElement("template");
    tpl.innerHTML = hudBody.trim();
    host.appendChild(tpl.content.cloneNode(true));
    let cancelled = false;
    loadScriptChain(HOME_LEGACY_SCRIPTS)
      .then(() => {
        if (cancelled) return;
        initHudRailFlyouts();
      })
      .catch((e) => {
        console.error(e);
      });
    return () => {
      cancelled = true;
      host.innerHTML = "";
    };
  }, []);

  useEffect(() => {
    fetch("/api")
      .then((r) => r.json())
      .then((d: { version?: string }) => {
        const el = document.getElementById("hud-app-version");
        if (el) el.textContent = d.version ?? "—";
      })
      .catch(() => {
        const el = document.getElementById("hud-app-version");
        if (el) el.textContent = "—";
      });
  }, []);

  return (
    <div
      className="h-dvh max-h-dvh overflow-hidden bg-background text-on-background font-body select-none"
      ref={hostRef}
    />
  );
}
