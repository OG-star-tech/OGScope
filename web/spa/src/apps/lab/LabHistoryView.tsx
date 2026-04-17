import type { Dispatch, SetStateAction } from "react";
import { History } from "lucide-react";

import { experimentAssetUrl, exportExperiments } from "@dev-api/analysis";
import { useI18n } from "@shared/i18n/I18nProvider";
import { formatDateTime } from "@shared/utils/format";

export function LabHistoryView({
  historyQ,
  setHistoryQ,
  historyPage,
  setHistoryPage,
  historyData,
  historyExpandId,
  setHistoryExpandId,
  historyTotalPages,
  onDeleteExperiment,
  onSearch,
}: {
  historyQ: string;
  setHistoryQ: (q: string) => void;
  historyPage: number;
  setHistoryPage: Dispatch<SetStateAction<number>>;
  historyData: { items: unknown[]; total: number } | null;
  historyExpandId: string | null;
  setHistoryExpandId: (id: string | null) => void;
  historyTotalPages: number;
  onDeleteExperiment: (id: string) => void | Promise<void>;
  /** 搜索并重置到第一页 / Search and reset to page 1 */
  onSearch: () => void;
}) {
  const { t, locale } = useI18n();
  return (
    <main className="og-scrollbar flex-1 overflow-auto p-4">
      <p className="mb-4 rounded-lg border border-outline-variant/25 bg-surface-container-lowest/90 p-3 text-xs leading-relaxed text-on-surface-variant">
        {t("history.intro")}
      </p>
      <div className="mb-4 flex flex-wrap items-center gap-4">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <History className="h-5 w-5" /> {t("history.title")}
        </h2>
        <input
          className="rounded bg-surface-container-highest px-2 py-1 text-xs"
          placeholder={t("history.search")}
          value={historyQ}
          onChange={(e) => setHistoryQ(e.target.value)}
        />
        <button type="button" className="rounded bg-surface-container px-2 py-1 text-xs" onClick={onSearch}>
          {t("history.searchBtn")}
        </button>
        <button
          type="button"
          className="rounded bg-primary-container/50 px-2 py-1 text-xs"
          onClick={() =>
            exportExperiments("json").then((text) => {
              const blob = new Blob([text], { type: "application/json" });
              const a = document.createElement("a");
              a.href = URL.createObjectURL(blob);
              a.download = "experiments.json";
              a.click();
            })
          }
        >
          {t("history.exportJson")}
        </button>
        <button
          type="button"
          className="rounded bg-primary-container/50 px-2 py-1 text-xs"
          onClick={() =>
            exportExperiments("csv").then((text) => {
              const blob = new Blob([text], { type: "text/csv" });
              const a = document.createElement("a");
              a.href = URL.createObjectURL(blob);
              a.download = "experiments.csv";
              a.click();
            })
          }
        >
          {t("history.exportCsv")}
        </button>
      </div>
      <div className="flex flex-wrap items-center gap-3 text-xs text-on-surface-variant">
        <span>{t("history.total", { n: historyData?.total ?? 0 })}</span>
        <button
          type="button"
          className="rounded border border-outline-variant/30 px-2 py-0.5 disabled:opacity-40"
          disabled={historyPage <= 1}
          onClick={() => setHistoryPage((p) => Math.max(1, p - 1))}
        >
          {t("history.prev")}
        </button>
        <span>
          {historyPage} / {historyTotalPages}
        </span>
        <button
          type="button"
          className="rounded border border-outline-variant/30 px-2 py-0.5 disabled:opacity-40"
          disabled={historyPage >= historyTotalPages}
          onClick={() => setHistoryPage((p) => p + 1)}
        >
          {t("history.next")}
        </button>
      </div>
      <ul className="mt-2 space-y-2">
        {(historyData?.items as Array<Record<string, unknown>>)?.map((row) => {
          const id = String(row.id ?? "");
          const metrics = row.metrics as Record<string, unknown> | undefined;
          const open = historyExpandId === id;
          return (
            <li
              key={id}
              className="rounded border border-outline-variant/20 p-2 text-[11px]"
            >
              <div className="flex flex-wrap items-start justify-between gap-2 font-mono">
                <div>
                  <div className="text-on-surface">
                    {formatDateTime(String(row.created_at ?? ""), locale)} —{" "}
                    {String(row.input_name)} — {String(row.preset_label)}
                  </div>
                  <div className="mt-1 text-on-surface-variant">
                    {t("history.preset")}: {String(row.preset_label)} · {t("history.metrics")}:{" "}
                    matches={String(metrics?.matches ?? "—")} rmse=
                    {String(metrics?.rmse_arcsec ?? "—")}
                  </div>
                </div>
                <div className="flex shrink-0 gap-1">
                  <button
                    type="button"
                    className="rounded bg-surface-container px-2 py-0.5 text-[10px]"
                    onClick={() => setHistoryExpandId(open ? null : id)}
                  >
                    {open ? t("history.collapse") : t("history.detail")}
                  </button>
                  <button
                    type="button"
                    className="rounded px-2 py-0.5 text-[10px] text-error hover:bg-error-container/20"
                    title={t("history.delete")}
                    onClick={() => void onDeleteExperiment(id)}
                  >
                    {t("history.delete")}
                  </button>
                </div>
              </div>
              {open && (
                <div className="mt-2 space-y-2">
                  {row.asset_snapshot_relpath ? (
                    <img
                      src={experimentAssetUrl(id)}
                      alt=""
                      className="max-h-48 max-w-full rounded border border-outline-variant/20 object-contain"
                    />
                  ) : null}
                  <pre className="og-scrollbar max-h-64 overflow-auto rounded bg-surface-container p-2 text-[10px]">
                    {JSON.stringify(row.result_json, null, 2)}
                  </pre>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </main>
  );
}
