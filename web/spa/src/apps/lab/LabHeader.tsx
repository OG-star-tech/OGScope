import { Home } from "lucide-react";

import type { LabView } from "./labTypes";
import { useI18n } from "@shared/i18n/I18nProvider";

export function LabHeader({
  view,
  setView,
}: {
  view: LabView;
  setView: (v: LabView) => void;
}) {
  const { t, locale, setLocale } = useI18n();
  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b border-outline-variant/20 px-4">
      <div className="flex items-center gap-6">
        <span className="font-headline text-sm font-bold tracking-wide text-on-surface">
          {t("app.title")}
        </span>
        <nav className="flex flex-wrap gap-3 text-xs">
          <button
            type="button"
            className={view === "lab_image" ? "text-primary" : "text-on-surface-variant"}
            onClick={() => setView("lab_image")}
          >
            {t("nav.labImage")}
          </button>
          <button
            type="button"
            className={view === "lab_video" ? "text-primary" : "text-on-surface-variant"}
            onClick={() => setView("lab_video")}
          >
            {t("nav.labVideo")}
          </button>
          <button
            type="button"
            className={view === "pool" ? "text-primary" : "text-on-surface-variant"}
            onClick={() => setView("pool")}
          >
            {t("nav.pool")}
          </button>
          <button
            type="button"
            className={view === "history" ? "text-primary" : "text-on-surface-variant"}
            onClick={() => setView("history")}
          >
            {t("nav.history")}
          </button>
        </nav>
      </div>
      <div className="flex items-center gap-2">
        <div className="mr-2 flex gap-1 text-[10px]">
          <button
            type="button"
            className={`rounded px-2 py-0.5 ${locale === "zh" ? "bg-primary-container text-on-primary-container" : "text-on-surface-variant"}`}
            onClick={() => setLocale("zh")}
          >
            {t("lang.zh")}
          </button>
          <button
            type="button"
            className={`rounded px-2 py-0.5 ${locale === "en" ? "bg-primary-container text-on-primary-container" : "text-on-surface-variant"}`}
            onClick={() => setLocale("en")}
          >
            {t("lang.en")}
          </button>
        </div>
        <a
          className="flex items-center gap-1 rounded border border-outline-variant/30 px-2 py-1 text-xs text-on-surface-variant hover:bg-surface-container"
          href="/debug"
        >
          <Home className="h-3.5 w-3.5" /> {t("nav.systemAdmin")}
        </a>
      </div>
    </header>
  );
}
