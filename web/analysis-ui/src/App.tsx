import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Database,
  FlaskConical,
  History,
  Home,
  Loader2,
  RefreshCw,
  Upload,
} from "lucide-react";
import {
  BatchRun,
  fetchExperiments,
  fetchPresets,
  fetchUploads,
  importFromDebug,
  saveExperiment,
  saveUserPreset,
  solveBatch,
  solveImage,
  uploadFile,
  uploadFileUrl,
  exportExperiments,
  type SolveParams,
  type UploadFileRow,
} from "./api";
import { drawSolveOverlay, type SolveOverlay } from "./drawOverlay";

type View = "lab" | "pool" | "history";

const defaultParams = (): SolveParams => ({
  hint_ra_deg: 45,
  hint_dec_deg: 80,
  fov_estimate: 16,
  fov_max_error: undefined,
  solve_timeout_ms: 8000,
  max_image_side: 2048,
  centroid: {
    sigma: 2.5,
    max_area: 400,
    min_area: 5,
    filtsize: 25,
    binary_open: true,
    max_axis_ratio: undefined,
  },
});

function metricsFromResult(result: Record<string, unknown> | null): Record<string, unknown> {
  if (!result) return {};
  return {
    matches: result.matches,
    rmse_arcsec: result.rmse_arcsec,
    status: result.status,
    prob: result.prob,
    t_solve_ms: result.t_solve_ms,
  };
}

