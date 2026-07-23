import { useEffect, useMemo, useState } from "react";
import { BookOpen, Plus, RefreshCw, Save, Search, Trash2 } from "lucide-react";
import { requestJson } from "@shared/transport/http";
import { useI18n } from "@shared/i18n/I18nProvider";

type ConfigFileItem = {
  file_id: string;
  path: string;
  exists: boolean;
  writable: boolean;
  writable_direct?: boolean;
  writable_via_sudo?: boolean;
  content: string;
  error?: string | null;
};

type ConfigFilesResponse = {
  success: boolean;
  files: ConfigFileItem[];
};

type CatalogEntry = {
  key: string;
  field?: string;
  scope: "ogscope" | "network" | "both";
  default?: string | null;
  zh: string;
  en: string;
};

type CatalogSection = {
  id: string;
  title_zh: string;
  title_en: string;
  scope: "ogscope" | "network" | "both";
  entries: CatalogEntry[];
};

type ConfigCatalogResponse = {
  success: boolean;
  env_prefix: string;
  env_files: Record<string, string>;
  sections: CatalogSection[];
  network_only: CatalogEntry[];
};

type EditorMode = "form" | "raw";

type EnvEntry = {
  id: string;
  key: string;
  value: string;
};

const FILE_LABELS: Record<string, { zh: string; en: string }> = {
  ogscope: { zh: "主配置 ogscope.env", en: "Primary ogscope.env" },
  network: { zh: "网络 network.env", en: "Network network.env" },
};

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

function scopeMatchesFile(scope: CatalogEntry["scope"], fileId: string): boolean {
  if (scope === "both") return true;
  return scope === fileId;
}

