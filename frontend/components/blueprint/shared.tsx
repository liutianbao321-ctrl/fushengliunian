"use client";

import { Lock } from "lucide-react";

import { NINE_LINES, type NodeStatus, type OutlineNode } from "@/lib/blueprint";

const STATUS_META: Record<NodeStatus, { label: string; className: string }> = {
  draft: { label: "草稿", className: "bg-[#ece8df] text-[#6d6f68] border-[#d8d1c4]" },
  confirmed: { label: "已确认", className: "bg-[#e7eef6] text-[#2e6db4] border-[#bcd4ec]" },
  locked: { label: "已锁定", className: "bg-[#fbf2dc] text-[#9a7320] border-[#e6cf94]" },
};

export function StatusBadge({ status }: { status: NodeStatus }) {
  const meta = STATUS_META[status];
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${meta.className}`}>
      {status === "locked" ? <Lock size={11} /> : null}
      {meta.label}
    </span>
  );
}

export const LAYER_LABELS: Record<string, string> = {
  L0: "点子",
  L1: "立意",
  L2: "设定",
  L3: "主线",
  L4: "阶段",
  L5: "章纲",
};

export function LayerTag({ layer }: { layer: string }) {
  return (
    <span className="inline-flex h-5 min-w-5 items-center justify-center rounded bg-[#20221f] px-1.5 text-[11px] font-bold text-white">
      {layer}
    </span>
  );
}

export function NineLineDots({ covered, size = 9 }: { covered: string[]; size?: number }) {
  return (
    <span className="inline-flex items-center gap-1" title={`覆盖九线：${covered.join("、") || "无"}`}>
      {NINE_LINES.map((line) => {
        const on = covered.includes(line.key);
        return (
          <span
            key={line.key}
            className="rounded-full"
            style={{
              width: size,
              height: size,
              backgroundColor: on ? line.color : "transparent",
              border: `1px solid ${on ? line.color : "#cbbfa9"}`,
              opacity: on ? 1 : 0.5,
            }}
          />
        );
      })}
    </span>
  );
}

export function KeywordChips({ keywords }: { keywords?: string[] }) {
  if (!keywords?.length) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {keywords.map((word) => (
        <span key={word} className="rounded-full bg-[#f0ece2] px-2 py-0.5 text-[11px] text-[#6b6d65]">
          {word}
        </span>
      ))}
    </div>
  );
}

export function SweetPointMarks({ points }: { points?: { type: string; position: string }[] }) {
  if (!points?.length) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {points.map((point, index) => (
        <span
          key={`${point.type}-${index}`}
          className="inline-flex items-center gap-1 rounded-full border border-[#e0b54e] bg-[#fdf6e3] px-2 py-0.5 text-[11px] font-semibold text-[#9a7320]"
          title={point.position || undefined}
        >
          <span className="h-1.5 w-1.5 rounded-full bg-[#e0b54e]" />
          {point.type}
        </span>
      ))}
    </div>
  );
}

export function nodeChildren(nodes: OutlineNode[], parentId: string | null): OutlineNode[] {
  return nodes
    .filter((node) => node.parent_id === parentId)
    .sort((a, b) => a.seq - b.seq || a.id.localeCompare(b.id));
}
