import { useEffect, useMemo, useState } from "react";
import { DebugShell } from "./DebugShell";
import { OverviewPage } from "./pages/OverviewPage";
import { NetworkPage } from "./pages/NetworkPage";
import { HmiPage } from "./pages/HmiPage";
import { PlaceholderPage } from "./pages/PlaceholderPage";
import { SensorsPage } from "./pages/SensorsPage";

type SystemRoute = "overview" | "network" | "sensors" | "hmi" | "power";

const routeSet = new Set<SystemRoute>(["overview", "network", "sensors", "hmi", "power"]);

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

  useEffect(() => {
    const onHashChange = () => setRoute(readRouteFromHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const page = useMemo(() => {
    if (route === "network") return <NetworkPage />;
    if (route === "sensors") return <SensorsPage />;
    if (route === "hmi") return <HmiPage />;
    if (route === "power") return <PlaceholderPage scope="power" />;
    return <OverviewPage />;
  }, [route]);

  return (
    <DebugShell
      route={route}
      onRouteChange={(next) => {
        if (next === route) return;
        setHashRoute(next);
      }}
    >
      {page}
    </DebugShell>
  );
}
