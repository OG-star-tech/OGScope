import { useEffect, useMemo, useState } from "react";
import { Plus, RefreshCw, Save, Trash2 } from "lucide-react";
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

type EditorMode = "form" | "raw";

type EnvEntry = {
  id: string;
  key: string;
  value: string;
};

type ConfigHint = {
  key: string;
  zh: string;
  en: string;
};

const OGSCOPE_ENV_HINTS: ConfigHint[] = [
  { key: "OGSCOPE_HOST", zh: "OGScope 服务监听地址，通常保持 0.0.0.0。", en: "OGScope bind host, usually keep 0.0.0.0." },
  { key: "OGSCOPE_PORT", zh: "OGScope 服务端口，默认 8000。", en: "OGScope service port, default 8000." },
  { key: "OGSCOPE_RELOAD", zh: "是否启用热重载（开发用）。", en: "Enable hot reload for development." },
  { key: "OGSCOPE_LOG_LEVEL", zh: "日志级别（DEBUG/INFO/WARNING/ERROR）。", en: "Log level (DEBUG/INFO/WARNING/ERROR)." },
  { key: "OGSCOPE_DEVELOPMENT_MODE", zh: "开发模式开关，打开后会输出更详细日志。", en: "Development mode switch for more verbose logs." },
  {
    key: "OGSCOPE_HARDWARE_PLANE_ROLE",
    zh: "硬件平面角色：standalone 或 subordinate。",
    en: "Hardware plane role: standalone or subordinate.",
  },
  {
    key: "OGSCOPE_SUBORDINATE_LOCAL_DEV_ONLY",
    zh: "在 subordinate 角色下是否仅允许本机访问 /api/dev/*。",
    en: "Restrict /api/dev/* to localhost in subordinate mode.",
  },
  { key: "OGSCOPE_ENABLE_UI", zh: "是否启用 Web UI 路由。", en: "Enable Web UI routes." },
  { key: "OGSCOPE_ENABLE_LOCAL_SENSORS", zh: "是否启用本地传感器服务。", en: "Enable local sensor services." },
  { key: "OGSCOPE_ENABLE_HMI", zh: "是否启用 HMI 服务。", en: "Enable HMI service." },
  {
    key: "OGSCOPE_WIFI_STA_SSID",
    zh: "STA 模式目标 WiFi SSID（network.env 常见项）。",
    en: "Target STA WiFi SSID (common in network.env).",
  },
  {
    key: "OGSCOPE_WIFI_STA_PASSWORD",
    zh: "STA 模式目标 WiFi 密码（network.env 常见项）。",
    en: "Target STA WiFi password (common in network.env).",
  },
];

const OGSCOPE_ENV_HINT_MAP = new Map<string, ConfigHint>(
  OGSCOPE_ENV_HINTS.map((item) => [item.key.toUpperCase(), item]),
);

function parseEnvEntries(content: string): { entries: EnvEntry[]; unsupportedLines: number } {
  const entries: EnvEntry[] = [];
  let unsupportedLines = 0;
  const lines = content.split(/\r?\n/);
  lines.forEach((line, index) => {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) return;
    const normalized = trimmed.startsWith("export ") ? trimmed.slice(7) : trimmed;
    const sepIndex = normalized.indexOf("=");
    if (sepIndex <= 0) {
      unsupportedLines += 1;
      return;
    }
    const key = normalized.slice(0, sepIndex).trim();
    if (!key) {
      unsupportedLines += 1;
      return;
    }
    const value = normalized.slice(sepIndex + 1);
    entries.push({
      id: `env-${index}-${key}`,
      key,
      value,
    });
  });
  return { entries, unsupportedLines };
}

function buildEnvContent(entries: EnvEntry[]): string {
  const lines = entries
    .map((entry) => ({ key: entry.key.trim(), value: entry.value }))
    .filter((entry) => entry.key.length > 0)
    .map((entry) => `${entry.key}=${entry.value}`);
  return lines.length > 0 ? `${lines.join("\n")}\n` : "";
}

