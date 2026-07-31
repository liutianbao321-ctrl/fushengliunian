"use client";

import Link from "next/link";
import { Activity, BookMarked, Check, ChevronRight, MapPin, Sparkles, UserRound, Waypoints } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { ReaderPanel } from "@/components/workspace/reader-panel";
import { apiFetch } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import type { ChapterPlan, RewriteOptions } from "@/components/editor/chapter-editor";

type Chapter = {
  chapter_sequence?: number;
  title?: string;
  beat_sheet?: ChapterPlan;
  summary?: string;
  content?: string;
  quality_scores?: Record<string, { passed?: boolean; score?: number }>;
    generation_log?: Record<string, unknown>;
};
type BibleItem = { id?: string; title: string; category: string; content: string };
type Foreshadowing = { content: string; planted_chapter: number };
type Tab = "context" | "activity" | "ai";

const categoryLabels: Record<string, string> = {
  character: "人物",
  worldview: "世界与背景",
  canon_rule: "写作边界",
  timeline: "故事进度",
  location: "地点",
};
const titleLabels: Record<string, string> = {
  "禁忌规则": "写作边界",
  "主时间线": "故事进度",
  "世界核心设定": "世界与背景",
};

export function ProjectInfoPanel({ projectId, chapter, bible, foreshadowing, onOptimize, onDeepOptimize, optimizing }: { projectId: string; chapter: Chapter | null; bible: BibleItem[]; foreshadowing: Foreshadowing[]; onOptimize: (options: RewriteOptions) => Promise<void>; onDeepOptimize: (options: RewriteOptions) => Promise<void>; optimizing: boolean }) {
  const [tab, setTab] = useState<Tab>("context");
  const [latestFeedback, setLatestFeedback] = useState<SavedFeedback | null>(null);
  const handleFeedback = useCallback((feedback: SavedFeedback | null) => setLatestFeedback(feedback), []);
  const tabs: { key: Tab; label: string; icon: typeof BookMarked }[] = [
    { key: "context", label: "人物设定", icon: BookMarked },
    { key: "activity", label: "检查", icon: Activity },
    { key: "ai", label: "AI 优化", icon: Sparkles },
  ];
  const characters = bible.filter((item) => item.category === "character");
  const rules = bible.filter((item) => ["worldview", "canon_rule"].includes(item.category));
  const timeline = bible.filter((item) => ["timeline", "location"].includes(item.category));

  return <aside className="tool-panel flex min-h-[520px] flex-col overflow-hidden xl:h-[calc(100vh-164px)]">
    <div className="border-b border-[#ded8cd] px-4 pt-4">
      <div className="flex items-center justify-between"><div><div className="text-[11px] font-semibold text-[#8a8174]">当前章节</div><h2 className="mt-0.5 font-editorial text-base font-bold">写作参考</h2></div><span className="rounded-md bg-[#edf1ec] px-2 py-1 text-[11px] text-[#4e6859]">检查与优化按需使用</span></div>
      <div className="mt-4 grid grid-cols-3" role="tablist" aria-label="章节写作参考">
        {tabs.map((item) => { const Icon = item.icon; return <button key={item.key} type="button" role="tab" aria-selected={tab === item.key} className={`relative flex min-w-0 flex-col items-center gap-1 pb-3 text-[11px] font-semibold transition ${tab === item.key ? "text-[#a63f2f]" : "text-[#85857d] hover:text-[#20221f]"}`} onClick={() => setTab(item.key)}><Icon size={15} /><span className="whitespace-nowrap">{item.label}</span>{tab === item.key ? <span className="absolute inset-x-2 bottom-0 h-0.5 bg-[#a63f2f]" /> : null}</button>; })}
      </div>
    </div>

    <div key={tab} className="reveal scrollbar-thin flex-1 overflow-y-auto p-4">
      {tab === "context" ? <div>
        <div className="mb-4 border-l-2 border-[#4e6859] bg-[#edf1ec] px-3 py-2.5 text-xs leading-5 text-[#596159]">这里的内容会参与本章写作和优化，避免人物、世界与前文互相矛盾。</div>
        <ContextSection icon={<UserRound size={15} />} title="本章人物" items={characters} emptyText="章纲确认人物后，会优先匹配相关人物设定。" />
        <ContextSection icon={<BookMarked size={15} />} title="必须遵守" items={rules} emptyText="还没有世界背景或写作边界。" />
        <ContextSection icon={<MapPin size={15} />} title="时间与地点" items={timeline} emptyText="还没有记录当前故事进度。" />
        <section className="border-t border-[#e4ded3] py-4"><h3 className="flex items-center gap-2 text-xs font-bold text-[#555852]"><Waypoints size={15} />待推进线索</h3>{foreshadowing.length ? <div className="mt-2 space-y-2">{foreshadowing.slice(0, 4).map((item, index) => <div className="flex gap-2 text-xs leading-5" key={`${item.content}-${index}`}><span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[#b88937]" /><span>{item.content}<small className="ml-1 text-[#948b7e]">第 {item.planted_chapter} 章埋下</small></span></div>)}</div> : <p className="mt-2 text-xs leading-5 text-[#92928a]">暂无需要推进的线索。</p>}</section>
        <Link href={`/settings/${projectId}`} className="flex min-h-10 items-center justify-between border-t border-[#e4ded3] pt-4 text-xs font-semibold text-[#a63f2f]">管理全部人物与设定<ChevronRight size={15} /></Link>
      </div> : null}

      {tab === "activity" ? chapter?.chapter_sequence && chapter.content?.trim() ? <ReaderPanel projectId={projectId} chapterSequence={chapter.chapter_sequence} onFeedback={handleFeedback} /> : <EmptyState text="这一章有正文后，可以按需检查。" /> : null}

      {tab === "ai" ? chapter?.chapter_sequence && chapter.content?.trim() ? <OptimizePanel projectId={projectId} chapterSequence={chapter.chapter_sequence} onOptimize={onOptimize} onDeepOptimize={onDeepOptimize} optimizing={optimizing} latestFeedback={latestFeedback} onFeedback={handleFeedback} /> : <EmptyState text="这一章有正文后，可以使用 AI 优化。" /> : null}
    </div>
  </aside>;
}

type SavedFeedback = { summary?: string | null; risk_points?: { category?: string; finding?: string; description?: string; reason?: string; suggestion?: string; quote?: string; location?: string }[] };
function OptimizePanel({ projectId, chapterSequence, onOptimize, onDeepOptimize, optimizing, latestFeedback, onFeedback }: { projectId: string; chapterSequence: number; onOptimize: (options: RewriteOptions) => Promise<void>; onDeepOptimize: (options: RewriteOptions) => Promise<void>; optimizing: boolean; latestFeedback: SavedFeedback | null; onFeedback: (feedback: SavedFeedback | null) => void }) {
  const token = useAppStore((state) => state.token);
  const [instruction, setInstruction] = useState("");
  const [mode, setMode] = useState<"light" | "deep">("light");
  useEffect(() => {
    if (!token) return;
    onFeedback(null);
    apiFetch<SavedFeedback[]>(`/projects/${projectId}/reader-feedback?chapter_sequence=${chapterSequence}`, {}, token).then((items) => onFeedback(items[0] ?? null)).catch(() => undefined);
  }, [chapterSequence, onFeedback, projectId, token]);
  const checkDirection = [
    latestFeedback?.summary,
    ...(latestFeedback?.risk_points ?? []).map((item) => [
      item.category ? `【${item.category}】` : "",
      item.finding || item.description || item.reason || item.location || "",
      item.suggestion ? `建议：${item.suggestion}` : "",
      item.quote ? `原文：${item.quote}` : "",
    ].filter(Boolean).join(" ")),
  ].filter(Boolean).join("；");
  const effectiveInstruction = [checkDirection ? `参考最近检查结果：${checkDirection}` : "", instruction.trim()].filter(Boolean).join("\n");
  const options = { focus: checkDirection ? ["参考章节检查结果"] : [], preserve: ["关键事件", "人物关系", "章末悬念"], instruction: effectiveInstruction };
  return <div className="space-y-4">
    <div className="grid grid-cols-2 rounded-md border border-[#d8d1c4] bg-[#eee9df] p-1" role="tablist" aria-label="优化方式"><button type="button" role="tab" aria-selected={mode === "light"} className={`min-h-9 rounded px-2 text-xs font-semibold ${mode === "light" ? "bg-white text-[#a63f2f] shadow-sm" : "text-[#70726b]"}`} onClick={() => setMode("light")} title="只修改必要句子">快速修改</button><button type="button" role="tab" aria-selected={mode === "deep"} className={`min-h-9 rounded px-2 text-xs font-semibold ${mode === "deep" ? "bg-white text-[#a63f2f] shadow-sm" : "text-[#70726b]"}`} onClick={() => setMode("deep")} title="重新处理整章结构与表达">深度重写</button></div>
    {latestFeedback ? <div className="rounded-md border border-[#d8d1c4] bg-[#faf9f6] p-4"><div className="text-xs font-bold">已同步最近检查结果</div><p className="mt-2 text-xs leading-6 text-[#686a64]">{checkDirection || "没有发现明确问题"}</p></div> : <p className="text-xs leading-5 text-[#85857d]">还没有检查结果。可以直接输入自己的优化方向，不需要先检查。</p>}
    <label className="block text-xs font-bold">我想怎么优化<textarea className="field mt-2 min-h-36 p-3 font-normal leading-6" value={instruction} onChange={(event) => setInstruction(event.target.value)} placeholder="例如：把开头写清楚，让读者先知道主角在哪里、要做什么；对话更自然；保留结尾悬念。" /></label>
    <button className="primary-button w-full" type="button" disabled={optimizing || !effectiveInstruction} onClick={() => mode === "light" ? onOptimize(options) : onDeepOptimize(options)}><Sparkles size={16} />{optimizing ? (mode === "light" ? "正在快速修改" : "正在深度重写") : (mode === "light" ? "应用局部修改" : "开始整章重写")}</button>
  </div>;
}

function ContextSection({ icon, title, items, emptyText }: { icon: React.ReactNode; title: string; items: BibleItem[]; emptyText: string }) {
  return <section className="border-t border-[#e4ded3] py-4 first:border-0 first:pt-0"><h3 className="flex items-center gap-2 text-xs font-bold text-[#555852]">{icon}{title}<span className="ml-auto font-normal text-[#97968e]">{items.length}</span></h3>{items.length ? <div className="mt-2 space-y-1">{items.slice(0, 5).map((item) => <details className="group border-b border-[#eee9df] py-2 last:border-0" key={item.id ?? item.title}><summary className="flex cursor-pointer list-none items-center gap-2 text-sm"><Check className="text-[#4e6859]" size={13} /><span className="min-w-0 flex-1 truncate">{titleLabels[item.title] ?? item.title}</span><span className="text-[10px] text-[#999087]">{categoryLabels[item.category] ?? "设定"}</span></summary><p className="mt-2 pl-5 text-xs leading-5 text-[#686a64]">{item.content}</p></details>)}</div> : <p className="mt-2 text-xs leading-5 text-[#92928a]">{emptyText}</p>}</section>;
}
function EmptyState({ text }: { text: string }) { return <div className="flex min-h-40 items-center justify-center px-4 text-center text-xs leading-6 text-[#8b8b83]">{text}</div>; }
