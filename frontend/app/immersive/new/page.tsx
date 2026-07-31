"use client";

import { BookOpen, Compass, LoaderCircle, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import { useAppStore } from "@/lib/store";

type ImportedWork = {
  id: string;
  title: string;
  author: string | null;
  genre: string | null;
  analysis_status: string;
};

const experienceStyles = [
  { key: "action", label: "热血战斗", desc: "亲临战场，体验每一场激斗", emoji: "⚔️" },
  { key: "romance", label: "情感体验", desc: "感受角色之间的爱恨纠葛", emoji: "💕" },
  { key: "adventure", label: "冒险探索", desc: "踏入未知领域，探索新世界", emoji: "🗺️" },
  { key: "intrigue", label: "权谋博弈", desc: "在阴谋与计策中步步为营", emoji: "🎭" },
];

function NewImmersiveContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = useAppStore((s) => s.token);
  const workId = searchParams.get("work");

  const [work, setWork] = useState<ImportedWork | null>(null);
  const [characterName, setCharacterName] = useState("");
  const [style, setStyle] = useState("action");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!workId) {
      setError("请先从导入书架选择一部作品");
      setLoading(false);
      return;
    }
    if (!token) return;
    (async () => {
      try {
        const w = await apiFetch<ImportedWork>(`/imported-works/${workId}`, {}, token);
        setWork(w);
      } catch {
        setError("作品不存在");
      } finally {
        setLoading(false);
      }
    })();
  }, [token, workId]);

  async function handleStart() {
    if (!token || !workId) return;
    setSubmitting(true);
    setError(null);
    try {
      const session = await apiFetch<{ id: string }>(
        "/immersive",
        {
          method: "POST",
          body: JSON.stringify({
            work_id: workId,
            character_name: characterName.trim() || "旅人",
            experience_style: style,
          }),
        },
        token,
      );
      router.push(`/immersive/${session.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建失败");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#f8f5ee]">
        <LoaderCircle className="animate-spin text-[#a63f2f]" size={32} />
      </main>
    );
  }

  return (
    <main className="min-h-screen pb-10">
      <header className="border-b border-black/10 bg-[#f8f5ee]/90 backdrop-blur-xl">
        <div className="app-frame flex h-16 items-center justify-between">
          <Link href="/bookshelf" className="flex items-center gap-3 font-editorial text-lg font-bold">
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#20221f] text-white">
              <BookOpen size={17} />
            </span>
            浮生流年
          </Link>
          <Link href="/import" className="secondary-button">返回导入列表</Link>
        </div>
      </header>

      <div className="app-frame pt-8 md:pt-12">
        <div className="mx-auto max-w-2xl">
          <div className="mb-8 text-center">
            <span className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-[#f0e2cd] text-[#a63f2f]">
              <Compass size={28} />
            </span>
            <h1 className="page-title mt-6">代入体验</h1>
            <p className="mt-3 text-sm text-[#74756e]">
              化身角色，亲历《{work?.title || "..."}》的世界
            </p>
          </div>

          <div className="surface p-6">
            <div className="mb-5">
              <label className="mb-1 block text-sm font-semibold">你的角色名</label>
              <input
                type="text"
                value={characterName}
                onChange={(e) => setCharacterName(e.target.value)}
                className="w-full rounded-md border border-[#d8d1c4] bg-white px-3 py-2 text-sm focus:border-[#a63f2f] focus:outline-none"
                placeholder="给自己取个名字（默认：旅人）"
              />
            </div>

            <div className="mb-5">
              <label className="mb-2 block text-sm font-semibold">体验风格</label>
              <div className="grid grid-cols-2 gap-3">
                {experienceStyles.map((s) => (
                  <button
                    key={s.key}
                    type="button"
                    onClick={() => setStyle(s.key)}
                    className={`rounded-lg border p-4 text-left transition ${
                      style === s.key
                        ? "border-[#a63f2f] bg-[#fdf8f6] shadow-sm"
                        : "border-[#d8d1c4] bg-white/65 hover:bg-white"
                    }`}
                  >
                    <div className="text-lg">{s.emoji}</div>
                    <div className="mt-1 text-sm font-semibold">{s.label}</div>
                    <div className="mt-1 text-xs text-[#74756e]">{s.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            {error && <p className="mb-4 text-sm text-[#a63f2f]">{error}</p>}

            <button
              type="button"
              className="primary-button w-full justify-center"
              disabled={submitting}
              onClick={handleStart}
            >
              {submitting ? <LoaderCircle className="animate-spin" size={17} /> : <Sparkles size={17} />}
              {submitting ? "正在生成开篇..." : "开始体验"}
            </button>
          </div>
        </div>
      </div>
    </main>
  );
}

export default function NewImmersivePage() {
  return (
    <Suspense
      fallback={(
        <main className="flex min-h-screen items-center justify-center bg-[#f8f5ee]">
          <LoaderCircle className="animate-spin text-[#a63f2f]" size={32} />
        </main>
      )}
    >
      <NewImmersiveContent />
    </Suspense>
  );
}
