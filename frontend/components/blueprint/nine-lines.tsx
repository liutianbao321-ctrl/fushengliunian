"use client";

import { AlertTriangle } from "lucide-react";

import { NINE_LINES, type OutlineNode } from "@/lib/blueprint";

const BREAK_THRESHOLD = 5;

export function NineLines({
  segments,
  onEdit,
}: {
  segments: OutlineNode[];
  onEdit: (node: OutlineNode) => void;
}) {
  if (!segments.length) {
    return (
      <div className="rounded-md border border-dashed border-[#cdc6b8] bg-white/50 px-6 py-12 text-center">
        <p className="font-editorial text-lg font-bold">暂无阶段数据</p>
        <p className="mt-2 text-sm text-[#7a7b74]">九线泳道需要至少一段 L4 事件段。</p>
      </div>
    );
  }

  const gridStyle = {
    gridTemplateColumns: `150px repeat(${segments.length}, minmax(56px, 1fr))`,
  };

  return (
    <div className="scrollbar-thin overflow-x-auto pb-4">
      <div className="min-w-[760px]">
        {/* 表头：事件段 */}
        <div className="grid items-end gap-1" style={gridStyle}>
          <div className="px-2 pb-2 text-xs font-bold text-[#8a8174]">九线 ＼ 事件段</div>
          {segments.map((segment) => (
            <div key={segment.id} className="px-1 pb-2 text-center text-[11px] font-semibold text-[#6d6f68]">
              <div className="truncate" title={segment.title}>{segment.seq}</div>
            </div>
          ))}
        </div>

        {NINE_LINES.map((line) => {
          const coverage = segments.map((segment) => (segment.meta.nine_lines ?? []).includes(line.key));
          let maxGap = 0;
          let gap = 0;
          for (const covered of coverage) {
            gap = covered ? 0 : gap + 1;
            if (gap > maxGap) maxGap = gap;
          }
          const broken = maxGap >= BREAK_THRESHOLD;
          return (
            <div key={line.key} className="grid items-stretch gap-1 border-t border-[#ece6da]" style={gridStyle}>
              <div className="flex items-center gap-1.5 px-2 py-2">
                <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: line.color }} />
                <span className="truncate text-xs font-semibold text-[#4d504a]">{line.key}</span>
                {broken ? (
                  <span className="ml-auto inline-flex items-center gap-0.5 rounded-full bg-[#fff4d1] px-1.5 py-0.5 text-[10px] font-bold text-[#a87b16]" title={`连续 ${maxGap} 段未推进该线`}>
                    <AlertTriangle size={10} />断线
                  </span>
                ) : null}
              </div>
              {segments.map((segment, index) => {
                const on = coverage[index];
                return (
                  <button
                    type="button"
                    key={segment.id}
                    onClick={() => onEdit(segment)}
                    title={`${line.key} · 第 ${segment.seq} 段：${on ? "已覆盖" : "未覆盖"}`}
                    className="m-0.5 h-9 rounded transition"
                    style={{
                      backgroundColor: on ? line.color : "rgba(0,0,0,0.035)",
                      opacity: on ? 0.9 : 0.6,
                    }}
                  />
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}
