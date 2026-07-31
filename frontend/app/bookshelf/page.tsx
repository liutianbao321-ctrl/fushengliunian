"use client";

import { ArrowRight, BookOpenText, CircleUserRound, Download, LogOut, Plus, RefreshCw, Sparkles, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import { assetPath } from "@/lib/assets";
import { useAppStore } from "@/lib/store";

type Project = {
  id: string;
  title: string;
  current_chapter: number;
  total_chapters: number;
  status: string;
  target_words: number;
  creation_mode?: string;
};

type ImportedWork = {
  id: string;
  title: string;
  author: string | null;
  total_chapters: number;
  total_words: number;
  analysis_status: string;
};

const statusNames: Record<string, string> = {
  planning: "规划中",
  writing: "写作中",
  paused: "已暂停",
  completed: "已完成",
  draft: "草稿",
};

const modeLabels: Record<string, string> = {
  original: "原创",
  continuation: "续写",
  fanfic: "同人",
  immersive: "代入",
};

const modeBadgeColors: Record<string, string> = {
  original: "bg-[#4e6859]/10 text-[#4e6859]",
  continuation: "bg-[#d9ad62]/15 text-[#9a7b3a]",
  fanfic: "bg-[#a63f2f]/10 text-[#a63f2f]",
  immersive: "bg-[#34475a]/10 text-[#34475a]",
};

const analysisStatusLabels: Record<string, string> = {
  pending: "待分析",
  analyzing: "分析中",
  completed: "已完成",
  failed: "分析失败",
};

const coverTones = ["#31483d", "#7d352c", "#34475a", "#78613a", "#574b65", "#516361"];

export default function BookshelfPage() {
  const router = useRouter();
  const { token, user, hydrate, clearSession } = useAppStore();
  const [ready, setReady] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [importedWorks, setImportedWorks] = useState<ImportedWork[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    hydrate();
    setReady(true);
  }, [hydrate]);

  useEffect(() => {
    if (!ready) return;
    if (!token) {
      router.replace("/");
      return;
    }
    setLoading(true);
    Promise.all([
      apiFetch<Project[]>("/projects", {}, token),
      apiFetch<ImportedWork[]>("/imported-works", {}, token).catch(() => [] as ImportedWork[]),
    ])
      .then(([projectItems, importedItems]) => {
        setProjects(projectItems);
        setImportedWorks(importedItems);
        setError(null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "书架加载失败"))
      .finally(() => setLoading(false));
  }, [ready, router, token]);

  function logout() {
    clearSession();
    router.replace("/");
  }

  async function deleteProject(project: Project) {
    if (!token || !window.confirm(`确认删除《${project.title}》？章节、设定和生成记录会同时删除，且无法恢复。`)) return;
    try {
      await apiFetch(`/projects/${project.id}`, { method: "DELETE" }, token);
      setProjects((items) => items.filter((item) => item.id !== project.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    }
  }

  return (
    <main className="min-h-screen pb-12">
      <header className="border-b border-black/10 bg-[#f8f5ee]/90 backdrop-blur-xl">
        <div className="app-frame flex h-16 items-center justify-between">
          <div className="flex items-center gap-3 font-editorial text-lg font-bold">
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#20221f] text-white">
              <BookOpenText size={17} />
            </span>
            浮生流年
          </div>
          <div className="flex items-center gap-2">
            <div className="mr-2 hidden items-center gap-2 text-sm text-[#676861] sm:flex">
              <CircleUserRound size={17} />
              {user?.nickname ?? "创作者"}
            </div>
            <button className="icon-button" type="button" title="退出登录" aria-label="退出登录" onClick={logout}>
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </header>

      <div className="app-frame pt-9 md:pt-12">
        {/* Header with quick actions */}
        <section className="reveal flex flex-col justify-between gap-6 border-b border-[#d4cdc0] pb-8 md:flex-row md:items-end">
          <div>
            <div className="eyebrow">我的书架</div>
            <h1 className="page-title mt-4">故事，正在长出来</h1>
            <p className="mt-4 text-sm text-[#6e7069]">
              {projects.length ? `${projects.length} 部作品正在你的书架上` : "给第一部作品留一个位置"}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3 self-start md:self-auto">
            <Link className="primary-button" href="/create">
              <Plus size={17} />
              新建原创
            </Link>
            <Link
              className="flex items-center gap-2 rounded-md border border-[#d8d1c4] bg-white/80 px-4 py-2.5 text-sm font-medium text-[#585a54] transition hover:border-[#a63f2f]/35 hover:text-[#a63f2f]"
              href="/import"
            >
              <Download size={16} />
              导入作品
            </Link>
          </div>
        </section>

        {loading ? (
          <div className="mt-8 grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
            {[0, 1, 2].map((item) => <div key={item} className="h-60 animate-pulse rounded-lg border border-black/10 bg-white/45" />)}
          </div>
        ) : null}

        {!loading && error ? (
          <section className="mt-8 flex min-h-64 flex-col items-center justify-center rounded-lg border border-dashed border-[#bdaea0] bg-white/45 px-6 text-center">
            <p className="text-sm text-[#a63f2f]">{error}</p>
            <button className="secondary-button mt-5" type="button" onClick={() => window.location.reload()}>
              <RefreshCw size={16} />
              重新加载
            </button>
          </section>
        ) : null}

        {!loading && !error && projects.length === 0 && importedWorks.length === 0 ? (
          <section className="reveal reveal-delay-1 mt-8 grid min-h-[380px] overflow-hidden rounded-lg border border-black/10 bg-[#23251f] text-white md:grid-cols-[1fr_0.85fr]">
            <div className="flex flex-col justify-center px-7 py-12 md:px-12">
              <div className="font-editorial text-3xl font-bold">书架还是空的</div>
              <p className="mt-4 max-w-md text-sm leading-7 text-white/62">从类型、故事核心和主角开始，几分钟内建立第一部作品。</p>
              <Link href="/create" className="mt-8 inline-flex items-center gap-2 self-start text-sm font-semibold text-[#e2ba72]">
                开始创建 <ArrowRight size={16} />
              </Link>
            </div>
            <div className="min-h-56 bg-cover bg-center opacity-70" style={{ backgroundImage: `url(${assetPath("/images/library-desk.jpg")})` }} />
          </section>
        ) : null}

        {/* My Works Section */}
        {!loading && !error && projects.length > 0 ? (
          <section className="mt-8">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-[#585a54]">
              <Sparkles size={15} className="text-[#a63f2f]" />
              我的作品
            </h2>
            <div className="stagger-list mt-5 grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
              {projects.map((project, index) => {
                const progress = Math.min(100, Math.round((project.current_chapter / Math.max(project.total_chapters, 1)) * 100));
                const mode = project.creation_mode ?? "original";
                return (
                  <div
                    key={project.id}
                    className="group relative grid min-h-64 grid-cols-[92px_minmax(0,1fr)] overflow-hidden rounded-lg border border-black/10 bg-[#fbfaf6]/90 shadow-[0_12px_34px_rgba(45,39,30,0.06)] transition duration-300 hover:-translate-y-1 hover:border-[#a63f2f]/35 hover:shadow-[0_20px_46px_rgba(45,39,30,0.11)]"
                  >
                    <Link href={`/workspace/${project.id}`} className="absolute inset-0 z-10" aria-label={`打开《${project.title}》`} />
                    <button type="button" className="absolute right-3 top-3 z-20 flex h-8 w-8 items-center justify-center rounded-md bg-white/90 text-[#77786f] opacity-0 shadow-sm transition hover:text-[#a63f2f] group-hover:opacity-100 focus:opacity-100" title="删除作品" onClick={() => deleteProject(project)}><Trash2 size={15} /></button>
                    <div className="relative flex items-end overflow-hidden p-3 text-white" style={{ backgroundColor: coverTones[index % coverTones.length] }}>
                      <div className="absolute inset-y-0 left-3 w-px bg-white/18" />
                      <div className="absolute right-3 top-3 h-8 w-px bg-[#e2ba72]/70" />
                      <span className="relative font-editorial text-xs leading-5 text-white/78 [writing-mode:vertical-rl]">浮生流年作品</span>
                    </div>
                    <div className="flex min-w-0 flex-col p-5">
                      <div className="flex items-center justify-between gap-3 text-xs">
                        <span className="inline-flex items-center gap-2 text-[#557061]"><span className="status-dot" />{statusNames[project.status] ?? project.status}</span>
                        <div className="flex items-center gap-2">
                          {mode !== "original" && (
                            <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${modeBadgeColors[mode] ?? "bg-gray-100 text-gray-600"}`}>
                              {modeLabels[mode] ?? mode}
                            </span>
                          )}
                          <span className="text-[#8a8980]">{progress}%</span>
                        </div>
                      </div>
                      <h2 className="mt-5 line-clamp-2 font-editorial text-2xl font-bold leading-snug">{project.title}</h2>
                      <p className="mt-3 text-xs text-[#77786f]">目标 {(project.target_words / 10000).toFixed(0)} 万字</p>
                      <div className="mt-auto pt-6">
                        <div className="h-1 overflow-hidden rounded-full bg-[#e5dfd3]">
                          <div className="h-full bg-[#a63f2f] transition-[width] duration-700" style={{ width: `${progress}%` }} />
                        </div>
                        <div className="mt-3 flex items-center justify-between text-xs text-[#77786f]">
                          <span>第 {project.current_chapter} / {project.total_chapters} 章</span>
                          <ArrowRight className="transition-transform group-hover:translate-x-1" size={16} />
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        ) : null}

        {/* Imported Works Section */}
        {!loading && !error && importedWorks.length > 0 ? (
          <section className="mt-10">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-[#585a54]">
              <Download size={15} className="text-[#d9ad62]" />
              导入书架
            </h2>
            <div className="stagger-list mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {importedWorks.map((work) => (
                <div
                  key={work.id}
                  className="rounded-lg border border-black/10 bg-[#fbfaf6]/90 p-5 shadow-sm transition hover:shadow-md"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h3 className="truncate font-editorial text-lg font-bold">{work.title}</h3>
                      <p className="mt-1 text-xs text-[#77786f]">{work.author ? `${work.author} / ` : ""}{work.total_chapters} 章</p>
                    </div>
                    {work.analysis_status && (
                      <span className={`shrink-0 rounded px-2 py-0.5 text-[10px] font-medium ${
                        work.analysis_status === "completed"
                          ? "bg-[#4e6859]/10 text-[#4e6859]"
                          : work.analysis_status === "analyzing"
                            ? "bg-[#d9ad62]/15 text-[#9a7b3a]"
                            : work.analysis_status === "failed"
                              ? "bg-[#a63f2f]/10 text-[#a63f2f]"
                              : "bg-black/5 text-[#74756e]"
                      }`}>
                        {analysisStatusLabels[work.analysis_status] ?? work.analysis_status}
                      </span>
                    )}
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <Link
                      href={`/import/${work.id}`}
                      className="rounded-md border border-[#d8d1c4] px-3 py-1.5 text-xs font-medium text-[#585a54] transition hover:border-[#a63f2f]/35 hover:text-[#a63f2f]"
                    >
                      查看详情
                    </Link>
                    {work.analysis_status === "completed" && (
                      <>
                        <Link
                          href={`/import/${work.id}`}
                          className="rounded-md border border-[#4e6859]/30 px-3 py-1.5 text-xs font-medium text-[#4e6859] transition hover:bg-[#4e6859]/10"
                        >
                          续写
                        </Link>
                        <Link
                          href={`/import/${work.id}`}
                          className="rounded-md border border-[#a63f2f]/30 px-3 py-1.5 text-xs font-medium text-[#a63f2f] transition hover:bg-[#a63f2f]/10"
                        >
                          同人
                        </Link>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>
        ) : null}
      </div>
    </main>
  );
}
