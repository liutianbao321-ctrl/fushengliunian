"use client";

import {
  BookOpen,
  ChevronRight,
  Compass,
  LoaderCircle,
  Save,
  Sparkles,
  User,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { apiFetch } from "@/lib/api";
import { useAppStore } from "@/lib/store";

type Segment = {
  narrative: string;
  choices: string[];
  character_state: Record<string, unknown>;
};

type ImmersiveSession = {
  id: string;
  work_id: string;
  character_name: string;
  experience_style: string;
  segments: Segment[];
  character_state: Record<string, unknown>;
  project_id: string | null;
};

export default function ImmersivePlayPage() {
  const params = useParams();
  const router = useRouter();
  const token = useAppStore((s) => s.token);
  const sessionId = params.id as string;

  const [session, setSession] = useState<ImmersiveSession | null>(null);
  const [displayedSegments, setDisplayedSegments] = useState<Segment[]>([]);
  const [currentChoices, setCurrentChoices] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [choosing, setChoosing] = useState(false);
  const [solidifying, setSolidifying] = useState(false);
  const [showState, setShowState] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const narrativeEndRef = useRef<HTMLDivElement>(null);

  const loadSession = useCallback(async () => {
    if (!token) return;
    try {
      const data = await apiFetch<ImmersiveSession>(`/immersive/${sessionId}`, {}, token);
      setSession(data);
      if (data.segments.length > 0) {
        setDisplayedSegments(data.segments);
        const lastSegment = data.segments[data.segments.length - 1];
        setCurrentChoices(lastSegment.choices || []);
      }
    } catch {
      setError("会话不存在");
    } finally {
      setLoading(false);
    }
  }, [token, sessionId]);

  useEffect(() => {
    loadSession();
  }, [loadSession]);

  useEffect(() => {
    narrativeEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [displayedSegments]);

  async function handleChoice(index: number) {
    if (!token || choosing) return;
    setChoosing(true);
    setError(null);
    setCurrentChoices([]);
    try {
      const segment = await apiFetch<Segment>(
        `/immersive/${sessionId}/choose`,
        { method: "POST", body: JSON.stringify({ choice_index: index }) },
        token,
      );
      setDisplayedSegments((prev) => [...prev, segment]);
      setCurrentChoices(segment.choices || []);
      if (segment.character_state) {
        setSession((prev) => prev ? { ...prev, character_state: segment.character_state } : prev);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "选择失败");
      if (session) {
        const lastSegment = displayedSegments[displayedSegments.length - 1];
        setCurrentChoices(lastSegment?.choices || []);
      }
    } finally {
      setChoosing(false);
    }
  }

  async function handleSolidify() {
    if (!token) return;
    setSolidifying(true);
    try {
      const project = await apiFetch<{ id: string }>(
        `/immersive/${sessionId}/solidify`,
        { method: "POST" },
        token,
      );
      router.push(`/workspace/${project.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "固化失败");
    } finally {
      setSolidifying(false);
    }
  }

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#1a1c19]">
        <LoaderCircle className="animate-spin text-[#d9ad62]" size={32} />
      </main>
    );
  }

  if (!session) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#1a1c19] text-white">
        <p>会话不存在</p>
      </main>
    );
  }

  const charState = session.character_state || {};

  return (
    <main className="flex min-h-screen flex-col bg-[#1a1c19] text-[#e8e4dc]">
      {/* Header */}
      <header className="sticky top-0 z-10 border-b border-white/10 bg-[#1a1c19]/95 backdrop-blur-sm">
        <div className="mx-auto flex h-14 max-w-4xl items-center justify-between px-4">
          <div className="flex items-center gap-3">
            <Compass size={18} className="text-[#d9ad62]" />
            <span className="text-sm font-semibold">{session.character_name} 的旅程</span>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setShowState(!showState)}
              className="flex items-center gap-1.5 rounded-md border border-white/15 px-3 py-1.5 text-xs text-white/70 hover:bg-white/5"
            >
              <User size={14} />
              状态
            </button>
            <button
              type="button"
              onClick={handleSolidify}
              disabled={solidifying || displayedSegments.length < 2}
              className="flex items-center gap-1.5 rounded-md border border-[#d9ad62]/40 px-3 py-1.5 text-xs text-[#d9ad62] hover:bg-[#d9ad62]/10 disabled:opacity-40"
            >
              {solidifying ? <LoaderCircle className="animate-spin" size={14} /> : <Save size={14} />}
              固化为小说
            </button>
            <Link
              href="/bookshelf"
              className="flex items-center gap-1.5 rounded-md border border-white/15 px-3 py-1.5 text-xs text-white/70 hover:bg-white/5"
            >
              退出
            </Link>
          </div>
        </div>
      </header>

      <div className="relative mx-auto flex w-full max-w-4xl flex-1 flex-col px-4">
        {/* Character State Panel */}
        {showState && Object.keys(charState).length > 0 && (
          <div className="sticky top-14 z-10 mb-4 mt-4 rounded-lg border border-[#d9ad62]/20 bg-[#22251f] p-4">
            <h3 className="mb-2 text-xs font-semibold text-[#d9ad62]">角色状态</h3>
            <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
              {Object.entries(charState).map(([key, value]) => (
                <div key={key} className="rounded bg-white/5 px-2 py-1.5">
                  <span className="text-white/50">{key}：</span>
                  <span className="text-white/90">{String(value)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Narrative */}
        <div className="flex-1 py-6">
          {displayedSegments.map((seg, i) => (
            <div key={i} className="mb-8">
              <div className="prose prose-invert max-w-none">
                {seg.narrative.split("\n").map((para, j) =>
                  para.trim() ? (
                    <p key={j} className="mb-3 text-base leading-8 text-[#e8e4dc]/90">
                      {para}
                    </p>
                  ) : null,
                )}
              </div>
              {i < displayedSegments.length - 1 && (
                <div className="my-6 flex items-center gap-3 text-xs text-white/30">
                  <div className="h-px flex-1 bg-white/10" />
                  <span>第 {i + 2} 幕</span>
                  <div className="h-px flex-1 bg-white/10" />
                </div>
              )}
            </div>
          ))}
          <div ref={narrativeEndRef} />
        </div>

        {/* Choices */}
        <div className="sticky bottom-0 border-t border-white/10 bg-[#1a1c19]/95 py-5 backdrop-blur-sm">
          {choosing ? (
            <div className="flex items-center justify-center gap-2 py-4 text-sm text-[#d9ad62]">
              <LoaderCircle className="animate-spin" size={16} />
              命运正在展开...
            </div>
          ) : currentChoices.length > 0 ? (
            <div className="space-y-2">
              <p className="mb-3 text-xs font-semibold text-white/40">你的选择</p>
              {currentChoices.map((choice, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => handleChoice(i)}
                  className="group flex w-full items-center gap-3 rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-left text-sm transition hover:border-[#d9ad62]/40 hover:bg-[#d9ad62]/10"
                >
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-[#d9ad62]/40 text-xs text-[#d9ad62]">
                    {i + 1}
                  </span>
                  <span className="flex-1">{choice}</span>
                  <ChevronRight size={16} className="text-white/20 transition group-hover:text-[#d9ad62]" />
                </button>
              ))}
            </div>
          ) : displayedSegments.length > 0 ? (
            <div className="py-4 text-center text-sm text-white/40">
              故事在这里暂停了。
              <button
                type="button"
                onClick={handleSolidify}
                disabled={solidifying}
                className="ml-2 text-[#d9ad62] underline hover:no-underline"
              >
                固化为小说？
              </button>
            </div>
          ) : null}
          {error && <p className="mt-2 text-center text-sm text-[#a63f2f]">{error}</p>}
        </div>
      </div>
    </main>
  );
}
