"use client";

import { Link2, MessageSquare, Package, User } from "lucide-react";

import type { PlotLedgerEntry } from "@/lib/blueprint";

const TYPE_META: Record<PlotLedgerEntry["type"], { label: string; color: string; icon: typeof User }> = {
  person: { label: "人物", color: "#2e86c1", icon: User },
  item: { label: "物品", color: "#8e44ad", icon: Package },
  dialog: { label: "对话", color: "#16a085", icon: MessageSquare },
};

const STATUS_META: Record<PlotLedgerEntry["status"], { label: string; className: string }> = {
  open: { label: "未回收", className: "bg-[#ece8df] text-[#6d6f68]" },
  reminded: { label: "已提醒", className: "bg-[#fdf1d8] text-[#9a7320]" },
  closed: { label: "已回收", className: "bg-[#e7eef6] text-[#2e6db4]" },
  expired: { label: "已逾期", className: "bg-[#fbe3df] text-[#a63f2f]" },
};

function chapterRange(entries: PlotLedgerEntry[]): [number, number] {
  let min = Infinity;
  let max = -Infinity;
  for (const entry of entries) {
    const points = [entry.planted_chapter, entry.due_chapter, ...entry.mentioned_chapters, entry.resolved_chapter ?? 0];
    for (const point of points) {
      if (point < min) min = point;
      if (point > max) max = point;
    }
  }
  if (!Number.isFinite(min)) return [1, 1];
  if (max - min < 4) max = min + 4;
  return [min, max];
}

export function PlotLedger({ entries }: { entries: PlotLedgerEntry[] }) {
  if (!entries.length) {
    return (
      <div className="rounded-md border border-dashed border-[#cdc6b8] bg-white/50 px-6 py-12 text-center">
        <p className="font-editorial text-lg font-bold">伏笔登记表为空</p>
        <p className="mt-2 text-sm text-[#7a7b74]">AI 生成大纲或正文时会自动登记伏笔，也可以后续补充。</p>
      </div>
    );
  }

  const [minC, maxC] = chapterRange(entries);
  const span = Math.max(1, maxC - minC);

  const xOf = (chapter: number) => 12 + ((chapter - minC) / span) * 196;

  return (
    <div className="overflow-hidden rounded-lg border border-[#d8d1c4] bg-[#fbfaf6]">
      <div className="flex items-center justify-between border-b border-[#e4ded3] px-4 py-3">
        <h3 className="font-editorial text-base font-bold">伏笔登记表</h3>
        <span className="text-xs text-[#8a8174]">埋设章 → 回收章 连线 · 逾期未回收标红</span>
      </div>

      {/* 章节刻度 */}
      <div className="border-b border-[#ece6da] px-4 py-2">
        <div className="text-[11px] text-[#8a8174]">
          章节轴：第 {minC} 章 — 第 {maxC} 章
        </div>
      </div>

      <div className="scrollbar-thin overflow-x-auto">
        <table className="w-full min-w-[760px] border-collapse text-sm">
          <thead>
            <tr className="text-left text-[11px] font-semibold text-[#8a8174]">
              <th className="w-[180px] px-3 py-2">连线</th>
              <th className="px-3 py-2">类型</th>
              <th className="px-3 py-2">伏笔内容</th>
              <th className="px-3 py-2">埋设章</th>
              <th className="px-3 py-2">回收章</th>
              <th className="px-3 py-2">状态</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => {
              const meta = TYPE_META[entry.type];
              const Icon = meta.icon;
              const endChapter = entry.resolved_chapter ?? entry.due_chapter;
              const overdue = entry.status === "expired" || (entry.status === "open" && entry.due_chapter <= maxC && !entry.resolved_chapter);
              const x1 = xOf(entry.planted_chapter);
              const x2 = xOf(endChapter);
              const isYY = entry.is_yy;
              return (
                <tr key={entry.id} className={`border-t border-[#ece6da] ${overdue ? "bg-[#fdf0ee]" : ""}`}>
                  <td className="px-3 py-2">
                    <svg width="220" height="30" viewBox="0 0 220 30" className="overflow-visible">
                      <line x1={x1} y1="22" x2={x2} y2="22" stroke={overdue ? "#c0392b" : meta.color} strokeWidth="1.5" strokeDasharray="3 3" opacity="0.5" />
                      <path
                        d={`M ${x1} 22 Q ${(x1 + x2) / 2} 4 ${x2} 22`}
                        fill="none"
                        stroke={overdue ? "#c0392b" : meta.color}
                        strokeWidth="2"
                      />
                      <circle cx={x1} cy="22" r="3" fill={meta.color} />
                      <circle cx={x2} cy="22" r="3" fill={overdue ? "#c0392b" : meta.color} stroke="#fff" strokeWidth="1" />
                    </svg>
                  </td>
                  <td className="px-3 py-2">
                    <span className="inline-flex items-center gap-1 text-xs font-semibold" style={{ color: meta.color }}>
                      <Icon size={13} />{meta.label}
                      {isYY ? <span className="ml-1 rounded bg-[#fdf6e3] px-1 text-[10px] font-bold text-[#9a7320]">YY</span> : null}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-[#3e413c]">
                    <span className="line-clamp-2">{entry.description}</span>
                    {entry.mentioned_chapters.length ? (
                      <span className="mt-0.5 block text-[10px] text-[#8a8174]">提及：第 {entry.mentioned_chapters.join("、")} 章</span>
                    ) : null}
                  </td>
                  <td className="px-3 py-2 tabular-nums text-[#5b5d56]">第 {entry.planted_chapter} 章</td>
                  <td className="px-3 py-2 tabular-nums text-[#5b5d56]">{entry.resolved_chapter ? `第 ${entry.resolved_chapter} 章` : `应第 ${entry.due_chapter} 章`}</td>
                  <td className="px-3 py-2">
                    <span className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-semibold ${STATUS_META[entry.status].className}`}>
                      {STATUS_META[entry.status].label}
                    </span>
                    {overdue ? <span className="ml-1 text-[11px] font-bold text-[#a63f2f]" title="超过计划回收章仍未回收"><Link2 size={11} className="inline" />逾期</span> : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
