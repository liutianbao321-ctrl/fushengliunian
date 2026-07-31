"use client";

import { ArrowRight, LoaderCircle, Sparkles } from "lucide-react";
import { useState } from "react";

import { apiFetch } from "@/lib/api";
import { useAppStore } from "@/lib/store";

type Direction = {
  title: string;
  description: string;
  pros: string;
  cons: string;
};

export function ChapterDirections({
  projectId,
  chapterSequence,
}: {
  projectId: string;
  chapterSequence: number;
}) {
  const token = useAppStore((s) => s.token);
  const [directions, setDirections] = useState<Direction[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function fetchDirections() {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch<{ directions: Direction[] }>(
        "/ai/chapter-directions",
        {
          method: "POST",
          body: JSON.stringify({ project_id: projectId, chapter_sequence: chapterSequence }),
        },
        token,
      );
      setDirections(res.directions);
      setSelected(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成失败");
    } finally {
      setLoading(false);
    }
  }

  if (directions.length === 0) {
    return (
      <div className="rounded-lg border border-[#d8d1c4] bg-[#faf9f6] p-5">
        <h3 className="flex items-center gap-2 text-sm font-bold">
          <ArrowRight size={16} className="text-[#4e6859]" />
          规划下一章
        </h3>
        <p className="mt-2 text-xs text-[#74756e]">结合当前剧情，生成三种自然连贯的推进方案</p>
        {error && <p className="mt-2 text-xs text-[#a63f2f]">{error}</p>}
        <button
          type="button"
          className="mt-3 flex items-center gap-1.5 rounded-md border border-[#4e6859] px-3 py-1.5 text-xs font-medium text-[#4e6859] transition hover:bg-[#4e6859] hover:text-white"
          disabled={loading}
          onClick={fetchDirections}
        >
          {loading ? <LoaderCircle className="animate-spin" size={14} /> : <Sparkles size={14} />}
          {loading ? "正在规划..." : "规划下一章"}
        </button>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-[#d8d1c4] bg-[#faf9f6] p-4">
      <h3 className="flex items-center gap-2 text-sm font-bold">
        <ArrowRight size={16} className="text-[#4e6859]" />
        下一章可以这样写
      </h3>
      <div className="mt-3 space-y-2">
        {directions.map((dir, i) => (
          <button
            key={i}
            type="button"
            onClick={() => setSelected(i)}
            className={`w-full rounded-md border p-3 text-left transition ${
              selected === i
                ? "border-[#4e6859] bg-[#edf1ec]"
                : "border-[#d8d1c4] bg-white/65 hover:bg-white"
            }`}
          >
            <div className="text-sm font-semibold">{dir.title}</div>
            <p className="mt-1 text-xs leading-5 text-[#585a54]">{dir.description}</p>
            <div className="mt-2 flex gap-4 text-xs text-[#74756e]">
              <span className="text-[#4e6859]">优势：{dir.pros}</span>
              <span className="text-[#a63f2f]">风险：{dir.cons}</span>
            </div>
          </button>
        ))}
      </div>
      <button
        type="button"
        className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-md border border-[#d8d1c4] py-2 text-xs text-[#74756e] transition hover:bg-white"
        disabled={loading}
        onClick={fetchDirections}
      >
        {loading ? <LoaderCircle className="animate-spin" size={14} /> : <Sparkles size={14} />}
        换一批
      </button>
    </div>
  );
}
