"use client";

import {
  BookOpen,
  Check,
  GitBranch,
  LoaderCircle,
  Scroll,
  Sparkles,
  Swords,
  Trash2,
  User2,
  Wand2,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import { useAppStore } from "@/lib/store";

type ImportedWork = {
  id: string;
  title: string;
  author: string | null;
  genre: string | null;
  total_chapters: number;
  total_words: number;
  analysis_status: string;
  analysis_progress: number;
  style_profile: Record<string, unknown> | null;
  breakpoint_analysis: Record<string, unknown> | null;
};

type AnalysisReport = {
  work: ImportedWork;
  characters: { slug: string; title: string; content: string }[];
  world_rules: { slug: string; title: string; content: string }[];
  foreshadowing: { content: string; planted_chapter: number; status: string; importance: string }[];
  power_system: { title: string; content: string } | null;
  thrill_formula: string | null;
  style_summary: string | null;
};

type AnalysisStatus = {
  analysis_status: string;
  analysis_progress: number;
  total_chapters: number;
  total_words: number;
  completed_chapters?: number;
  attempt?: number;
  error?: string | null;
};

type CodexEntry = {
  id: string;
  layer: "fact" | "narrative" | "style" | "dna";
  kind: string;
  title: string;
  content: Record<string, unknown>;
  confidence: number;
  user_verified: boolean;
};

type ActionMode = null | "continue" | "fanfic";
const DERIVATIVE_TARGETS = [
  { v: 100_000, l: "10万字" },
  { v: 300_000, l: "30万字" },
  { v: 1_000_000, l: "100万字" },
  { v: 2_000_000, l: "200万字" },
  { v: 3_000_000, l: "300万字" },
  { v: 5_000_000, l: "500万字" },
];

export default function ImportDetailPage() {
  const params = useParams();
  const router = useRouter();
  const token = useAppStore((s) => s.token);
  const workId = params.id as string;

  const [status, setStatus] = useState<AnalysisStatus | null>(null);
  const [report, setReport] = useState<AnalysisReport | null>(null);
  const [work, setWork] = useState<ImportedWork | null>(null);
  const [codex, setCodex] = useState<CodexEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionMode, setActionMode] = useState<ActionMode>(null);

  // Continuation state
  const [strategy, setStrategy] = useState<"faithful" | "accelerate" | "diverge">("faithful");
  const [contTargetWords, setContTargetWords] = useState(300000);

  // Fanfic state
  const [fanficType, setFanficType] = useState("what_if");
  const [fanficDesc, setFanficDesc] = useState("");
  const [fanficTargetWords, setFanficTargetWords] = useState(300000);

  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    if (!token) return;
    try {
      const st = await apiFetch<AnalysisStatus>(`/imported-works/${workId}/status`, {}, token);
      setStatus(st);

      if (st.analysis_status === "completed") {
        const rpt = await apiFetch<AnalysisReport>(`/imported-works/${workId}/report`, {}, token);
        setReport(rpt);
        setWork(rpt.work);
        const codexResult = await apiFetch<{ entries: CodexEntry[] }>(
          `/imported-works/${workId}/codex`,
          {},
          token,
        );
        setCodex(codexResult.entries);
      } else {
        const w = await apiFetch<ImportedWork>(`/imported-works/${workId}`, {}, token);
        setWork(w);
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [token, workId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Poll while analyzing
  useEffect(() => {
    if (!status || !["pending", "analyzing"].includes(status.analysis_status)) return;
    const interval = setInterval(async () => {
      if (!token) return;
      const st = await apiFetch<AnalysisStatus>(`/imported-works/${workId}/status`, {}, token);
      setStatus(st);
      if (st.analysis_status === "completed") {
        clearInterval(interval);
        loadData();
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [status?.analysis_status, token, workId, loadData]);

  async function retryAnalysis() {
    if (!token) return;
    setError(null);
    try {
      await apiFetch(`/imported-works/${workId}/retry`, { method: "POST" }, token);
      await loadData();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "重试失败");
    }
  }

  function handleContinue() {
    const query = new URLSearchParams({
      sourceWork: workId,
      mode: "continuation",
      strategy,
      targetWords: String(contTargetWords),
    });
    router.push(`/create?${query.toString()}`);
  }

  function handleFanfic() {
    if (fanficType === "immersive") {
      router.push(`/immersive/new?work=${workId}`);
      return;
    }
    const query = new URLSearchParams({
      sourceWork: workId,
      mode: "fanfic",
      fanficType,
      seed: fanficDesc || `基于原作的${fanficType === "what_if" ? "如果线" : "同人"}创作`,
      targetWords: String(fanficTargetWords),
    });
    router.push(`/create?${query.toString()}`);
  }

  async function verifyCodex(entry: CodexEntry) {
    if (!token) return;
    await apiFetch(
      `/imported-works/${workId}/codex/${entry.id}`,
      { method: "PATCH", body: JSON.stringify({ user_verified: !entry.user_verified }) },
      token,
    );
    setCodex((current) => current.map((item) => (
      item.id === entry.id ? { ...item, user_verified: !entry.user_verified } : item
    )));
  }

  async function editCodex(entry: CodexEntry) {
    if (!token) return;
    const edited = window.prompt("修改知识条目（JSON）", JSON.stringify(entry.content, null, 2));
    if (!edited) return;
    try {
      const content = JSON.parse(edited) as Record<string, unknown>;
      await apiFetch(
        `/imported-works/${workId}/codex/${entry.id}`,
        { method: "PATCH", body: JSON.stringify({ content, user_verified: true }) },
        token,
      );
      setCodex((current) => current.map((item) => (
        item.id === entry.id ? { ...item, content, user_verified: true } : item
      )));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "JSON 格式不正确");
    }
  }

  async function removeCodex(entry: CodexEntry) {
    if (!token || !window.confirm(`确认删除“${entry.title}”？删除后不会带入续写项目。`)) return;
    await apiFetch(`/imported-works/${workId}/codex/${entry.id}`, { method: "DELETE" }, token);
    setCodex((current) => current.filter((item) => item.id !== entry.id));
  }

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#f8f5ee]">
        <LoaderCircle className="animate-spin text-[#a63f2f]" size={32} />
      </main>
    );
  }

  const isAnalyzing = status?.analysis_status === "analyzing";
  const isCompleted = status?.analysis_status === "completed";
  const analysisFailed = status?.analysis_status === "failed";
  const analysisPending = status?.analysis_status === "pending";
  const analysisProgress = Math.min(100, Math.max(0, status?.analysis_progress ?? 0));
  const analysisStage = analysisProgress < 5
    ? "正在准备分批读取"
    : analysisProgress < 88
      ? "正在并行读取原文并提取人物、设定与伏笔"
      : analysisProgress < 98
        ? "正在汇总全书文风、类型与断点"
        : "正在整理分析报告";

  return (
    <main className="min-h-screen pb-10">
      <header className="border-b border-black/10 bg-[#f8f5ee]/90 backdrop-blur-xl">
        <div className="app-frame flex h-16 items-center justify-between">
          <Link href="/bookshelf" className="flex items-center gap-3 font-editorial text-lg font-bold">
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#20221f] text-white">
              <BookOpen size={17} />
            </span>
            浮生流年
          </Link>
          <div className="flex gap-2">
            <Link href="/import" className="secondary-button">返回导入列表</Link>
          </div>
        </div>
      </header>

      <div className="app-frame pt-8 md:pt-12">
        <div className="mb-8">
          <div className="eyebrow">作品分析</div>
          <h1 className="page-title mt-4">{work?.title || "加载中..."}</h1>
          {work?.author && <p className="mt-2 text-sm text-[#74756e]">原作者：{work.author}</p>}
          <div className="mt-2 flex gap-4 text-sm text-[#585a54]">
            <span>{status?.total_chapters || 0} 章</span>
            <span>{Math.round((status?.total_words || 0) / 10000)} 万字</span>
          </div>
        </div>

        {/* Analysis Progress */}
        {isAnalyzing && (
          <div className="surface mb-8 p-6">
            <div className="flex items-center gap-3">
              <LoaderCircle className="animate-spin text-[#4e6859]" size={20} />
              <span className="font-semibold">AI 正在分析作品...</span>
            </div>
            <div className="mt-4 h-2 overflow-hidden rounded-full bg-[#ede9e0]">
              <div
                className="h-full bg-[#4e6859] transition-[width] duration-500"
                style={{ width: `${analysisProgress}%` }}
              />
            </div>
            <p className="mt-2 text-xs text-[#74756e]">
              {analysisStage}（{analysisProgress.toFixed(1)}%）
              {status?.completed_chapters !== undefined ? ` · 已处理 ${status.completed_chapters} / ${status.total_chapters} 章` : ""}
            </p>
          </div>
        )}

        {analysisPending && (
          <div className="surface mb-8 p-6"><div className="flex items-center gap-3"><LoaderCircle className="animate-spin text-[#4e6859]" size={20} /><span className="font-semibold">作品已导入，等待开始分析</span></div><p className="mt-2 text-sm text-[#74756e]">系统会依次识别章节、人物、世界设定和未完成剧情，本页会自动更新。</p></div>
        )}

        {analysisFailed && (
          <div className="surface mb-8 border-[#a63f2f]/25 p-6"><h2 className="font-bold text-[#a63f2f]">这次分析没有完成</h2><p className="mt-2 text-sm leading-6 text-[#74756e]">原文仍安全保存在导入书架中，可以从已完成章节继续重试。</p>{status?.error ? <p className="mt-2 text-xs text-[#a63f2f]">{status.error}</p> : null}<button type="button" className="primary-button mt-4" onClick={retryAnalysis}>重新分析</button></div>
        )}

        {/* Analysis Report */}
        {isCompleted && report && (
          <>
            {/* Action Cards */}
            <div className="mb-8 grid gap-4 md:grid-cols-3">
              {[
                { key: "continue" as const, icon: GitBranch, title: "忠实续写原作", desc: "从断点接力，保持人物、设定与原作方向" },
                { key: "fanfic" as const, icon: Wand2, title: "基于原作写同人", desc: "选择 IF 线、后日谈、角色视角、OC、CP 或 AU" },
              ].map((action) => {
                const Icon = action.icon;
                return (
                  <button
                    key={action.key}
                    type="button"
                    onClick={() => setActionMode(action.key)}
                    className={`rounded-lg border p-5 text-left transition hover:-translate-y-0.5 ${
                      actionMode === action.key
                        ? "border-[#a63f2f] bg-[#fdf8f6] shadow-sm"
                        : "border-[#d8d1c4] bg-white/65 hover:bg-white hover:shadow-sm"
                    }`}
                  >
                    <Icon size={22} className="text-[#a63f2f]" />
                    <h3 className="mt-3 font-bold">{action.title}</h3>
                    <p className="mt-1 text-xs text-[#74756e]">{action.desc}</p>
                  </button>
                );
              })}
              <Link
                href={`/create?sourceWork=${workId}`}
                className="rounded-lg border border-[#d8d1c4] bg-white/65 p-5 text-left transition hover:-translate-y-0.5 hover:bg-white hover:shadow-sm"
              >
                <Sparkles size={22} className="text-[#a63f2f]" />
                <h3 className="mt-3 font-bold">借鉴技法写新书</h3>
                <p className="mt-1 text-xs text-[#74756e]">只继承文风与节奏方法，人物、世界和剧情全部重新创建</p>
              </Link>
            </div>

            {/* Continuation Setup */}
            {actionMode === "continue" && (
              <div className="surface mb-8 p-6">
                <h3 className="text-lg font-bold">续写设置</h3>
                <div className="mt-4">
                  <div className="mb-2 text-sm font-semibold">续写策略</div>
                  <div className="grid gap-2 md:grid-cols-3">
                    {[
                      { key: "faithful" as const, label: "忠实原著", desc: "保持原作节奏和方向" },
                      { key: "accelerate" as const, label: "加速推进", desc: "加快节奏，推向高潮" },
                      { key: "diverge" as const, label: "大胆分叉", desc: "在断点处走不同路线" },
                    ].map((s) => (
                      <button
                        key={s.key}
                        type="button"
                        onClick={() => setStrategy(s.key)}
                        className={`rounded-md border p-4 text-left transition ${
                          strategy === s.key
                            ? "border-[#4e6859] bg-[#edf1ec]"
                            : "border-[#d8d1c4] bg-white/65 hover:bg-white"
                        }`}
                      >
                        <div className="text-sm font-medium">{s.label}</div>
                        <div className="mt-1 text-xs text-[#74756e]">{s.desc}</div>
                      </button>
                    ))}
                  </div>
                </div>
                <div className="mt-4">
                  <div className="mb-2 text-sm font-semibold">续写篇幅</div>
                  <div className="flex gap-2">
                    {DERIVATIVE_TARGETS.map((t) => (
                      <button
                        key={t.v}
                        type="button"
                        onClick={() => setContTargetWords(t.v)}
                        className={`rounded-md border px-4 py-2 text-sm transition ${
                          contTargetWords === t.v
                            ? "border-[#4e6859] bg-[#edf1ec] font-medium"
                            : "border-[#d8d1c4] bg-white/65 hover:bg-white"
                        }`}
                      >
                        {t.l}
                      </button>
                    ))}
                  </div>
                </div>
                {error && <p className="mt-3 text-sm text-[#a63f2f]">{error}</p>}
                <button
                  type="button"
                  className="primary-button mt-6"
                  onClick={handleContinue}
                >
                  <Sparkles size={17} />
                  进入新书向导
                </button>
              </div>
            )}

            {/* Fanfic Setup */}
            {actionMode === "fanfic" && (
              <div className="surface mb-8 p-6">
                <h3 className="text-lg font-bold">同人设置</h3>
                <div className="mt-4">
                  <div className="mb-2 text-sm font-semibold">同人类型</div>
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                    {[
                      { key: "what_if", label: "IF 线", desc: "关键选择改变后会怎样" },
                      { key: "after_story", label: "后日谈", desc: "原作结局之后的新故事" },
                      { key: "side_story", label: "原作支线", desc: "补写未展开的人物和事件" },
                      { key: "character_pov", label: "角色视角", desc: "从另一角色眼中重看故事" },
                      { key: "new_protagonist", label: "原创主角 / OC", desc: "让新人物进入原作世界" },
                      { key: "cp", label: "CP 向", desc: "围绕角色关系发展" },
                      { key: "au", label: "AU 世界", desc: "保留人物，改换时代或设定" },
                      { key: "immersive", label: "代入体验", desc: "由你扮演角色推动选择" },
                      { key: "fanfic_continuation", label: "续写已有同人", desc: "导入同人后结合原作接着写" },
                    ].map((ft) => (
                      <button
                        key={ft.key}
                        type="button"
                        onClick={() => setFanficType(ft.key)}
                        className={`rounded-md border p-3 text-left transition ${
                          fanficType === ft.key
                            ? "border-[#4e6859] bg-[#edf1ec]"
                            : "border-[#d8d1c4] bg-white/65 hover:bg-white"
                        }`}
                      >
                        <div className="text-sm font-medium">{ft.label}</div>
                        <div className="mt-1 text-xs text-[#74756e]">{ft.desc}</div>
                      </button>
                    ))}
                  </div>
                </div>
                <div className="mt-4">
                  <label className="mb-1 block text-sm font-semibold">故事种子描述（选填）</label>
                  <textarea
                    value={fanficDesc}
                    onChange={(e) => setFanficDesc(e.target.value)}
                    rows={3}
                    className="w-full rounded-md border border-[#d8d1c4] bg-white px-3 py-2 text-sm focus:border-[#a63f2f] focus:outline-none"
                    placeholder="例如：如果主角当年没有离开，想让哪段关系或事件发生变化？"
                  />
                </div>
                <div className="mt-4">
                  <div className="mb-2 text-sm font-semibold">篇幅</div>
                  <div className="flex gap-2">
                    {DERIVATIVE_TARGETS.map((t) => (
                      <button
                        key={t.v}
                        type="button"
                        onClick={() => setFanficTargetWords(t.v)}
                        className={`rounded-md border px-4 py-2 text-sm transition ${
                          fanficTargetWords === t.v
                            ? "border-[#4e6859] bg-[#edf1ec] font-medium"
                            : "border-[#d8d1c4] bg-white/65 hover:bg-white"
                        }`}
                      >
                        {t.l}
                      </button>
                    ))}
                  </div>
                </div>
                {error && <p className="mt-3 text-sm text-[#a63f2f]">{error}</p>}
                <button
                  type="button"
                  className="primary-button mt-6"
                  onClick={handleFanfic}
                >
                  <Wand2 size={17} />
                  进入新书向导
                </button>
              </div>
            )}

            {/* Analysis Report Sections */}
            <div className="space-y-6">
              {codex.length > 0 ? (
                <div className="surface p-6">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <h3 className="font-bold">作品知识库校对</h3>
                      <p className="mt-1 text-xs text-[#74756e]">低置信度事实建议先核对；修改、确认或删除后再开始续写。</p>
                    </div>
                    <span className="text-xs text-[#74756e]">已确认 {codex.filter((item) => item.user_verified).length}/{codex.length}</span>
                  </div>
                  <div className="mt-4 max-h-[420px] space-y-2 overflow-y-auto pr-1">
                    {codex.map((entry) => (
                      <div key={entry.id} className="flex items-start gap-3 rounded-md border border-[#d8d1c4] bg-[#faf9f6] p-3">
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-semibold">{entry.title}</span>
                            <span className="rounded bg-[#eee9df] px-1.5 py-0.5 text-[10px] text-[#74756e]">{entry.layer} / {entry.kind}</span>
                            {entry.confidence < 0.75 ? <span className="text-[10px] font-semibold text-[#a63f2f]">需核对</span> : null}
                          </div>
                          <p className="mt-1 line-clamp-2 text-xs leading-5 text-[#74756e]">{JSON.stringify(entry.content)}</p>
                        </div>
                        <div className="flex shrink-0 gap-1">
                          <button type="button" className="icon-button" title="编辑" onClick={() => editCodex(entry)}><Scroll size={15} /></button>
                          <button type="button" className={`icon-button ${entry.user_verified ? "text-[#4e6859]" : ""}`} title={entry.user_verified ? "取消确认" : "确认准确"} onClick={() => verifyCodex(entry)}><Check size={15} /></button>
                          <button type="button" className="icon-button text-[#a63f2f]" title="删除" onClick={() => removeCodex(entry)}><Trash2 size={15} /></button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
              {/* Style */}
              {report.style_summary && (
                <div className="surface p-6">
                  <h3 className="flex items-center gap-2 font-bold">
                    <Scroll size={18} className="text-[#d9ad62]" />
                    文风分析
                  </h3>
                  <p className="mt-3 text-sm leading-6 text-[#585a54]">{report.style_summary}</p>
                </div>
              )}

              {/* Characters */}
              {report.characters.length > 0 && (
                <div className="surface p-6">
                  <h3 className="flex items-center gap-2 font-bold">
                    <User2 size={18} className="text-[#a63f2f]" />
                    角色图谱（{report.characters.length} 个角色）
                  </h3>
                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    {report.characters.map((char) => (
                      <div key={char.slug} className="rounded-md border border-[#d8d1c4] bg-[#faf9f6] p-4">
                        <div className="font-semibold">{char.title}</div>
                        <p className="mt-1 line-clamp-3 text-xs leading-5 text-[#74756e]">{char.content}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* World Rules */}
              {report.world_rules.length > 0 && (
                <div className="surface p-6">
                  <h3 className="flex items-center gap-2 font-bold">
                    <Swords size={18} className="text-[#4e6859]" />
                    世界观设定
                  </h3>
                  <div className="mt-4 space-y-3">
                    {report.world_rules.map((rule) => (
                      <div key={rule.slug} className="rounded-md border border-[#d8d1c4] bg-[#faf9f6] p-4">
                        <div className="font-semibold">{rule.title}</div>
                        <p className="mt-1 text-xs leading-5 text-[#74756e]">{rule.content}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Power System */}
              {report.power_system && (
                <div className="surface p-6">
                  <h3 className="font-bold">{report.power_system.title}</h3>
                  <p className="mt-2 text-sm leading-6 text-[#585a54]">{report.power_system.content}</p>
                </div>
              )}

              {/* Foreshadowing */}
              {report.foreshadowing.length > 0 && (
                <div className="surface p-6">
                  <h3 className="font-bold">伏笔追踪（{report.foreshadowing.length} 条）</h3>
                  <div className="mt-4 space-y-2">
                    {report.foreshadowing.slice(0, 10).map((f, i) => (
                      <div key={i} className="flex items-start gap-3 rounded-md border border-[#d8d1c4] bg-[#faf9f6] p-3">
                        <span className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-xs ${
                          f.status === "resolved" ? "bg-[#edf1ec] text-[#4e6859]" : "bg-[#f0e2cd] text-[#a63f2f]"
                        }`}>
                          {f.status === "resolved" ? "已收" : "待收"}
                        </span>
                        <div className="min-w-0">
                          <p className="text-sm">{f.content}</p>
                          <p className="mt-1 text-xs text-[#74756e]">第 {f.planted_chapter} 章 · {f.importance}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Thrill Formula */}
              {report.thrill_formula && (
                <div className="surface p-6">
                  <h3 className="font-bold">节奏分析</h3>
                  <p className="mt-2 text-sm text-[#585a54]">{report.thrill_formula}</p>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </main>
  );
}
