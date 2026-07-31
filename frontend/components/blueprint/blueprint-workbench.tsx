"use client";

import {
  ArrowLeft,
  BookOpenText,
  LoaderCircle,
  Plus,
  RefreshCw,
  Settings2,
  X,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  NINE_LINES,
  type NodeStatus,
  type OutlineNode,
  type OutlineNodeMeta,
  type PacingConfig,
  type PlotLedgerEntry,
  type SweetPoint,
  type UpdateNodePayload,
  generateBlueprint,
  getBlueprint,
  getJob,
  getPlotLedger,
  getPacingConfig,
  updateBlueprintNode,
  updatePacingConfig,
} from "@/lib/blueprint";
import { useAppStore } from "@/lib/store";

import { LayerTree } from "./layer-tree";
import { NineLines } from "./nine-lines";
import { PacingDrawer } from "./pacing-drawer";
import { PlotLedger } from "./plot-ledger";
import { StageMap } from "./stage-map";
import { StatusBadge, SweetPointMarks } from "./shared";

type ViewKey = "stage" | "nine" | "ledger" | "tree";
const VIEWS: { key: ViewKey; label: string }[] = [
  { key: "stage", label: "阶段地图" },
  { key: "nine", label: "九线泳道" },
  { key: "ledger", label: "伏笔登记表" },
  { key: "tree", label: "层级树" },
];

