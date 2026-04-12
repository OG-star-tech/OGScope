import { useEffect, useMemo, useState } from "react";
import { DebugShell } from "./DebugShell";
import { OverviewPage } from "./pages/OverviewPage";
import { NetworkPage } from "./pages/NetworkPage";
import { PlaceholderPage } from "./pages/PlaceholderPage";
import { ZacpPage } from "./pages/ZacpPage";

type SystemRoute = "overview" | "network" | "legacy protocol" | "sensors" | "hmi" | "power";

const routeSet = new Set<SystemRoute>(["overview", "network", "legacy protocol", "sensors", "hmi", "power"]);

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
    if (route === "legacy protocol") return <ZacpPage />;
    if (route === "sensors") return <PlaceholderPage scope="sensors" />;
    if (route === "hmi") return <PlaceholderPage scope="hmi" />;
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
