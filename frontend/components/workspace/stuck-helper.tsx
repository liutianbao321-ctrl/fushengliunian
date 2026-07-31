"use client";

import { HelpCircle, Lightbulb, LoaderCircle, X } from "lucide-react";
import { useState } from "react";

import { apiFetch } from "@/lib/api";
import { useAppStore } from "@/lib/store";

export function StuckHelper({ projectId }: { projectId: string }) {
  const token = useAppStore((s) => s.token);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [tips, setTips] = useState<string[]>([]);
  const [inspirations, setInspirations] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function fetchHelp() {
    if (!token) return;
    setOpen(true);
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch<{ tips: string[]; inspiration_prompts: string[] }>(
        `/ai/stuck-help?project_id=${projectId}`,
        {},
        token,
      );
      setTips(res.tips);
      setInspirations(res.inspiration_prompts);
    } catch (err) {
      setError(err instanceof Error ? err.message : "获取失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={fetchHelp}
        className="flex items-center gap-1.5 rounded-md border border-[#d9ad62]/40 px-3 py-1.5 text-xs text-[#d9ad62] transition hover:bg-[#d9ad62]/10"
      >
        <HelpCircle size={14} />
        卡文急救
      </button>

      {open && (
        <div className="absolute right-0 top-full z-20 mt-2 w-80 rounded-lg border border-[#d8d1c4] bg-white p-4 shadow-lg">
          <div className="flex items-center justify-between">
            <h3 className="flex items-center gap-2 text-sm font-bold">
              <Lightbulb size={16} className="text-[#d9ad62]" />
              卡文急救包
            </h3>
            <button type="button" onClick={() => setOpen(false)} className="text-[#74756e] hover:text-[#20221f]">
              <X size={16} />
            </button>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-8">
              <LoaderCircle className="animate-spin text-[#d9ad62]" size={20} />
            </div>
          ) : (
            <>
              {tips.length > 0 && (
                <div className="mt-3">
                  <div className="mb-1 text-xs font-semibold text-[#585a54]">写作建议</div>
                  <ul className="space-y-1.5">
                    {tips.map((tip, i) => (
                      <li key={i} className="text-xs leading-5 text-[#585a54]">{tip}</li>
                    ))}
                  </ul>
                </div>
              )}
              {inspirations.length > 0 && (
                <div className="mt-3">
                  <div className="mb-1 text-xs font-semibold text-[#a63f2f]">灵感触发器</div>
                  <ul className="space-y-1.5">
                    {inspirations.map((ins, i) => (
                      <li key={i} className="text-xs leading-5 text-[#585a54]">{ins}</li>
                    ))}
                  </ul>
                </div>
              )}
              {error && <p className="mt-2 text-xs text-[#a63f2f]">{error}</p>}
            </>
          )}
        </div>
      )}
    </div>
  );
}
