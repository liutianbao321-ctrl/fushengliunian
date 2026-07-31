"use client";

import { BookOpen, PenLine, Search } from "lucide-react";
import { useDeferredValue, useState } from "react";

type Chapter = {
  volume_sequence: number;
  chapter_sequence: number;
  title: string;
  status: string;
  content?: string;
};

const statusLabel: Record<string, string> = {
  unplanned: "未规划",
  planned: "待写",
  drafting: "生成中",
  review_required: "待审",
  published: "完成",
  completed: "完成",
};

export function ChapterSidebar({
  chapters,
  currentChapter,
  isGenerating,
  onSelect,
  onWriteNext,
  autoWrite,
  onAutoWriteChange,
  totalChapters,
}: {
  chapters: Chapter[];
  currentChapter: number;
  isGenerating: boolean;
  onSelect: (sequence: number) => void;
  onWriteNext: () => void;
  autoWrite: boolean;
  onAutoWriteChange: (enabled: boolean) => void;
  totalChapters: number;
}) {
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query.trim().toLowerCase());
  const filtered = deferredQuery
    ? chapters.filter((chapter) => `${chapter.chapter_sequence}${chapter.title}`.toLowerCase().includes(deferredQuery))
    : chapters;
  const completed = chapters.filter((chapter) => Boolean(chapter.content?.trim())).length;
  const lastWrittenSequence = chapters.reduce((latest, chapter) => chapter.content?.trim() ? Math.max(latest, chapter.chapter_sequence) : latest, 0);
  const lastSequence = chapters.length ? chapters[chapters.length - 1].chapter_sequence : 0;
  const nextSequence = lastWrittenSequence ? lastWrittenSequence + 1 : Math.min(lastSequence || 1, 1);
  const bookComplete = completed >= totalChapters;
  const volumes = Array.from(new Set(filtered.map((chapter) => chapter.volume_sequence))).sort((a, b) => a - b);

  return (
    <aside className="tool-panel flex min-h-[520px] flex-col overflow-hidden xl:h-[calc(100vh-164px)]">
      <div className="border-b border-[#ded8cd] px-4 pb-4 pt-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="eyebrow">章节</div>
            <h2 className="mt-2 font-editorial text-xl font-bold">正文目录</h2>
          </div>
          <span className="text-xs text-[#82827a]">{completed}/{chapters.length}</span>
        </div>
        <label className="relative mt-4 block">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[#8b8a81]" size={15} />
          <input
            className="field h-10 pl-9 pr-3 text-sm"
            placeholder="搜索章节"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
      </div>

      <div className="scrollbar-thin flex-1 overflow-y-auto px-2 py-3">
        {filtered.length ? (
          <div className="space-y-3">
            {volumes.map((volume) => <section key={volume}>
              <div className="mb-1 flex items-center gap-2 px-2 text-[11px] font-semibold text-[#8c7a62]">
                <span className="h-px flex-1 bg-[#ddd5c8]" />第 {volume} 卷<span className="h-px flex-1 bg-[#ddd5c8]" />
              </div>
              <div className="space-y-1">
            {filtered.filter((chapter) => chapter.volume_sequence === volume).map((chapter) => {
              const active = currentChapter === chapter.chapter_sequence;
              return (
                <button
                  key={chapter.chapter_sequence}
                  type="button"
                  onClick={() => onSelect(chapter.chapter_sequence)}
                  className={`group grid w-full grid-cols-[32px_minmax(0,1fr)] items-center gap-2 rounded-md px-2 py-2.5 text-left transition ${
                    active ? "bg-[#252821] text-white" : "hover:bg-[#eee9df]"
                  }`}
                >
                  <span className={`flex h-8 w-8 items-center justify-center rounded text-xs font-semibold ${active ? "bg-white/10 text-[#e4bd76]" : "bg-[#e8e2d7] text-[#74756d]"}`}>
                    {chapter.chapter_sequence}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium">{chapter.title || `第 ${chapter.chapter_sequence} 章`}</span>
                    <span className={`mt-0.5 block text-[11px] ${active ? "text-white/50" : "text-[#929188]"}`}>{chapter.content?.trim() ? "正文已写" : statusLabel[chapter.status] ?? chapter.status}</span>
                  </span>
                </button>
              );
            })}
              </div>
            </section>)}
          </div>
        ) : (
          <div className="flex h-40 flex-col items-center justify-center text-center text-xs text-[#8c8b82]">
            <BookOpen size={22} strokeWidth={1.4} />
            <span className="mt-3">没有匹配章节</span>
          </div>
        )}
      </div>

      <div className="border-t border-[#ded8cd] bg-[#f6f2ea] p-3">
        <div className="mb-3 flex items-center justify-between rounded-md border border-[#d8d0c2] bg-white px-3 py-2.5"><div><div className="text-xs font-semibold">自动连续写作</div><p className="mt-0.5 text-[10px] text-[#7d7d75]">写完一章后自动规划并写下一章</p></div><button type="button" role="switch" aria-checked={autoWrite} onClick={() => onAutoWriteChange(!autoWrite)} className={`relative h-6 w-11 rounded-full transition ${autoWrite ? "bg-[#4e6859]" : "bg-[#cfc8bc]"}`}><span className={`absolute top-1 h-4 w-4 rounded-full bg-white transition ${autoWrite ? "left-6" : "left-1"}`} /></button></div>
        <button type="button" className="primary-button w-full" onClick={onWriteNext} disabled={isGenerating || bookComplete}>
          <PenLine size={16} />
          {bookComplete ? "全书正文已完成" : `开始写第 ${Math.min(nextSequence, totalChapters)} 章`}
        </button>
      </div>
    </aside>
  );
}
