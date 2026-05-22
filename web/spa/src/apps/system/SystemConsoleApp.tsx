import { useEffect, useMemo, useState } from "react";
import { DebugShell } from "./DebugShell";
import { OverviewPage } from "./pages/OverviewPage";
import { NetworkPage } from "./pages/NetworkPage";
import { HmiPage } from "./pages/HmiPage";
import { PlaceholderPage } from "./pages/PlaceholderPage";
import { SensorsPage } from "./pages/SensorsPage";
import { ConfigPage } from "./pages/ConfigPage";

type SystemRoute = "overview" | "network" | "sensors" | "hmi" | "power" | "config";

const routeSet = new Set<SystemRoute>(["overview", "network", "sensors", "hmi", "power", "config"]);

function readRouteFromHash(): SystemRoute {
  const raw = window.location.hash.replace(/^#\/?/, "").trim().toLowerCase();
  if (routeSet.has(raw as SystemRoute)) return raw as SystemRoute;
  return "overview";
}

function setHashRoute(route: SystemRoute) {
  window.location.hash = `/${route}`;
}

export function SystemConsoleApp() {
  const [route, setRoute] = useState<SystemRoute>(() => readRouteFromHash());
  const [allowNetworkRoute, setAllowNetworkRoute] = useState(true);

  useEffect(() => {
    const onHashChange = () => setRoute(readRouteFromHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        const payload = await fetch("/api", { cache: "no-store" });
        if (!payload.ok) return;
        const data = (await payload.json()) as { endpoints?: Record<string, string> };
        setAllowNetworkRoute(Boolean(data.endpoints?.network));
      } catch {
        // keep default true for backward compatibility
      }
    })();
  }, []);

  const page = useMemo(() => {
    if (route === "network") {
      return allowNetworkRoute ? (
        <NetworkPage />
      ) : (
        <PlaceholderPage scope="network" />
      );
    }
    if (route === "sensors") return <SensorsPage />;
    if (route === "hmi") return <HmiPage />;
    if (route === "config") return <ConfigPage />;
    if (route === "power") return <PlaceholderPage scope="power" />;
    return <OverviewPage />;
  }, [allowNetworkRoute, route]);

  return (
    <DebugShell
      route={route}
      allowNetworkRoute={allowNetworkRoute}
      onRouteChange={(next) => {
        if (next === "network" && !allowNetworkRoute) return;
        if (next === route) return;
        setHashRoute(next);
      }}
    >
      {page}
    </DebugShell>
  );
}
