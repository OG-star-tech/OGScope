import { Database, Trash2 } from "lucide-react";

import type { UploadFileRow } from "@shared/api";
import { useI18n } from "@shared/i18n/I18nProvider";
import { formatDateTime, formatFileSize } from "@shared/utils/format";

export function LabPoolView({
  uploads,
  onDelete,
}: {
  uploads: UploadFileRow[];
  onDelete: (filename: string) => void | Promise<void>;
}) {
  const { t, locale } = useI18n();
  return (
    <main className="og-scrollbar flex-1 overflow-auto p-4">
      <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold">
        <Database className="h-5 w-5" /> {t("pool.title")}
      </h2>
      <table className="w-full text-left text-xs">
        <thead>
          <tr className="border-b border-outline-variant/30 text-on-surface-variant">
            <th className="py-2">{t("pool.col.name")}</th>
            <th className="py-2">{t("pool.col.source")}</th>
            <th className="py-2">{t("pool.col.size")}</th>
            <th className="py-2">{t("pool.col.time")}</th>
            <th className="w-16 py-2 text-center">{t("pool.delete")}</th>
          </tr>
        </thead>
        <tbody>
          {uploads.map((u) => (
            <tr key={u.filename} className="border-b border-outline-variant/10">
              <td className="py-2 font-mono">{u.filename}</td>
              <td className="py-2">{u.source ?? t("common.placeholder")}</td>
              <td className="py-2">{formatFileSize(u.size)}</td>
              <td className="py-2">{formatDateTime(u.modified_at, locale)}</td>
              <td className="py-2 text-center">
                <button
                  type="button"
                  className="inline-flex rounded p-1 text-on-surface-variant hover:bg-error-container/30 hover:text-error"
                  title={t("pool.delete")}
                  aria-label={t("pool.delete")}
                  onClick={() => void onDelete(u.filename)}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