export function ConfigPage() {
  const { locale } = useI18n();
  const [files, setFiles] = useState<ConfigFileItem[]>([]);
  const [catalog, setCatalog] = useState<ConfigCatalogResponse | null>(null);
  const [activeId, setActiveId] = useState<string>("");
  const [editor, setEditor] = useState("");
  const [mode, setMode] = useState<EditorMode>("form");
  const [formEntries, setFormEntries] = useState<EnvEntry[]>([]);
  const [unsupportedLines, setUnsupportedLines] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [search, setSearch] = useState("");
  const [glossaryOpen, setGlossaryOpen] = useState(true);
  const [catalogPick, setCatalogPick] = useState("");

  const isZh = locale === "zh";

  const activeFile = useMemo(
    () => files.find((item) => item.file_id === activeId) ?? null,
    [activeId, files],
  );

  const hintMap = useMemo(() => {
    const map = new Map<string, CatalogEntry>();
    for (const section of catalog?.sections ?? []) {
      for (const entry of section.entries) {
        map.set(entry.key.toUpperCase(), entry);
      }
    }
    for (const entry of catalog?.network_only ?? []) {
      map.set(entry.key.toUpperCase(), entry);
    }
    return map;
  }, [catalog]);

  const catalogOptions = useMemo(() => {
    if (!activeId) return [];
    const existing = new Set(formEntries.map((e) => e.key.trim().toUpperCase()).filter(Boolean));
    const options: CatalogEntry[] = [];
    for (const section of catalog?.sections ?? []) {
      for (const entry of section.entries) {
        if (!scopeMatchesFile(entry.scope, activeId)) continue;
        if (existing.has(entry.key.toUpperCase())) continue;
        options.push(entry);
      }
    }
    for (const entry of catalog?.network_only ?? []) {
      if (!scopeMatchesFile(entry.scope, activeId)) continue;
      if (existing.has(entry.key.toUpperCase())) continue;
      options.push(entry);
    }
    return options.sort((a, b) => a.key.localeCompare(b.key));
  }, [activeId, catalog, formEntries]);

  const filteredFormEntries = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return formEntries;
    return formEntries.filter((entry) => {
      const key = entry.key.toLowerCase();
      const hint = hintMap.get(entry.key.trim().toUpperCase());
      const text = `${key} ${entry.value} ${hint?.zh ?? ""} ${hint?.en ?? ""}`.toLowerCase();
      return text.includes(q);
    });
  }, [formEntries, hintMap, search]);

  const reloadFormFromRaw = (raw: string) => {
    const parsed = parseEnvEntries(raw);
    setFormEntries(parsed.entries);
    setUnsupportedLines(parsed.unsupportedLines);
  };

  const loadAll = async () => {
    setBusy(true);
    setError("");
    try {
      const [filesPayload, catalogPayload] = await Promise.all([
        requestJson<ConfigFilesResponse>("/api/dev/system/config/files", { cache: "no-store" }),
        requestJson<ConfigCatalogResponse>("/api/dev/system/config/catalog", { cache: "no-store" }),
      ]);
      setFiles(filesPayload.files ?? []);
      setCatalog(catalogPayload);
      const nextId = filesPayload.files?.[0]?.file_id ?? "";
      setActiveId((prev) =>
        prev && filesPayload.files?.some((f) => f.file_id === prev) ? prev : nextId,
      );
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
          ? "当前文件包含无法表单化的行，请切换到「原始文本」模式编辑后再保存。"
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
          ? `保存成功：${result.message ?? activeId}；请重启 ogscope 服务使配置生效`
          : `Saved: ${result.message ?? activeId}; restart ogscope to apply changes`,
      );
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void loadAll();
  }, []);

  useEffect(() => {
    if (!activeFile) {
      setEditor("");
      setFormEntries([]);
      setUnsupportedLines(0);
      setCatalogPick("");
      return;
    }
    const nextRaw = activeFile.content ?? "";
    setEditor(nextRaw);
    reloadFormFromRaw(nextRaw);
    setCatalogPick("");
  }, [activeFile]);

  const addEntry = () => {
    setFormEntries((prev) => [
      ...prev,
      { id: `env-new-${Date.now()}-${prev.length}`, key: "", value: "" },
    ]);
  };

  const addFromCatalog = () => {
    const picked = catalogOptions.find((item) => item.key === catalogPick);
    if (!picked) return;
    setFormEntries((prev) => [
      ...prev,
      {
        id: `env-catalog-${Date.now()}-${picked.key}`,
        key: picked.key,
        value: picked.default ?? "",
      },
    ]);
    setCatalogPick("");
  };

  const updateEntry = (id: string, patch: Partial<EnvEntry>) => {
    setFormEntries((prev) => prev.map((entry) => (entry.id === id ? { ...entry, ...patch } : entry)));
  };

  const removeEntry = (id: string) => {
    setFormEntries((prev) => prev.filter((entry) => entry.id !== id));
  };

  const configHintText = (key: string) => {
    const hint = hintMap.get(key.trim().toUpperCase());
    if (!hint) return isZh ? "暂无释义（可查阅 deploy/*.env.example）" : "No hint (see deploy/*.env.example)";
    return isZh ? hint.zh : hint.en;
  };

  const defaultHintText = (key: string) => {
    const hint = hintMap.get(key.trim().toUpperCase());
    if (!hint?.default) return "";
    return isZh ? `默认：${hint.default}` : `Default: ${hint.default}`;
  };

  const fileLabel = (fileId: string) => {
    const label = FILE_LABELS[fileId];
    return label ? (isZh ? label.zh : label.en) : fileId;
  };

  const writableHint = (file: ConfigFileItem) => {
    if (!file.writable) {
      return isZh
        ? "不可写：请运行 sudo ./scripts/ogscope-network-init.sh ensure-config"
        : "Not writable: run sudo ./scripts/ogscope-network-init.sh ensure-config";
    }
    if (file.writable_via_sudo && !file.writable_direct) {
      return isZh ? "可写（经 sudo 助手）" : "Writable (via sudo helper)";
    }
    if (file.writable_direct) {
      return isZh ? "可写（直接）" : "Writable (direct)";
    }
    return isZh ? "可写" : "Writable";
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
            ? "编辑 /etc/ogscope 下的 ogscope.env 与 network.env。保存后请重启 ogscope 服务；配置项说明来自服务端目录 API。"
            : "Edit ogscope.env and network.env under /etc/ogscope. Restart ogscope after saving; hints come from the server catalog API."}
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
            <button type="button" onClick={() => void loadAll()} disabled={busy}>
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
              <div className="font-medium">{fileLabel(file.file_id)}</div>
              <div className="mt-1 truncate font-mono text-[11px]">{file.path}</div>
            </button>
          ))}
          {catalog?.env_files && (
            <div className="mt-3 rounded border border-outline-variant/20 bg-surface-container-low px-2 py-2 text-[11px] text-on-surface-variant">
              <p className="mb-1 font-medium text-on-surface">{isZh ? "配置路径" : "Config paths"}</p>
              {Object.entries(catalog.env_files).map(([id, path]) => (
                <p key={id} className="font-mono">
                  {id}: {path}
                </p>
              ))}
            </div>
          )}
        </aside>

        <div className="col-span-12 rounded-xl border border-outline-variant/20 bg-surface-container p-4 lg:col-span-9">
          {!activeFile && (
            <p className="text-sm text-on-surface-variant">{isZh ? "暂无可编辑配置文件" : "No editable config files."}</p>
          )}
          {activeFile && (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="font-mono text-xs text-on-surface">{activeFile.path}</p>
                  <p className="text-xs text-on-surface-variant">
                    {writableHint(activeFile)} · {isZh ? "存在" : "Exists"}: {String(activeFile.exists)}
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
                        ? `检测到 ${unsupportedLines} 行无法转换为键值表单。请切到「原始文本」模式处理。`
                        : `${unsupportedLines} line(s) cannot be represented in key-value form. Use Raw mode.`}
                    </div>
                  )}
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="relative min-w-[200px] flex-1">
                      <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-on-surface-variant" />
                      <input
                        className="w-full rounded border border-outline-variant/30 bg-surface-container-low py-1.5 pl-8 pr-2 text-xs outline-none focus:border-primary"
                        placeholder={isZh ? "搜索键名、值或释义…" : "Search keys, values, or hints…"}
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                      />
                    </div>
                    <select
                      className="max-w-xs flex-1 rounded border border-outline-variant/30 bg-surface-container-low px-2 py-1.5 text-xs outline-none focus:border-primary"
                      value={catalogPick}
                      onChange={(e) => setCatalogPick(e.target.value)}
                    >
                      <option value="">
                        {isZh ? "从目录添加配置项…" : "Add from catalog…"}
                      </option>
                      {catalogOptions.map((item) => (
                        <option key={item.key} value={item.key}>
                          {item.key}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      disabled={!catalogPick}
                      onClick={addFromCatalog}
                      className="rounded border border-outline-variant/30 px-2 py-1.5 text-xs disabled:opacity-50"
                    >
                      {isZh ? "添加" : "Add"}
                    </button>
                  </div>
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
                        {filteredFormEntries.map((entry) => (
                          <tr key={entry.id}>
                            <td className="pr-2 align-top">
                              <input
                                className="w-full rounded border border-outline-variant/30 bg-surface-container-low px-2 py-1 font-mono text-xs outline-none focus:border-primary"
                                placeholder="OGSCOPE_PORT"
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
                              <p>{configHintText(entry.key)}</p>
                              {defaultHintText(entry.key) && (
                                <p className="mt-0.5 font-mono text-[10px] text-on-surface-variant/80">
                                  {defaultHintText(entry.key)}
                                </p>
                              )}
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
                        {isZh ? "当前没有可编辑变量，可从目录添加或手动新增。" : "No variables yet. Add from catalog or manually."}
                      </div>
                    )}
                    {formEntries.length > 0 && filteredFormEntries.length === 0 && (
                      <div className="rounded border border-outline-variant/20 bg-surface-container-low px-2 py-2 text-xs text-on-surface-variant">
                        {isZh ? "无匹配项，请调整搜索条件。" : "No matches for the current search."}
                      </div>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button type="button" onClick={addEntry}>
                      <span className="inline-flex items-center gap-1 text-xs">
                        <Plus className="h-3.5 w-3.5" />
                        {isZh ? "空白行" : "Blank row"}
                      </span>
                    </button>
                  </div>
                  <details
                    open={glossaryOpen}
                    onToggle={(e) => setGlossaryOpen((e.target as HTMLDetailsElement).open)}
                    className="rounded border border-outline-variant/20 bg-surface-container-low px-3 py-2 text-xs text-on-surface-variant"
                  >
                    <summary className="cursor-pointer font-medium text-on-surface">
                      <span className="inline-flex items-center gap-1">
                        <BookOpen className="h-3.5 w-3.5" />
                        {isZh ? "配置目录（按模块）" : "Config catalog (by section)"}
                      </span>
                    </summary>
                    <div className="mt-3 space-y-4">
                      {(catalog?.sections ?? []).map((section) => {
                        const entries = section.entries.filter((entry) =>
                          activeId ? scopeMatchesFile(entry.scope, activeId) : true,
                        );
                        if (entries.length === 0) return null;
                        return (
                          <div key={section.id}>
                            <p className="mb-1 font-medium text-on-surface">
                              {isZh ? section.title_zh : section.title_en}
                            </p>
                            <div className="space-y-1">
                              {entries.map((entry) => (
                                <p key={entry.key}>
                                  <span className="font-mono text-[11px] text-on-surface">{entry.key}</span>
                                  {entry.default != null && entry.default !== "" && (
                                    <span className="ml-1 font-mono text-[10px] text-on-surface-variant/80">
                                      (= {entry.default})
                                    </span>
                                  )}
                                  {" — "}
                                  <span>{isZh ? entry.zh : entry.en}</span>
                                </p>
                              ))}
                            </div>
                          </div>
                        );
                      })}
                      {(catalog?.network_only ?? []).filter((entry) =>
                        activeId ? scopeMatchesFile(entry.scope, activeId) : true,
                      ).length > 0 && (
                        <div>
                          <p className="mb-1 font-medium text-on-surface">
                            {isZh ? "仅 network.env / 脚本" : "network.env / scripts only"}
                          </p>
                          <div className="space-y-1">
                            {(catalog?.network_only ?? [])
                              .filter((entry) => (activeId ? scopeMatchesFile(entry.scope, activeId) : true))
                              .map((entry) => (
                                <p key={entry.key}>
                                  <span className="font-mono text-[11px] text-on-surface">{entry.key}</span>
                                  {" — "}
                                  <span>{isZh ? entry.zh : entry.en}</span>
                                </p>
                              ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </details>
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
