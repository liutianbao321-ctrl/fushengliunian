"use client";

import { RefreshCw, Sparkles } from "lucide-react";

import type { OutlineNode } from "@/lib/blueprint";
import { KeywordChips, NineLineDots, SweetPointMarks } from "./shared";

export function StageMap({
  segments,
  generatingIds,
  onEdit,
  onRegenerate,
}: {
  segments: OutlineNode[];
  generatingIds: Set<string>;
  onEdit: (node: OutlineNode) => void;
  onRegenerate: (node: OutlineNode) => void;
}) {
  if (!segments.length) {
    return (
      <div className="rounded-md border border-dashed border-[#cdc6b8] bg-white/50 px-6 py-12 text-center">
        <p className="font-editorial text-lg font-bold">还没有阶段规划</p>
        <p className="mt-2 text-sm text-[#7a7b74]">让 AI 生成 L4 事件段，或从层级树里补齐阶段节点。</p>
      </div>
    );
  }

  return (
    <div className="scrollbar-thin flex gap-4 overflow-x-auto pb-4">
      {segments.map((segment) => {
        const busy = generatingIds.has(segment.id);
        const covered = segment.meta.nine_lines ?? [];
        return (
          <article
            key={segment.id}
            className="flex w-[280px] shrink-0 flex-col rounded-lg border border-[#d8d1c4] bg-[#fbfaf6] shadow-[0_8px_24px_rgba(45,39,30,0.05)]"
          >
            <button
              type="button"
              className="flex flex-1 flex-col gap-3 rounded-t-lg px-4 py-4 text-left transition hover:bg-[#fff7f0]"
              onClick={() => onEdit(segment)}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] font-bold text-[#a08a5a]">第 {segment.seq} 段</span>
                <NineLineDots covered={covered} />
              </div>
              <h3 className="font-editorial text-lg font-bold leading-snug">{segment.title || "未命名阶段"}</h3>
              {segment.body ? (
                <p className="line-clamp-4 text-[13px] leading-6 text-[#5b5d56]">{segment.body}</p>
              ) : null}
              {segment.meta.keywords?.length ? <KeywordChips keywords={segment.meta.keywords} /> : null}
              {segment.meta.sweet_points?.length ? <SweetPointMarks points={segment.meta.sweet_points} /> : null}
              {segment.meta.est_chapters ? (
                <span className="text-[11px] text-[#8a8174]">预计约 {segment.meta.est_chapters} 章</span>
              ) : null}
            </button>
            <div className="flex items-center justify-between gap-2 border-t border-[#e4ded3] px-3 py-2.5">
              <button
                type="button"
                className="text-xs font-semibold text-[#6d6f68] hover:text-[#a63f2f]"
                onClick={() => onEdit(segment)}
              >
                编辑
              </button>
              <button
                type="button"
                className="inline-flex items-center gap-1.5 rounded-md border border-[#d8d1c4] bg-white px-2.5 py-1.5 text-xs font-semibold text-[#a63f2f] transition hover:border-[#a63f2f] disabled:opacity-60"
                onClick={() => onRegenerate(segment)}
                disabled={busy}
              >
                {busy ? <RefreshCw size={13} className="animate-spin" /> : <Sparkles size={13} />}
                {busy ? "重出中" : "AI 重出"}
              </button>
            </div>
          </article>
        );
      })}
    </div>
  );
}