export function ConfigPage() {
  const { locale } = useI18n();
  const [files, setFiles] = useState<ConfigFileItem[]>([]);
  const [activeId, setActiveId] = useState<string>("");
  const [editor, setEditor] = useState("");
  const [mode, setMode] = useState<EditorMode>("form");
  const [formEntries, setFormEntries] = useState<EnvEntry[]>([]);
  const [unsupportedLines, setUnsupportedLines] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const isZh = locale === "zh";

  const activeFile = useMemo(
    () => files.find((item) => item.file_id === activeId) ?? null,
    [activeId, files],
  );

  const reloadFormFromRaw = (raw: string) => {
    const parsed = parseEnvEntries(raw);
    setFormEntries(parsed.entries);
    setUnsupportedLines(parsed.unsupportedLines);
  };

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
    if (mode === "form" && unsupportedLines > 0) {
      setError(
        isZh
          ? "当前文件包含无法表单化的行，请切换到“原始文本”模式编辑后再保存。"
          : "This file has lines not supported by form mode. Switch to Raw mode before saving.",
      );
      return;
    }
    const payloadContent = mode === "form" ? buildEnvContent(formEntries) : editor;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await requestJson<{ message?: string; restart_required?: boolean }>(
        "/api/dev/system/config/files",
        {
          method: "POST",
          body: JSON.stringify({ file_id: activeId, content: payloadContent }),
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
      setFormEntries([]);
      setUnsupportedLines(0);
      return;
    }
    const nextRaw = activeFile.content ?? "";
    setEditor(nextRaw);
    reloadFormFromRaw(nextRaw);
  }, [activeFile]);

  const addEntry = () => {
    setFormEntries((prev) => [
      ...prev,
      { id: `env-new-${Date.now()}-${prev.length}`, key: "", value: "" },
    ]);
  };

  const updateEntry = (id: string, patch: Partial<EnvEntry>) => {
    setFormEntries((prev) => prev.map((entry) => (entry.id === id ? { ...entry, ...patch } : entry)));
  };

  const removeEntry = (id: string) => {
    setFormEntries((prev) => prev.filter((entry) => entry.id !== id));
  };

  const configHintText = (key: string) => {
    const hint = OGSCOPE_ENV_HINT_MAP.get(key.trim().toUpperCase());
    if (!hint) return isZh ? "暂无释义" : "No hint";
    return isZh ? hint.zh : hint.en;
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <header>
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.14em] text-on-surface-variant">
          <span>Console</span>
          <span>/</span>
          <span className="text-primary">{isZh ? "配置管理" : "Config Manager"}</span>
        </div>
        <h2 className="mt-1 font-headline text-3xl font-black tracking-tight">
          {isZh ? "环境配置管理" : "Environment Config Manager"}
        </h2>
        <p className="text-sm text-on-surface-variant">
          {isZh
            ? "支持键值表单与原始文本两种模式。保存后建议重启 ogscope 服务。"
            : "Supports both key-value form mode and raw text mode. Restart ogscope after saving."}
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
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      if (mode === "raw") reloadFormFromRaw(editor);
                      setMode("form");
                    }}
                    className={`rounded px-2 py-1 text-xs ${
                      mode === "form"
                        ? "bg-primary-container text-on-primary-container"
                        : "border border-outline-variant/30 text-on-surface-variant"
                    }`}
                  >
                    {isZh ? "表单模式" : "Form"}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (mode === "form") setEditor(buildEnvContent(formEntries));
                      setMode("raw");
                    }}
                    className={`rounded px-2 py-1 text-xs ${
                      mode === "raw"
                        ? "bg-primary-container text-on-primary-container"
                        : "border border-outline-variant/30 text-on-surface-variant"
                    }`}
                  >
                    {isZh ? "原始文本" : "Raw"}
                  </button>
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
              {mode === "form" ? (
                <div className="space-y-3">
                  {unsupportedLines > 0 && (
                    <div className="rounded border border-warning/40 bg-warning/10 px-2 py-1 text-xs text-on-surface">
                      {isZh
                        ? `检测到 ${unsupportedLines} 行无法转换为键值表单（如复杂写法）。请切到“原始文本”模式处理。`
                        : `${unsupportedLines} line(s) cannot be represented in key-value form. Use Raw mode for these lines.`}
                    </div>
                  )}
                  <div className="max-h-[420px] overflow-auto pr-1">
                    <table className="w-full border-separate border-spacing-y-2">
                      <thead>
                        <tr className="text-left text-[11px] uppercase tracking-wide text-on-surface-variant">
                          <th>{isZh ? "配置项" : "Key"}</th>
                          <th>{isZh ? "值" : "Value"}</th>
                          <th>{isZh ? "释义" : "Meaning"}</th>
                          <th>{isZh ? "操作" : "Action"}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {formEntries.map((entry) => (
                          <tr key={entry.id}>
                            <td className="pr-2 align-top">
                              <input
                                className="w-full rounded border border-outline-variant/30 bg-surface-container-low px-2 py-1 font-mono text-xs outline-none focus:border-primary"
                                placeholder={isZh ? "变量名，如 OGSCOPE_PORT" : "Key, e.g. OGSCOPE_PORT"}
                                value={entry.key}
                                onChange={(e) => updateEntry(entry.id, { key: e.target.value })}
                              />
                            </td>
                            <td className="pr-2 align-top">
                              <input
                                className="w-full rounded border border-outline-variant/30 bg-surface-container-low px-2 py-1 font-mono text-xs outline-none focus:border-primary"
                                placeholder={isZh ? "变量值" : "Value"}
                                value={entry.value}
                                onChange={(e) => updateEntry(entry.id, { value: e.target.value })}
                              />
                            </td>
                            <td className="pr-2 align-top text-xs text-on-surface-variant">
                              {configHintText(entry.key)}
                            </td>
                            <td className="align-top">
                              <button type="button" onClick={() => removeEntry(entry.id)}>
                                <Trash2 className="h-3.5 w-3.5 text-on-surface-variant" />
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {formEntries.length === 0 && (
                      <div className="rounded border border-outline-variant/20 bg-surface-container-low px-2 py-2 text-xs text-on-surface-variant">
                        {isZh ? "当前没有可编辑变量，点击下方添加。" : "No variables yet. Add one below."}
                      </div>
                    )}
                  </div>
                  <button type="button" onClick={addEntry}>
                    <span className="inline-flex items-center gap-1 text-xs">
                      <Plus className="h-3.5 w-3.5" />
                      {isZh ? "添加变量" : "Add Variable"}
                    </span>
                  </button>
                  <div className="rounded border border-outline-variant/20 bg-surface-container-low px-3 py-2 text-xs text-on-surface-variant">
                    <p className="mb-2 font-medium text-on-surface">{isZh ? "常用配置释义" : "Common Config Glossary"}</p>
                    <div className="space-y-1">
                      {OGSCOPE_ENV_HINTS.map((hint) => (
                        <p key={hint.key}>
                          <span className="font-mono text-[11px] text-on-surface">{hint.key}</span>
                          {" - "}
                          <span>{isZh ? hint.zh : hint.en}</span>
                        </p>
                      ))}
                    </div>
                  </div>
                </div>
              ) : (
                <textarea
                  className="h-[460px] w-full rounded-lg border border-outline-variant/30 bg-neutral-950 p-3 font-mono text-xs text-on-surface outline-none focus:border-primary"
                  spellCheck={false}
                  value={editor}
                  onChange={(e) => setEditor(e.target.value)}
                />
              )}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
