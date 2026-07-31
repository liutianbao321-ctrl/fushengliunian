"use client";

import { apiFetch, apiFetchOptional } from "@/lib/api";

// ---------- 类型定义（与后端契约一致）----------

export type OutlineLayer = "L0" | "L1" | "L2" | "L3" | "L4" | "L5";
export type NodeStatus = "draft" | "confirmed" | "locked";

export type SweetPoint = { type: string; position: string };
export type OutlineNodeMeta = {
  keywords?: string[];
  nine_lines?: string[];
  sweet_points?: SweetPoint[];
  foreshadow_ids?: string[];
  est_chapters?: number;
};
export type OutlineNode = {
  id: string;
  layer: OutlineLayer;
  parent_id: string | null;
  seq: number;
  title: string;
  body: string;
  status: NodeStatus;
  meta: OutlineNodeMeta;
};

export type BlueprintResponse = { nodes: OutlineNode[] };

export type UpdateNodePayload = {
  title?: string;
  body?: string;
  status?: NodeStatus;
  seq?: number;
  meta?: OutlineNodeMeta;
};

export type GenerateBlueprintPayload = {
  layer: OutlineLayer;
  parent_id?: string;
  regenerate_node_id?: string;
};

export type JobStatus = {
  job_id: string;
  status: "queued" | "running" | "completed" | "failed";
  result?: unknown;
  error?: string;
};

export type PlotLedgerEntry = {
  id: string;
  type: "person" | "item" | "dialog";
  description: string;
  planted_chapter: number;
  mentioned_chapters: number[];
  due_chapter: number;
  resolved_chapter: number | null;
  status: "open" | "reminded" | "closed" | "expired";
  is_yy: boolean;
};
export type PlotLedgerResponse = { entries: PlotLedgerEntry[] };

export type PacingConfig = {
  minor_climax_cycle: number;
  major_climax_cycle: number;
  sweet_density: number;
  mode: "ladder" | "ecg";
  opening_mode: boolean;
};

export type BeatCardFields = {
  entry_state?: string;
  pov?: string;
  desire?: string;
  opposition?: string;
  knowledge_boundary?: string;
  turn?: string;
  exit_state?: string;
  emotional_residue?: string;
  promise_movement?: string;
  setup?: string;
  external_conflict?: string;
  internal_conflict?: string;
  protagonist_goal?: string;
  opponent_goal?: string;
  difficulty?: string;
  contrast?: string;
  suppression?: string;
  trump_card?: string;
  twist?: string;
  showoff?: string;
  gain?: string;
  expectation?: string;
};
export type BeatCardStatus = "draft" | "confirmed";
export type BeatCard = {
  id: string;
  chapter_id: string;
  fields: BeatCardFields;
  status: BeatCardStatus;
};

// ---------- 九线常量 ----------

export const NINE_LINES: { key: string; color: string }[] = [
  { key: "主角性格", color: "#c0392b" },
  { key: "配角", color: "#2e86c1" },
  { key: "技能", color: "#27ae60" },
  { key: "伙伴", color: "#e67e22" },
  { key: "装备", color: "#8e44ad" },
  { key: "冒险", color: "#16a085" },
  { key: "身世", color: "#f39c12" },
  { key: "势力", color: "#34495e" },
  { key: "感情", color: "#e84393" },
];

export const BEAT_FIELD_LABELS: Partial<Record<keyof BeatCardFields, string>> = {
  setup: "前设 / 铺垫",
  external_conflict: "外部矛盾",
  internal_conflict: "内部矛盾",
  protagonist_goal: "主角目的",
  opponent_goal: "对手目的",
  difficulty: "主角面临的困难",
  contrast: "衬托 / 对比",
  suppression: "压抑（蓄力）",
  trump_card: "底牌 / 金手指",
  twist: "神转折",
  showoff: "出风头",
  gain: "得好处",
  expectation: "读者期待落点",
};

// ---------- API 封装 ----------

export async function getBlueprint(projectId: string, token: string): Promise<BlueprintResponse> {
  return apiFetch<BlueprintResponse>(`/projects/${projectId}/blueprint`, {}, token);
}

export async function updateBlueprintNode(nodeId: string, payload: UpdateNodePayload, token: string): Promise<OutlineNode> {
  return apiFetch<OutlineNode>(`/blueprint/nodes/${nodeId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  }, token);
}

export async function generateBlueprint(
  projectId: string,
  payload: GenerateBlueprintPayload,
  token: string,
): Promise<{ job_id: string }> {
  return apiFetch<{ job_id: string }>(`/projects/${projectId}/blueprint/generate`, {
    method: "POST",
    body: JSON.stringify(payload),
  }, token);
}

export async function getJob(jobId: string, token: string): Promise<JobStatus> {
  return apiFetch<JobStatus>(`/jobs/${jobId}`, {}, token);
}

export async function getPlotLedger(projectId: string, token: string): Promise<PlotLedgerResponse> {
  return apiFetch<PlotLedgerResponse>(`/projects/${projectId}/plot-ledger`, {}, token);
}

export async function getPacingConfig(projectId: string, token: string): Promise<PacingConfig> {
  return apiFetch<PacingConfig>(`/projects/${projectId}/pacing-config`, {}, token);
}

export async function updatePacingConfig(projectId: string, payload: PacingConfig, token: string): Promise<PacingConfig> {
  return apiFetch<PacingConfig>(`/projects/${projectId}/pacing-config`, {
    method: "PUT",
    body: JSON.stringify(payload),
  }, token);
}

export async function getBeatCard(chapterId: string, token: string): Promise<BeatCard | null> {
  return apiFetchOptional<BeatCard>(`/chapters/${chapterId}/beat-card`, {}, token);
}

export async function updateBeatCard(
  chapterId: string,
  payload: { fields: BeatCardFields; status: BeatCardStatus },
  token: string,
): Promise<BeatCard> {
  return apiFetch<BeatCard>(`/chapters/${chapterId}/beat-card`, {
    method: "PUT",
    body: JSON.stringify(payload),
  }, token);
}

export async function regenerateBeatCard(chapterId: string, token: string): Promise<{ job_id: string }> {
  return apiFetch<{ job_id: string }>(`/chapters/${chapterId}/beat-card/regenerate`, {
    method: "POST",
  }, token);
}