export function BlueprintWorkbench({ projectId }: { projectId: string }) {
  const { token, hydrate } = useAppStore();
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nodes, setNodes] = useState<OutlineNode[]>([]);
  const [ledger, setLedger] = useState<PlotLedgerEntry[]>([]);
  const [pacing, setPacing] = useState<PacingConfig | null>(null);
  const [view, setView] = useState<ViewKey>("stage");
  const [generatingIds, setGeneratingIds] = useState<Set<string>>(new Set());
  const [generatingAll, setGeneratingAll] = useState(false);
  const [editing, setEditing] = useState<OutlineNode | null>(null);
  const [pacingOpen, setPacingOpen] = useState(false);
  const [pacingSaving, setPacingSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const authToken = useCallback((): string | null => {
    const value = token ?? (typeof window !== "undefined" ? window.localStorage.getItem("fushengliunian.token") : null);
    if (!value) setError("登录状态已失效，请重新登录后继续");
    return value;
  }, [token]);

  const loadAll = useCallback(async () => {
    const current = authToken();
    if (!current) return;
    setLoading(true);
    setError(null);
    try {
      const [blueprint, plot, config] = await Promise.all([
        getBlueprint(projectId, current).catch(() => ({ nodes: [] as OutlineNode[] })),
        getPlotLedger(projectId, current).catch(() => ({ entries: [] as PlotLedgerEntry[] })),
        getPacingConfig(projectId, current).catch(() => null),
      ]);
      setNodes(blueprint.nodes ?? []);
      setLedger(plot.entries ?? []);
      setPacing(config);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "蓝图加载失败");
    } finally {
      setLoading(false);
    }
  }, [authToken, projectId]);

  useEffect(() => {
    hydrate();
    setReady(true);
  }, [hydrate]);

  useEffect(() => {
    if (ready) void loadAll();
  }, [ready, loadAll]);

  const segments = useMemo(() => nodes.filter((node) => node.layer === "L4").sort((a, b) => a.seq - b.seq), [nodes]);

  const pollJob = useCallback(async (jobId: string) => {
    const current = authToken();
    if (!current) return;
    for (let attempt = 0; attempt < 120; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 1500));
      try {
        const status = await getJob(jobId, current);
        if (status.status === "completed") return true;
        if (status.status === "failed") {
          setError(status.error || "AI 生成失败，请重试");
          return false;
        }
      } catch {
        // 轮询中断后继续尝试
      }
    }
    setError("AI 生成超时，请稍后刷新查看结果");
    return false;
  }, [authToken]);

  async function regenerateSegment(node: OutlineNode) {
    const current = authToken();
    if (!current) return;
    setGeneratingIds((prev) => new Set(prev).add(node.id));
    setNotice(null);
    try {
      const { job_id } = await generateBlueprint(projectId, { layer: "L4", regenerate_node_id: node.id }, current);
      const done = await pollJob(job_id);
      if (done) await loadAll();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "重出失败");
    } finally {
      setGeneratingIds((prev) => {
        const next = new Set(prev);
        next.delete(node.id);
        return next;
      });
    }
  }

  async function generateStages() {
    const current = authToken();
    if (!current) return;
    setGeneratingAll(true);
    setNotice(null);
    try {
      const { job_id } = await generateBlueprint(projectId, { layer: "L4" }, current);
      const done = await pollJob(job_id);
      if (done) {
        await loadAll();
        setNotice("阶段规划已生成，可逐段查看与编辑");
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "生成失败");
    } finally {
      setGeneratingAll(false);
    }
  }

  async function changeStatus(node: OutlineNode, status: NodeStatus) {
    const current = authToken();
    if (!current) return;
    try {
      const updated = await updateBlueprintNode(node.id, { status }, current);
      setNodes((prev) => prev.map((item) => (item.id === node.id ? updated : item)));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "状态更新失败");
    }
  }

  async function saveNode(payload: UpdateNodePayload) {
    if (!editing) return;
    const current = authToken();
    if (!current) return;
    try {
      const updated = await updateBlueprintNode(editing.id, payload, current);
      setNodes((prev) => prev.map((item) => (item.id === editing.id ? updated : item)));
      setEditing(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存失败");
    }
  }

  async function savePacing(config: PacingConfig) {
    const current = authToken();
    if (!current) return;
    setPacingSaving(true);
    try {
      const saved = await updatePacingConfig(projectId, config, current);
      setPacing(saved);
      setPacingOpen(false);
      setNotice("节奏参数已保存");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "节奏参数保存失败");
    } finally {
      setPacingSaving(false);
    }
  }

  return (
    <main className="min-h-screen pb-10">
      <header className="border-b border-black/10 bg-[#f8f5ee]/90 backdrop-blur-xl">
        <div className="app-frame flex h-16 items-center justify-between">
          <Link href={`/workspace/${projectId}`} className="flex items-center gap-3 font-editorial text-lg font-bold">
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#20221f] text-white">
              <BookOpenText size={17} />
            </span>
            蓝图工作台
          </Link>
          <div className="flex items-center gap-2">
            <button className="secondary-button" type="button" onClick={() => setPacingOpen(true)}>
              <Settings2 size={16} />节奏参数
            </button>
            <Link href={`/workspace/${projectId}`} className="secondary-button">
              <ArrowLeft size={16} />返回工作台
            </Link>
          </div>
        </div>
      </header>

      <div className="app-frame pt-5">
        {error ? <div className="mb-4 rounded-md border border-[#a63f2f]/25 bg-[#fff0ed] px-4 py-3 text-sm text-[#8e3327]">{error}</div> : null}
        {notice ? <div className="mb-4 rounded-md border border-[#4e6859]/25 bg-[#edf1ec] px-4 py-3 text-sm text-[#3f5748]" onClick={() => setNotice(null)}>{notice}</div> : null}

        <div className="flex flex-wrap items-center justify-between gap-3">
          <nav className="flex flex-wrap gap-1 rounded-md border border-[#d8d1c4] bg-white/70 p-1">
            {VIEWS.map((item) => (
              <button
                key={item.key}
                type="button"
                className={`rounded px-3 py-1.5 text-sm font-semibold transition ${view === item.key ? "bg-[#20221f] text-white" : "text-[#5b5d56] hover:bg-[#f1ece1]"}`}
                onClick={() => setView(item.key)}
              >
                {item.label}
              </button>
            ))}
          </nav>
          {view === "stage" ? (
            <button className="primary-button" type="button" onClick={generateStages} disabled={generatingAll}>
              {generatingAll ? <LoaderCircle size={16} className="animate-spin" /> : <Plus size={16} />}
              {generatingAll ? "生成中" : "AI 生成阶段规划"}
            </button>
          ) : null}
        </div>

        <section className="surface mt-5 p-5 reveal">
          {loading ? (
            <div className="flex items-center justify-center gap-3 py-20 text-sm text-[#74756e]">
              <LoaderCircle className="animate-spin" size={18} />正在加载蓝图…
            </div>
          ) : (
            <>
              {view === "stage" ? <StageMap segments={segments} generatingIds={generatingIds} onEdit={setEditing} onRegenerate={regenerateSegment} /> : null}
              {view === "nine" ? <NineLines segments={segments} onEdit={setEditing} /> : null}
              {view === "ledger" ? <PlotLedger entries={ledger} /> : null}
              {view === "tree" ? <LayerTree nodes={nodes} onEdit={setEditing} onStatusChange={changeStatus} /> : null}
            </>
          )}
        </section>
      </div>

      {editing ? <NodeEditor node={editing} onClose={() => setEditing(null)} onSave={saveNode} /> : null}
      <PacingDrawer open={pacingOpen} initial={pacing} saving={pacingSaving} onClose={() => setPacingOpen(false)} onSave={savePacing} />
    </main>
  );
}

