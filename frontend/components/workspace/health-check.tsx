"use client";

import { Activity, LoaderCircle, Sparkles } from "lucide-react";
import { useState } from "react";

import { apiFetch } from "@/lib/api";
import { useAppStore } from "@/lib/store";

type HealthCheck = {
  overall_score: number;
  pacing_verdict: string;
  consistency_issues: string[];
  improvement_suggestions: string[];
};

export function HealthCheck({
  projectId,
  chapterRange,
}: {
  projectId: string;
  chapterRange: [number, number];
}) {
  const token = useAppStore((s) => s.token);
  const [data, setData] = useState<HealthCheck | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function fetchCheck() {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch<HealthCheck>(
        `/projects/${projectId}/health-check?start=${chapterRange[0]}&end=${chapterRange[1]}`,
        {},
        token,
      );
      setData(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "检查失败");
    } finally {
      setLoading(false);
    }
  }

  if (!data) {
    return (
      <div className="rounded-lg border border-[#d8d1c4] bg-[#faf9f6] p-5">
        <h3 className="flex items-center gap-2 text-sm font-bold">
          <Activity size={16} className="text-[#d9ad62]" />
          作品体检
        </h3>
        <p className="mt-2 text-xs text-[#74756e]">检测已有章节的节奏、一致性、潜在问题</p>
        {error && <p className="mt-2 text-xs text-[#a63f2f]">{error}</p>}
        <button
          type="button"
          className="mt-3 flex items-center gap-1.5 rounded-md border border-[#d9ad62] px-3 py-1.5 text-xs font-medium text-[#d9ad62] transition hover:bg-[#d9ad62] hover:text-white"
          disabled={loading}
          onClick={fetchCheck}
        >
          {loading ? <LoaderCircle className="animate-spin" size={14} /> : <Sparkles size={14} />}
          {loading ? "检测中..." : "开始体检"}
        </button>
      </div>
    );
  }

  const scoreColor = data.overall_score >= 7 ? "text-[#4e6859]" : data.overall_score >= 4 ? "text-[#d9ad62]" : "text-[#a63f2f]";

  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-[#d8d1c4] bg-[#faf9f6] p-4">
        <div className="flex items-center justify-between">
          <h3 className="flex items-center gap-2 text-sm font-bold">
            <Activity size={16} className="text-[#d9ad62]" />
            作品体检报告
          </h3>
          <span className={`text-2xl font-bold ${scoreColor}`}>
            {data.overall_score}<span className="text-sm font-normal text-[#74756e]">/10</span>
          </span>
        </div>
        <p className="mt-2 text-xs text-[#585a54]">节奏：{data.pacing_verdict}</p>
      </div>

      {data.consistency_issues.length > 0 && (
        <div className="rounded-lg border border-[#d8d1c4] bg-[#faf9f6] p-4">
          <h4 className="text-xs font-semibold text-[#a63f2f]">一致性问题</h4>
          <ul className="mt-2 space-y-1">
            {data.consistency_issues.map((issue, i) => (
              <li key={i} className="text-xs text-[#585a54]">{issue}</li>
            ))}
          </ul>
        </div>
      )}

      {data.improvement_suggestions.length > 0 && (
        <div className="rounded-lg border border-[#d8d1c4] bg-[#faf9f6] p-4">
          <h4 className="text-xs font-semibold text-[#4e6859]">改进建议</h4>
          <ul className="mt-2 space-y-1">
            {data.improvement_suggestions.map((sug, i) => (
              <li key={i} className="text-xs text-[#585a54]">{sug}</li>
            ))}
          </ul>
        </div>
      )}

      <button
        type="button"
        className="flex w-full items-center justify-center gap-1.5 rounded-md border border-[#d8d1c4] py-2 text-xs text-[#74756e] transition hover:bg-white"
        disabled={loading}
        onClick={fetchCheck}
      >
        {loading ? <LoaderCircle className="animate-spin" size={14} /> : <Sparkles size={14} />}
        重新检测
      </button>
    </div>
  );
}