export default function App() {
  const [view, setView] = useState<View>("lab");
  const [uploads, setUploads] = useState<UploadFileRow[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [params, setParams] = useState<SolveParams>(defaultParams);
  const [official, setOfficial] = useState<
    Array<{ id: string; name: string; params: SolveParams }>
  >([]);
  const [userPresets, setUserPresets] = useState<
    Array<{ id: string; name: string; params: SolveParams }>
  >([]);
  const [selectedPresetIds, setSelectedPresetIds] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<Record<string, unknown> | null>(null);
  const [batchPack, setBatchPack] = useState<{
    results: Array<Record<string, unknown>>;
  } | null>(null);
  const [historyQ, setHistoryQ] = useState("");
  const [historyPage, setHistoryPage] = useState(1);
  const [historyData, setHistoryData] = useState<{ items: unknown[]; total: number } | null>(
    null
  );
  const [debugImportName, setDebugImportName] = useState("");
  const [newPresetName, setNewPresetName] = useState("");
  const [layers, setLayers] = useState({ matched: true, pattern: true, all: true });

  const imgRef = useRef<HTMLImageElement>(null);
  const cvRef = useRef<HTMLCanvasElement>(null);

  const loadLists = useCallback(async () => {
    const [u, o, usr] = await Promise.all([
      fetchUploads(),
      fetchPresets("official"),
      fetchPresets("user"),
    ]);
    setUploads(u.files);
    setOfficial(o.presets as typeof official);
    setUserPresets(usr.presets as typeof userPresets);
  }, []);

  useEffect(() => {
    loadLists().catch((e) => setErr(String(e)));
  }, [loadLists]);

  useEffect(() => {
    if (view !== "history") return;
    fetchExperiments(historyQ, historyPage)
      .then(setHistoryData)
      .catch((e) => setErr(String(e)));
  }, [view, historyQ, historyPage]);

  const overlay = useMemo(() => {
    const r = lastResult?.result as Record<string, unknown> | undefined;
    if (!r) return null;
    return (r.solve_overlay || null) as SolveOverlay | null;
  }, [lastResult]);

  useEffect(() => {
    const img = imgRef.current;
    const cv = cvRef.current;
    if (!img || !cv || !overlay || !selected) return;
    const draw = () => drawSolveOverlay(cv, img, overlay, layers);
    if (img.complete) draw();
    else img.onload = draw;
  }, [overlay, selected, lastResult, layers]);

  const previewUrl = selected ? uploadFileUrl(selected) : "";

  const applyPreset = (p: SolveParams) => {
    setParams({
      ...defaultParams(),
      ...p,
      centroid: { ...defaultParams().centroid, ...p.centroid },
    });
  };

  const onSingleSolve = async () => {
    if (!selected) {
      setErr("请选择素材 / Select a file");
      return;
    }
    setErr(null);
    setBusy(true);
    try {
      const out = (await solveImage(selected, params)) as { result?: Record<string, unknown> };
      setLastResult(out as Record<string, unknown>);
      setBatchPack(null);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  const onBatch = async () => {
    if (!selected) {
      setErr("请选择素材 / Select a file");
      return;
    }
    const runs: BatchRun[] = [];
    for (const id of selectedPresetIds) {
      const all = [...official, ...userPresets];
      const pr = all.find((x) => x.id === id);
      if (pr) runs.push({ label: pr.name, params: pr.params });
    }
    if (runs.length === 0) {
      setErr("请勾选至少一个预设 / Select presets");
      return;
    }
    setErr(null);
    setBusy(true);
    try {
      const pack = (await solveBatch(selected, runs)) as { results: unknown[] };
      setBatchPack({
        results: pack.results as Array<Record<string, unknown>>,
      });
      setLastResult(null);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  const togglePreset = (id: string) => {
    setSelectedPresetIds((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  };

  return (
    <div className="flex min-h-full flex-col bg-surface text-on-surface">
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-outline-variant/20 px-4">
        <div className="flex items-center gap-6">
          <span className="font-headline text-sm font-bold tracking-wide text-on-surface">
            OGScope 星图解算实验室
          </span>
          <nav className="flex gap-4 text-xs">
            <button
              type="button"
              className={view === "lab" ? "text-primary" : "text-on-surface-variant"}
              onClick={() => setView("lab")}
            >
              Lab
            </button>
            <button
              type="button"
              className={view === "pool" ? "text-primary" : "text-on-surface-variant"}
              onClick={() => setView("pool")}
            >
              素材池
            </button>
            <button
              type="button"
              className={view === "history" ? "text-primary" : "text-on-surface-variant"}
              onClick={() => setView("history")}
            >
              实验记录
            </button>
          </nav>
        </div>
        <div className="flex gap-2">
          <a
            className="flex items-center gap-1 rounded border border-outline-variant/30 px-2 py-1 text-xs text-on-surface-variant hover:bg-surface-container"
            href="/debug"
          >
            <FlaskConical className="h-3.5 w-3.5" /> 调试控制台
          </a>
          <a
            className="flex items-center gap-1 rounded border border-outline-variant/30 px-2 py-1 text-xs text-on-surface-variant hover:bg-surface-container"
            href="/"
          >
            <Home className="h-3.5 w-3.5" /> 首页
          </a>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <aside className="w-56 shrink-0 border-r border-outline-variant/15 bg-surface-container-lowest p-4 text-xs">
          <div className="mb-4 font-semibold text-on-surface-variant">素材</div>
          <label className="mb-3 flex cursor-pointer items-center gap-2 rounded bg-primary-container/30 px-2 py-2 text-on-primary-container">
            <Upload className="h-4 w-4" />
            <span>上传文件</span>
            <input
              type="file"
              accept="image/*,video/*"
              className="hidden"
              onChange={async (e) => {
                const f = e.target.files?.[0];
                if (!f) return;
                setBusy(true);
                setErr(null);
                try {
                  const r = await uploadFile(f);
                  await loadLists();
                  setSelected(r.filename);
                } catch (ex) {
                  setErr(String(ex));
                } finally {
                  setBusy(false);
                  e.target.value = "";
                }
              }}
            />
          </label>
          <button
            type="button"
            className="mb-2 flex w-full items-center gap-1 text-left text-on-surface-variant hover:text-on-surface"
            onClick={() => loadLists().catch((e) => setErr(String(e)))}
          >
            <RefreshCw className="h-3 w-3" /> 刷新列表
          </button>
          <div className="max-h-40 overflow-y-auto border-t border-outline-variant/10 pt-2">
            {uploads.map((u) => (
              <button
                key={u.filename}
                type="button"
                className={`mb-1 w-full truncate rounded px-2 py-1 text-left ${
                  selected === u.filename ? "bg-surface-container text-primary" : ""
                }`}
                onClick={() => {
                  setSelected(u.filename);
                  setView("lab");
                }}
                title={u.filename}
              >
                {u.filename}
              </button>
            ))}
          </div>
          <div className="mt-4 border-t border-outline-variant/10 pt-4">
            <div className="mb-2 font-semibold text-on-surface-variant">调试台导入</div>
            <input
              className="mb-1 w-full rounded bg-surface-container-highest px-2 py-1 text-[10px]"
              placeholder="dev_captures 内文件名"
              value={debugImportName}
              onChange={(e) => setDebugImportName(e.target.value)}
            />
            <button
              type="button"
              className="w-full rounded bg-surface-container py-1 text-[10px]"
              onClick={async () => {
                if (!debugImportName.trim()) return;
                setBusy(true);
                try {
                  const r = await importFromDebug(debugImportName.trim());
                  await loadLists();
                  setSelected(r.filename);
                  setView("lab");
                } catch (e) {
                  setErr(String(e));
                } finally {
                  setBusy(false);
                }
              }}
            >
              导入到素材池
            </button>
          </div>
          <div className="mt-4 border-t border-outline-variant/10 pt-4">
            <div className="mb-2 font-semibold text-on-surface-variant">批量预设</div>
            <div className="max-h-32 space-y-1 overflow-y-auto">
              {[...official, ...userPresets].map((p) => (
                <label key={p.id} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={selectedPresetIds.has(p.id)}
                    onChange={() => togglePreset(p.id)}
                  />
                  <span className="truncate">{p.name}</span>
                </label>
              ))}
            </div>
          </div>
        </aside>

        {view === "lab" && (
          <>
            <main className="min-w-0 flex-1 overflow-auto p-4">
              {err && (
                <div className="mb-2 rounded border border-error/40 bg-error-container/20 px-3 py-2 text-xs text-error">
                  {err}
                </div>
              )}
              <div className="relative aspect-video w-full max-w-5xl overflow-hidden rounded-lg border border-outline-variant/20 bg-surface-container-lowest">
                {selected ? (
                  <>
                    <img
                      ref={imgRef}
                      src={previewUrl}
                      alt="preview"
                      className="max-h-[70vh] w-full object-contain"
                    />
                    <canvas
                      ref={cvRef}
                      className="pointer-events-none absolute left-0 top-0"
                    />
                  </>
                ) : (
                  <div className="flex h-full items-center justify-center text-on-surface-variant">
                    选择左侧素材或上传
                  </div>
                )}
                {busy && (
                  <div className="absolute inset-0 flex items-center justify-center bg-black/40">
                    <Loader2 className="h-8 w-8 animate-spin text-primary" />
                  </div>
                )}
              </div>
              {selected && (
                <div className="mt-2 flex flex-wrap gap-4 text-xs text-on-surface-variant">
                  <span>文件: {selected}</span>
                  {uploads.find((u) => u.filename === selected)?.source && (
                    <span className="rounded bg-surface-container-high px-2 py-0.5">
                      来源: {uploads.find((u) => u.filename === selected)?.source}
                    </span>
                  )}
                </div>
              )}
              <div className="mt-4 flex flex-wrap gap-3 text-xs">
                <span className="text-on-surface-variant">叠加层:</span>
                {(["matched", "pattern", "all"] as const).map((k) => (
                  <label key={k} className="flex items-center gap-1">
                    <input
                      type="checkbox"
                      checked={layers[k]}
                      onChange={(e) =>
                        setLayers((L) => ({ ...L, [k]: e.target.checked }))
                      }
                    />
                    {k}
                  </label>
                ))}
              </div>
            </main>

            <aside className="w-80 shrink-0 overflow-y-auto border-l border-outline-variant/15 bg-surface-container-low p-4 text-xs">
              <h3 className="mb-3 font-semibold text-on-surface-variant">解算参数</h3>
              <div className="space-y-2">
                <Field
                  label="FOV 估计 (°)"
                  type="number"
                  value={params.fov_estimate ?? ""}
                  onChange={(v) => setParams((p) => ({ ...p, fov_estimate: v }))}
                />
                <Field
                  label="FOV 误差 (°)"
                  type="number"
                  value={params.fov_max_error ?? ""}
                  onChange={(v) => setParams((p) => ({ ...p, fov_max_error: v }))}
                />
                <Field
                  label="超时 (ms)"
                  type="number"
                  value={params.solve_timeout_ms ?? ""}
                  onChange={(v) => setParams((p) => ({ ...p, solve_timeout_ms: v }))}
                />
                <Field
                  label="RA 提示 (°)"
                  type="number"
                  value={params.hint_ra_deg ?? ""}
                  onChange={(v) => setParams((p) => ({ ...p, hint_ra_deg: v }))}
                />
                <Field
                  label="Dec 提示 (°)"
                  type="number"
                  value={params.hint_dec_deg ?? ""}
                  onChange={(v) => setParams((p) => ({ ...p, hint_dec_deg: v }))}
                />
                <Field
                  label="提星长边上界 (px)"
                  type="number"
                  value={params.max_image_side ?? ""}
                  onChange={(v) => setParams((p) => ({ ...p, max_image_side: v }))}
                />
              </div>
              <h3 className="mb-3 mt-6 font-semibold text-on-surface-variant">提星</h3>
              <div className="space-y-2">
                <Field
                  label="σ"
                  type="number"
                  step={0.1}
                  value={params.centroid?.sigma ?? ""}
                  onChange={(v) =>
                    setParams((p) => ({
                      ...p,
                      centroid: { ...p.centroid, sigma: v },
                    }))
                  }
                />
                <Field
                  label="max_area"
                  type="number"
                  value={params.centroid?.max_area ?? ""}
                  onChange={(v) =>
                    setParams((p) => ({
                      ...p,
                      centroid: { ...p.centroid, max_area: v },
                    }))
                  }
                />
                <Field
                  label="min_area"
                  type="number"
                  value={params.centroid?.min_area ?? ""}
                  onChange={(v) =>
                    setParams((p) => ({
                      ...p,
                      centroid: { ...p.centroid, min_area: v },
                    }))
                  }
                />
                <Field
                  label="filtsize (奇数)"
                  type="number"
                  step={2}
                  value={params.centroid?.filtsize ?? ""}
                  onChange={(v) =>
                    setParams((p) => ({
                      ...p,
                      centroid: { ...p.centroid, filtsize: v },
                    }))
                  }
                />
              </div>
              <div className="mt-4 space-y-2">
                <button
                  type="button"
                  className="w-full rounded bg-primary py-2 font-semibold text-on-primary-container"
                  onClick={onSingleSolve}
                  disabled={busy}
                >
                  单张解算
                </button>
                <button
                  type="button"
                  className="w-full rounded bg-secondary/80 py-2 font-semibold text-on-secondary"
                  onClick={onBatch}
                  disabled={busy}
                >
                  批量解算（勾选预设）
                </button>
              </div>
              <div className="mt-6 border-t border-outline-variant/20 pt-4">
                <div className="mb-2 font-semibold">应用预设到表单</div>
                <div className="max-h-24 space-y-1 overflow-y-auto">
                  {[...official, ...userPresets].map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      className="block w-full truncate text-left text-primary hover:underline"
                      onClick={() => applyPreset(p.params)}
                    >
                      {p.name}
                    </button>
                  ))}
                </div>
                <div className="mt-3 flex gap-1">
                  <input
                    className="flex-1 rounded bg-surface-container-highest px-2 py-1"
                    placeholder="新预设名称"
                    value={newPresetName}
                    onChange={(e) => setNewPresetName(e.target.value)}
                  />
                  <button
                    type="button"
                    className="rounded bg-surface-container-high px-2"
                    onClick={async () => {
                      if (!newPresetName.trim()) return;
                      setBusy(true);
                      try {
                        await saveUserPreset(newPresetName.trim(), params);
                        setNewPresetName("");
                        await loadLists();
                        const usr = await fetchPresets("user");
                        setUserPresets(usr.presets as typeof userPresets);
                      } catch (e) {
                        setErr(String(e));
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    保存
                  </button>
                </div>
              </div>
            </aside>
          </>
        )}

        {view === "pool" && (
          <main className="flex-1 overflow-auto p-4">
            <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold">
              <Database className="h-5 w-5" /> 服务器素材池
            </h2>
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-outline-variant/30 text-on-surface-variant">
                  <th className="py-2">文件名</th>
                  <th className="py-2">来源</th>
                  <th className="py-2">大小</th>
                  <th className="py-2">修改时间</th>
                </tr>
              </thead>
              <tbody>
                {uploads.map((u) => (
                  <tr key={u.filename} className="border-b border-outline-variant/10">
                    <td className="py-2 font-mono">{u.filename}</td>
                    <td className="py-2">{u.source ?? "—"}</td>
                    <td className="py-2">{u.size}</td>
                    <td className="py-2">{u.modified_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </main>
        )}

        {view === "history" && (
          <main className="flex-1 overflow-auto p-4">
            <div className="mb-4 flex items-center gap-4">
              <h2 className="flex items-center gap-2 text-lg font-semibold">
                <History className="h-5 w-5" /> 实验记录
              </h2>
              <input
                className="rounded bg-surface-container-highest px-2 py-1 text-xs"
                placeholder="搜索…"
                value={historyQ}
                onChange={(e) => setHistoryQ(e.target.value)}
              />
              <button
                type="button"
                className="rounded bg-surface-container px-2 py-1 text-xs"
                onClick={() =>
                  fetchExperiments(historyQ, historyPage).then(setHistoryData)
                }
              >
                搜索
              </button>
              <button
                type="button"
                className="rounded bg-primary-container/50 px-2 py-1 text-xs"
                onClick={() =>
                  exportExperiments("json").then((t) => {
                    const blob = new Blob([t], { type: "application/json" });
                    const a = document.createElement("a");
                    a.href = URL.createObjectURL(blob);
                    a.download = "experiments.json";
                    a.click();
                  })
                }
              >
                导出 JSON
              </button>
              <button
                type="button"
                className="rounded bg-primary-container/50 px-2 py-1 text-xs"
                onClick={() =>
                  exportExperiments("csv").then((t) => {
                    const blob = new Blob([t], { type: "text/csv" });
                    const a = document.createElement("a");
                    a.href = URL.createObjectURL(blob);
                    a.download = "experiments.csv";
                    a.click();
                  })
                }
              >
                导出 CSV
              </button>
            </div>
            <div className="text-xs text-on-surface-variant">
              共 {historyData?.total ?? 0} 条
            </div>
            <ul className="mt-2 space-y-2">
              {(historyData?.items as Array<Record<string, unknown>>)?.map((row) => (
                <li
                  key={String(row.id)}
                  className="rounded border border-outline-variant/20 p-2 font-mono text-[11px]"
                >
                  {String(row.created_at)} — {String(row.input_name)} —{" "}
                  {String(row.preset_label)}
                </li>
              ))}
            </ul>
          </main>
        )}
      </div>

      {view === "lab" && (
        <footer className="h-40 shrink-0 overflow-hidden border-t border-outline-variant/20 bg-surface-container-lowest/95">
          <div className="flex h-9 items-center justify-between border-b border-outline-variant/15 px-4 text-[10px] uppercase text-on-surface-variant">
            <span>结果对比 / Results</span>
            {lastResult && (
              <button
                type="button"
                className="rounded bg-surface-container px-2 py-0.5"
                onClick={async () => {
                  if (!selected) return;
                  const res = lastResult.result as Record<string, unknown> | undefined;
                  await saveExperiment({
                    input_name: selected,
                    preset_label: "manual",
                    result_json: lastResult,
                    metrics: metricsFromResult(res ?? null),
                  });
                  setErr(null);
                }}
              >
                保存当前到实验记录
              </button>
            )}
          </div>
          <div className="flex gap-3 overflow-x-auto p-3 text-xs">
            {batchPack?.results.map((r, i) => (
              <div
                key={i}
                className="w-56 shrink-0 rounded border border-outline-variant/20 bg-surface-container p-2"
              >
                <div className="font-semibold text-secondary">{String(r.label)}</div>
                {r.success ? (
                  <pre className="mt-1 max-h-24 overflow-auto text-[10px] text-on-surface-variant">
                    {JSON.stringify(r.result, null, 1)}
                  </pre>
                ) : (
                  <div className="text-error">{String(r.error)}</div>
                )}
                {r.success && selected && (
                  <button
                    type="button"
                    className="mt-2 w-full rounded bg-surface-container-high py-1 text-[10px]"
                    onClick={() =>
                      saveExperiment({
                        input_name: selected,
                        preset_label: String(r.label),
                        result_json: r,
                        metrics: metricsFromResult(
                          (r.result as Record<string, unknown> | null) ?? null
                        ),
                      }).catch((e) => setErr(String(e)))
                    }
                  >
                    保存记录
                  </button>
                )}
              </div>
            ))}
            {lastResult && !batchPack && (
              <div className="w-full max-w-xl rounded border border-outline-variant/20 bg-surface-container p-2">
                <pre className="max-h-28 overflow-auto text-[10px]">
                  {JSON.stringify(lastResult, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </footer>
      )}
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "number",
  step,
}: {
  label: string;
  value: number | "";
  onChange: (v: number | undefined) => void;
  type?: string;
  step?: number;
}) {
  return (
    <label className="block">
      <span className="text-[10px] text-on-surface-variant">{label}</span>
      <input
        type={type}
        step={step}
        className="mt-0.5 w-full rounded bg-surface-container-highest px-2 py-1"
        value={value === "" ? "" : value}
        onChange={(e) => {
          const t = e.target.value;
          if (t === "") onChange(undefined);
          else onChange(type === "number" ? Number(t) : Number(t));
        }}
      />
    </label>
  );
}
