import { useEffect, useMemo, useState } from "react";
import { RefreshCw, Save } from "lucide-react";
import { requestJson } from "@shared/transport/http";
import { useI18n } from "@shared/i18n/I18nProvider";

type ConfigFileItem = {
  file_id: string;
  path: string;
  exists: boolean;
  writable: boolean;
  content: string;
  error?: string | null;
};

type ConfigFilesResponse = {
  success: boolean;
  files: ConfigFileItem[];
};

export function ConfigPage() {
  const { locale } = useI18n();
  const [files, setFiles] = useState<ConfigFileItem[]>([]);
  const [activeId, setActiveId] = useState<string>("");
  const [editor, setEditor] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const isZh = locale === "zh";

  const activeFile = useMemo(
    () => files.find((item) => item.file_id === activeId) ?? null,
    [activeId, files],
  );

  const loadFiles = async () => {
    setBusy(true);
    setError("");
    try {
      const payload = await requestJson<ConfigFilesResponse>("/api/dev/system/config/files", {
        cache: "no-store",
      });
      setFiles(payload.files ?? []);
      const nextId = payload.files?.[0]?.file_id ?? "";
      setActiveId((prev) => (prev && payload.files?.some((f) => f.file_id === prev) ? prev : nextId));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const saveFile = async () => {
    if (!activeId) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await requestJson<{ message?: string; restart_required?: boolean }>(
        "/api/dev/system/config/files",
        {
          method: "POST",
          body: JSON.stringify({ file_id: activeId, content: editor }),
        },
      );
      setMessage(
        isZh
          ? `保存成功：${result.message ?? activeId}；建议重启服务使配置生效`
          : `Saved: ${result.message ?? activeId}; restart service to apply changes`,
      );
      await loadFiles();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void loadFiles();
  }, []);

  useEffect(() => {
    if (!activeFile) {
      setEditor("");
      return;
    }
    setEditor(activeFile.content ?? "");
  }, [activeFile]);

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <header>
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.14em] text-on-surface-variant">
          <span>Console</span>
          <span>/</span>
          <span className="text-primary">{isZh ? "配置管理" : "Config Manager"}</span>
        </div>
        <h2 className="mt-1 font-headline text-3xl font-black tracking-tight">
          {isZh ? "环境配置编辑器" : "Environment Config Editor"}
        </h2>
        <p className="text-sm text-on-surface-variant">
          {isZh
            ? "用于编辑 /etc/ogscope 下部署配置，保存后建议重启 ogscope 服务。"
            : "Edit deployment config under /etc/ogscope. Restart ogscope service after saving."}
        </p>
      </header>

      {error && (
        <div className="rounded-lg border border-error/40 bg-error-container/20 px-3 py-2 text-sm text-on-error-container">
          {error}
        </div>
      )}
      {message && <div className="rounded-lg border border-primary/30 bg-primary/10 px-3 py-2 text-sm">{message}</div>}

      <section className="grid grid-cols-12 gap-4">
        <aside className="col-span-12 space-y-2 rounded-xl border border-outline-variant/20 bg-surface-container p-3 lg:col-span-3">
          <div className="flex items-center justify-between">
            <p className="text-xs uppercase tracking-wider text-on-surface-variant">{isZh ? "配置文件" : "Config Files"}</p>
            <button type="button" onClick={() => void loadFiles()} disabled={busy}>
              <span className="inline-flex items-center gap-1 text-xs">
                <RefreshCw className="h-3.5 w-3.5" /> {isZh ? "刷新" : "Refresh"}
              </span>
            </button>
          </div>
          {files.map((file) => (
            <button
              type="button"
              key={file.file_id}
              onClick={() => setActiveId(file.file_id)}
              className={`w-full rounded-lg border px-3 py-2 text-left text-sm ${
                file.file_id === activeId
                  ? "border-primary bg-primary/10 text-on-surface"
                  : "border-outline-variant/30 bg-surface-container-low text-on-surface-variant"
              }`}
            >
              <div className="font-medium">{file.file_id}</div>
              <div className="mt-1 truncate font-mono text-[11px]">{file.path}</div>
            </button>
          ))}
        </aside>

        <div className="col-span-12 rounded-xl border border-outline-variant/20 bg-surface-container p-4 lg:col-span-9">
          {!activeFile && <p className="text-sm text-on-surface-variant">{isZh ? "暂无可编辑配置文件" : "No editable config files."}</p>}
          {activeFile && (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="font-mono text-xs text-on-surface">{activeFile.path}</p>
                  <p className="text-xs text-on-surface-variant">
                    {isZh ? "可写" : "Writable"}: {String(activeFile.writable)} ·{" "}
                    {isZh ? "存在" : "Exists"}: {String(activeFile.exists)}
                  </p>
                </div>
                <button type="button" onClick={() => void saveFile()} disabled={busy || !activeFile.writable}>
                  <span className="inline-flex items-center gap-1">
                    <Save className="h-3.5 w-3.5" />
                    {isZh ? "保存并提示重启" : "Save"}
                  </span>
                </button>
              </div>
              {activeFile.error && (
                <div className="rounded border border-error/40 bg-error-container/20 px-2 py-1 text-xs text-on-error-container">
                  {activeFile.error}
                </div>
              )}
              <textarea
                className="h-[460px] w-full rounded-lg border border-outline-variant/30 bg-neutral-950 p-3 font-mono text-xs text-on-surface outline-none focus:border-primary"
                spellCheck={false}
                value={editor}
                onChange={(e) => setEditor(e.target.value)}
              />
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