function NodeEditor({
  node,
  onClose,
  onSave,
}: {
  node: OutlineNode;
  onClose: () => void;
  onSave: (payload: UpdateNodePayload) => void;
}) {
  const [title, setTitle] = useState(node.title);
  const [body, setBody] = useState(node.body);
  const [keywords, setKeywords] = useState((node.meta.keywords ?? []).join("、"));
  const [nineLines, setNineLines] = useState<string[]>(node.meta.nine_lines ?? []);
  const [sweetPoints, setSweetPoints] = useState<SweetPoint[]>(node.meta.sweet_points ?? []);
  const [estChapters, setEstChapters] = useState<number>(node.meta.est_chapters ?? 0);
  const [saving, setSaving] = useState(false);

  function toggleLine(key: string) {
    setNineLines((prev) => (prev.includes(key) ? prev.filter((item) => item !== key) : [...prev, key]));
  }

  function updateSweet(index: number, field: keyof SweetPoint, value: string) {
    setSweetPoints((prev) => prev.map((item, i) => (i === index ? { ...item, [field]: value } : item)));
  }

  async function submit() {
    setSaving(true);
    const meta: OutlineNodeMeta = {
      keywords: keywords.split(/[，,、]/).map((item) => item.trim()).filter(Boolean),
      nine_lines: nineLines,
      sweet_points: sweetPoints.filter((item) => item.type.trim()),
      est_chapters: estChapters || undefined,
    };
    try {
      await onSave({ title: title.trim(), body, meta });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[80] flex justify-end bg-black/40 p-3 backdrop-blur-sm sm:p-6" role="dialog" aria-modal="true" aria-label="编辑节点">
      <div className="flex w-full max-w-md flex-col overflow-hidden bg-[#fbfaf6] shadow-2xl sm:rounded-md">
        <div className="flex items-start justify-between border-b border-[#ded8cd] px-5 py-4">
          <div className="flex items-center gap-2">
            <span className="rounded bg-[#20221f] px-1.5 py-0.5 text-[11px] font-bold text-white">{node.layer}</span>
            <h2 className="font-editorial text-xl font-bold">编辑节点</h2>
          </div>
          <button className="icon-button" type="button" onClick={onClose} title="关闭" aria-label="关闭"><X size={17} /></button>
        </div>

        <div className="scrollbar-thin flex-1 space-y-5 overflow-y-auto px-5 py-5">
          <label className="block">
            <span className="form-label">标题</span>
            <input className="field mt-1.5 h-10 px-3 font-normal" value={title} onChange={(event) => setTitle(event.target.value)} />
          </label>
          <label className="block">
            <span className="form-label">正文 / 描述</span>
            <textarea className="field mt-1.5 min-h-32 resize-y p-3 font-normal leading-6" value={body} onChange={(event) => setBody(event.target.value)} />
          </label>
          <label className="block">
            <span className="form-label">关键词（顿号或逗号分隔）</span>
            <input className="field mt-1.5 h-10 px-3 font-normal" value={keywords} onChange={(event) => setKeywords(event.target.value)} placeholder="例如：背叛、逆袭、密钥" />
          </label>
          <label className="block">
            <span className="form-label">预计章数</span>
            <input type="number" min={0} className="field mt-1.5 h-10 w-28 px-3 font-normal tabular-nums" value={estChapters} onChange={(event) => setEstChapters(Number(event.target.value) || 0)} />
          </label>

          <div>
            <span className="form-label">九线覆盖</span>
            <div className="mt-2 flex flex-wrap gap-2">
              {NINE_LINES.map((line) => {
                const on = nineLines.includes(line.key);
                return (
                  <button
                    key={line.key}
                    type="button"
                    onClick={() => toggleLine(line.key)}
                    className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold transition ${on ? "border-transparent text-white" : "border-[#d8d1c4] text-[#5b5d56]"}`}
                    style={on ? { backgroundColor: line.color } : undefined}
                  >
                    <span className="h-2 w-2 rounded-full" style={{ backgroundColor: on ? "#fff" : line.color }} />
                    {line.key}
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between">
              <span className="form-label">爽点标记</span>
              <button type="button" className="text-xs font-semibold text-[#a63f2f]" onClick={() => setSweetPoints((prev) => [...prev, { type: "", position: "" }])}>+ 添加</button>
            </div>
            {sweetPoints.length ? (
              <div className="mt-2 space-y-2">
                {sweetPoints.map((point, index) => (
                  <div key={index} className="flex items-center gap-2">
                    <input className="field h-9 flex-1 px-2 text-xs" placeholder="类型（如：扮猪吃虎）" value={point.type} onChange={(event) => updateSweet(index, "type", event.target.value)} />
                    <input className="field h-9 flex-1 px-2 text-xs" placeholder="落点（如：第3段）" value={point.position} onChange={(event) => updateSweet(index, "position", event.target.value)} />
                    <button type="button" className="icon-button h-8 w-8 text-[#a63f2f]" onClick={() => setSweetPoints((prev) => prev.filter((_, i) => i !== index))} title="删除"><X size={14} /></button>
                  </div>
                ))}
              </div>
            ) : (
              <p className="mt-2 text-xs text-[#8a8174]">暂未标记爽点</p>
            )}
          </div>
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-[#ded8cd] px-5 py-4">
          <StatusBadge status={node.status} />
          <div className="flex gap-2">
            <button className="secondary-button" type="button" onClick={onClose}>取消</button>
            <button className="primary-button" type="button" disabled={saving} onClick={submit}>
              {saving ? <LoaderCircle size={16} className="animate-spin" /> : <RefreshCw size={16} />}{saving ? "保存中" : "保存修改"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
