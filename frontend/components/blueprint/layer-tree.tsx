"use client";

import { ChevronRight } from "lucide-react";

import type { NodeStatus, OutlineNode, OutlineLayer } from "@/lib/blueprint";
import { LayerTag, StatusBadge, nodeChildren } from "./shared";

const STATUS_OPTIONS: NodeStatus[] = ["draft", "confirmed", "locked"];

export function LayerTree({
  nodes,
  onEdit,
  onStatusChange,
}: {
  nodes: OutlineNode[];
  onEdit: (node: OutlineNode) => void;
  onStatusChange: (node: OutlineNode, status: NodeStatus) => void;
}) {
  const roots = nodeChildren(nodes, null);
  if (!roots.length) {
    return (
      <div className="rounded-md border border-dashed border-[#cdc6b8] bg-white/50 px-6 py-12 text-center">
        <p className="font-editorial text-lg font-bold">大纲树为空</p>
        <p className="mt-2 text-sm text-[#7a7b74]">从层级树里逐级补齐 L0–L5 节点，或让 AI 生成。</p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-[#d8d1c4] bg-[#fbfaf6] p-4">
      {roots.map((root) => (
        <NodeRow key={root.id} node={root} nodes={nodes} depth={0} onEdit={onEdit} onStatusChange={onStatusChange} />
      ))}
    </div>
  );
}

function NodeRow({
  node,
  nodes,
  depth,
  onEdit,
  onStatusChange,
}: {
  node: OutlineNode;
  nodes: OutlineNode[];
  depth: number;
  onEdit: (node: OutlineNode) => void;
  onStatusChange: (node: OutlineNode, status: NodeStatus) => void;
}) {
  const children = nodeChildren(nodes, node.id);
  return (
    <div className="relative" style={{ paddingLeft: depth === 0 ? 0 : 22 }}>
      {depth > 0 ? <span className="absolute left-2 top-4 h-px w-3 bg-[#d8d1c4]" /> : null}
      <div className="group flex items-center gap-2 rounded-md px-2 py-2 transition hover:bg-[#fff7f0]">
        <ChevronRight size={14} className="shrink-0 text-[#b7b0a2]" />
        <LayerTag layer={node.layer} />
        <button type="button" className="min-w-0 flex-1 truncate text-left font-editorial text-[15px] font-bold text-[#2c2e29]" onClick={() => onEdit(node)} title={node.title}>
          {node.title || "未命名节点"}
        </button>
        <button type="button" className="text-xs text-[#8a8174] opacity-0 transition group-hover:opacity-100" onClick={() => onEdit(node)}>
          编辑
        </button>
        <select
          className="rounded border border-[#d8d1c4] bg-white px-1.5 py-1 text-[11px] font-semibold text-[#4d504a] outline-none"
          value={node.status}
          onChange={(event) => onStatusChange(node, event.target.value as NodeStatus)}
          title="修改状态"
        >
          {STATUS_OPTIONS.map((status) => (
            <option key={status} value={status}>
              {status === "draft" ? "草稿" : status === "confirmed" ? "已确认" : "已锁定"}
            </option>
          ))}
        </select>
        <StatusBadge status={node.status} />
      </div>
      {children.map((child) => (
        <NodeRow key={child.id} node={child} nodes={nodes} depth={depth + 1} onEdit={onEdit} onStatusChange={onStatusChange} />
      ))}
    </div>
  );
}

export const ALL_LAYERS: OutlineLayer[] = ["L0", "L1", "L2", "L3", "L4", "L5"];
