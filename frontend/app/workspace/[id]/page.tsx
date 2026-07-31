"use client";

import Link from "next/link";
import { ArrowLeft, BookOpenText, Check, Download, GitBranch, LibraryBig, LoaderCircle, Pencil, Settings2, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";

import { ChapterEditor, ChapterPlanDialog, type ChapterPlan, type RewriteOptions } from "@/components/editor/chapter-editor";
import { ProjectInfoPanel } from "@/components/info-panel/project-info-panel";
import { ChapterSidebar } from "@/components/sidebar/chapter-sidebar";
import { apiFetch } from "@/lib/api";
import { getBeatCard, updateBeatCard, type BeatCard, type BeatCardFields } from "@/lib/blueprint";
import { projectStreamRequest } from "@/lib/sse";
import { useAppStore } from "@/lib/store";


type Chapter = {
  id?: string;
  volume_sequence: number;
  chapter_sequence: number;
  title: string;
  status: string;
  content: string;
  summary: string;
  beat_sheet?: ChapterPlan;
  quality_scores?: Record<string, { passed?: boolean; score?: number }>;
  generation_log?: Record<string, unknown>;
};

type BiblePage = { id: string; title: string; category: string; content: string };
type Foreshadowing = { content: string; planted_chapter: number };
type StatusPayload = {
  active: boolean; current_chapter: number; total_chapters: number;
  run_status?: string | null;
  current_node?: string | null; attempt?: number;
  error?: string | null;
  last_event?: { type: string; error?: string };
  auto_write?: boolean;
  operation?: "write" | "rewrite" | "optimize" | null;
};
export default function WorkspacePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const params = useParams<{ id: string }>();
  const { token, hydrate } = useAppStore();
  const [ready, setReady] = useState(false);
  const projectId = params.id;
  const [project, setProject] = useState<{ title: string; current_chapter: number; total_chapters: number } | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [selectedSequence, setSelectedSequence] = useState(1);
  const [selectedChapter, setSelectedChapter] = useState<Chapter | null>(null);
  const [sceneContract, setSceneContract] = useState<BeatCard | null>(null);
  const [draftBuffer, setDraftBuffer] = useState("");
  const [bible, setBible] = useState<BiblePage[]>([]);
  const [foreshadowing, setForeshadowing] = useState<Foreshadowing[]>([]);
  const [streamLog, setStreamLog] = useState<string[]>([]);
  const [statusText, setStatusText] = useState("待机");
  const [isGenerating, setIsGenerating] = useState(false);
  const [activeGenerationChapter, setActiveGenerationChapter] = useState<number | null>(null);
  const [activeGenerationOperation, setActiveGenerationOperation] = useState<"write" | "rewrite" | "optimize" | null>(null);
  const [pageError, setPageError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [editingProjectTitle, setEditingProjectTitle] = useState(false);
  const [projectTitle, setProjectTitle] = useState("");
  const [planCandidates, setPlanCandidates] = useState<Record<number, ChapterPlan>>({});
  const [planningChapters, setPlanningChapters] = useState<Record<number, boolean>>({});
  const [planEditor, setPlanEditor] = useState<{ sequence: number; plan: ChapterPlan; title: string } | null>(null);
  const [rewriting, setRewriting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [autoWrite, setAutoWrite] = useState(false);
  const [exporting, setExporting] = useState(false);
  const pollRef = useRef<number | null>(null);
  const requestKeyRef = useRef<string | null>(null);
  const replaceOnNextChunkRef = useRef(false);
  const generationOperationRef = useRef<"write" | "rewrite" | "optimize" | null>(null);
  const selectedSequenceRef = useRef(1);
  const chapterRequestRef = useRef(0);
  const planRequestVersionsRef = useRef<Record<number, number>>({});

  useEffect(() => {
    hydrate();
    setReady(true);
  }, [hydrate]);

  useEffect(() => {
    if (!notice) return;
    const timeout = window.setTimeout(() => setNotice(null), 5000);
    return () => window.clearTimeout(timeout);
  }, [notice]);

  useEffect(() => {
    if (!ready) return;
    if (!token) {
      router.replace("/");
      return;
    }

    async function load() {
      const [projectData, chapterList, biblePages, foreshadowingItems] = await Promise.all([
        apiFetch<{ title: string; current_chapter: number; total_chapters: number }>(`/projects/${projectId}`, {}, token),
        apiFetch<Chapter[]>(`/projects/${projectId}/chapters`, {}, token),
        apiFetch<BiblePage[]>(`/projects/${projectId}/bible`, {}, token),
        apiFetch<Foreshadowing[]>(`/projects/${projectId}/foreshadowing`, {}, token),
      ]);
      setProject(projectData);
      setProjectTitle(projectData.title);
      setChapters(chapterList);
      const requestedSequence = Number(searchParams.get("chapter"));
      const defaultSequence = Number.isInteger(requestedSequence) && requestedSequence > 0 && requestedSequence <= projectData.total_chapters
        ? requestedSequence
        : [...chapterList].reverse().find((item) => item.content)?.chapter_sequence ?? projectData.current_chapter ?? 1;
      selectedSequenceRef.current = defaultSequence;
      setSelectedSequence(defaultSequence);
      setBible(biblePages);
      setForeshadowing(foreshadowingItems);
    }

    load().catch((err) => setPageError(err instanceof Error ? err.message : "工作台加载失败"));
  }, [projectId, ready, router, searchParams, token]);

  useEffect(() => {
    if (!token || !projectId) {
      return;
    }
    const requestId = ++chapterRequestRef.current;
    setSelectedChapter(null);
    setSceneContract(null);
    setDraftBuffer("");
    apiFetch<Chapter>(`/projects/${projectId}/chapters/${selectedSequence}`, {}, token)
      .then(async (chapter) => {
        if (requestId !== chapterRequestRef.current || chapter.chapter_sequence !== selectedSequenceRef.current) return;
        const card = chapter.id ? await getBeatCard(chapter.id, token) : null;
        if (requestId !== chapterRequestRef.current || chapter.chapter_sequence !== selectedSequenceRef.current) return;
        setSelectedChapter(chapter);
        setSceneContract(card);
        setDraftBuffer(chapter.content);
      })
      .catch(() => undefined);
  }, [projectId, selectedSequence, token]);

  function applyGenerationStatus(status: StatusPayload) {
    setIsGenerating(status.active);
    setAutoWrite(Boolean(status.auto_write));
    setActiveGenerationChapter(status.active ? status.current_chapter : null);
    setActiveGenerationOperation(status.active ? status.operation ?? "write" : null);
    setRewriting(Boolean(status.active && status.operation && status.operation !== "write"));
    generationOperationRef.current = status.active ? status.operation ?? "write" : null;
    if (status.run_status === "failed") {
      requestKeyRef.current = null;
      replaceOnNextChunkRef.current = false;
      setStatusText("生成未完成");
      setNotice(friendlyGenerationError(status.error ?? status.last_event?.error ?? "AI 暂时没有返回可用内容"));
      return;
    }
    setStatusText(status.active ? `第 ${status.current_chapter} 章 · ${generationStepLabel(status.current_node ?? undefined)}` : "待机");
  }

  async function refreshStatus() {
    if (!token) return;
    const status = await apiFetch<StatusPayload>(`/projects/${projectId}/generate/status`, {}, token);
    applyGenerationStatus(status);
  }

  useEffect(() => {
    if (!token) {
      return;
    }
    refreshStatus().catch(() => undefined);
    pollRef.current = window.setInterval(() => {
      refreshStatus().catch(() => undefined);
    }, 5000);
    return () => {
      if (pollRef.current) {
        window.clearInterval(pollRef.current);
      }
    };
  }, [projectId, token]);

  async function reloadChapters() {
    if (!token) return;
    const chapterList = await apiFetch<Chapter[]>(`/projects/${projectId}/chapters`, {}, token);
    setChapters(chapterList);
  }

  async function startGeneration() {
    if (!token) return;
    if (selectedChapter?.beat_sheet?.beats?.length && sceneContract?.status !== "confirmed") {
      setNotice("请先确认场景契约，再开始写正文");
      return;
    }
    setIsGenerating(true);
    setActiveGenerationChapter(selectedSequence);
    setActiveGenerationOperation("write");
    replaceOnNextChunkRef.current = true;
    setStatusText("正在准备本章正文");
    setNotice(null);
    generationOperationRef.current = "write";
    try {
      setStreamLog((prev) => ["正在读取章纲、前情和人物设定", ...prev].slice(0, 12));
      requestKeyRef.current ??= createRequestKey("draft");
      await apiFetch(
        `/projects/${projectId}/generate/start?chapter_sequence=${selectedSequence}`,
        { method: "POST", headers: { "Idempotency-Key": requestKeyRef.current } },
        token,
      );
      setIsGenerating(true);
      await refreshStatus();
    } catch (err) {
      setIsGenerating(false);
      setActiveGenerationChapter(null);
      setActiveGenerationOperation(null);
      replaceOnNextChunkRef.current = false;
      generationOperationRef.current = null;
      setStatusText("生成未启动");
      requestKeyRef.current = null;
      setNotice(err instanceof Error ? err.message : "启动生成失败");
    }
  }

  async function confirmChapter() {
    if (!token || !selectedChapter) return;
    const saved = await apiFetch<Chapter>(
      `/projects/${projectId}/chapters/${selectedChapter.chapter_sequence}`,
      { method: "PUT", body: JSON.stringify({ content: draftBuffer, title: selectedChapter.title, summary: selectedChapter.summary }) },
      token,
    );
    setSelectedChapter(saved);
    setDraftBuffer(saved.content);
    await reloadChapters();
  }

  async function saveProjectTitle() {
    if (!token || !projectTitle.trim()) return;
    const updated = await apiFetch<{ title: string; current_chapter: number; total_chapters: number }>(`/projects/${projectId}`, { method: "PATCH", body: JSON.stringify({ title: projectTitle.trim() }) }, token);
    setProject(updated); setProjectTitle(updated.title); setEditingProjectTitle(false);
  }

  async function exportTxt() {
    if (!token || exporting) return;
    setExporting(true);
    try {
      const result = await apiFetch<{ filename: string; content: string }>(`/projects/${projectId}/export/txt`, {}, token);
      const blob = new Blob(["\ufeff", result.content], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = result.filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setNotice(`已导出 ${result.filename}`);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "TXT 导出失败");
    } finally {
      setExporting(false);
    }
  }

  async function planChapter(sequence = selectedSequence, instruction = "") {
    if (!token) return;
    selectedSequenceRef.current = sequence;
    setSelectedSequence(sequence);
    const version = (planRequestVersionsRef.current[sequence] ?? 0) + 1;
    planRequestVersionsRef.current[sequence] = version;
    setPlanningChapters((current) => ({ ...current, [sequence]: true }));
    setNotice(null);
    try {
      const plan = await apiFetch<ChapterPlan>(`/projects/${projectId}/chapters/${sequence}/plan`, { method: "POST", body: JSON.stringify({ instruction }) }, token);
      if (planRequestVersionsRef.current[sequence] !== version) return;
      setPlanCandidates((current) => ({ ...current, [sequence]: plan }));
      const [chapter] = await Promise.all([
        apiFetch<Chapter>(`/projects/${projectId}/chapters/${sequence}`, {}, token),
        reloadChapters(),
      ]);
      if (selectedSequenceRef.current === sequence) {
        setSelectedChapter(chapter);
        setDraftBuffer(chapter.content);
      }
    }
    catch (err) { setNotice(err instanceof Error ? err.message : "章纲生成失败"); }
    finally {
      if (planRequestVersionsRef.current[sequence] === version) {
        setPlanningChapters((current) => ({ ...current, [sequence]: false }));
      }
    }
  }

  async function writeNextChapter() {
    if (!project) return;
    if (selectedChapter && draftBuffer !== selectedChapter.content) await confirmChapter();
    const savedLastWritten = chapters.reduce((latest, item) => item.content.trim() ? Math.max(latest, item.chapter_sequence) : latest, 0);
    const visibleLastWritten = selectedChapter && draftBuffer.trim() ? selectedChapter.chapter_sequence : 0;
    const lastWritten = Math.max(savedLastWritten, visibleLastWritten);
    const target = lastWritten ? lastWritten + 1 : 1;
    if (target > project.total_chapters) { setNotice("已经写到全书计划的最后一章"); return; }
    const next = chapters.find((item) => item.chapter_sequence === target);
    selectChapter(target);
    if (!next || next.status === "unplanned") void planChapter(target);
  }

  async function continueAfterCurrentChapter() {
    if (!project || !selectedChapter) return;
    if (draftBuffer !== selectedChapter.content) await confirmChapter();
    const target = selectedChapter.chapter_sequence + 1;
    if (target > project.total_chapters) { setNotice("已经写到全书计划的最后一章"); return; }
    const next = chapters.find((item) => item.chapter_sequence === target);
    selectChapter(target);
    if (!next?.beat_sheet?.beats?.length) void planChapter(target);
  }

  async function changeAutoWrite(enabled: boolean) {
    if (!token) return;
    setAutoWrite(enabled);
    try {
      await apiFetch(`/projects/${projectId}/generate/auto-write?enabled=${enabled}`, { method: "PUT" }, token);
      setNotice(enabled ? "自动连续写作已开启，当前章完成后会继续下一章" : "自动连续写作已关闭，当前章完成后停止");
    } catch (err) {
      setAutoWrite(!enabled);
      setNotice(err instanceof Error ? err.message : "自动写设置失败");
    }
  }

  async function applyPlan(sequence: number, plan: ChapterPlan, title: string) {
    if (!token) return;
    const saved = await apiFetch<Chapter>(`/projects/${projectId}/chapters/${sequence}`, { method: "PUT", body: JSON.stringify({ title, summary: plan.goal, beat_sheet: plan }) }, token);
    if (selectedSequenceRef.current === sequence) {
      setSelectedChapter(saved);
      setSceneContract(saved.id ? await getBeatCard(saved.id, token) : null);
    }
    setPlanCandidates((current) => {
      const next = { ...current };
      delete next[sequence];
      return next;
    });
    setPlanEditor(null);
    await reloadChapters();
    setNotice("章纲已保存，请确认场景契约后开始写正文");
  }

  async function saveSceneContract(fields: BeatCardFields, status: "draft" | "confirmed") {
    if (!token || !selectedChapter?.id) return;
    const saved = await updateBeatCard(selectedChapter.id, { fields, status }, token);
    setSceneContract(saved);
    setNotice(status === "confirmed" ? "场景契约已确认，将作为本章正文的直接依据" : "场景契约草稿已保存");
  }

  function selectChapter(sequence: number) {
    selectedSequenceRef.current = sequence;
    setSelectedSequence(sequence);
    setPlanEditor(null);
  }

  function changeChapterTitle(title: string) {
    if (!selectedChapter) return;
    setSelectedChapter({ ...selectedChapter, title });
  }

  async function saveChapterTitle() {
    if (!token || !selectedChapter || !selectedChapter.title.trim()) return;
    const saved = await apiFetch<Chapter>(`/projects/${projectId}/chapters/${selectedChapter.chapter_sequence}`, { method: "PUT", body: JSON.stringify({ title: selectedChapter.title.trim() }) }, token);
    setSelectedChapter(saved); await reloadChapters();
  }

  async function rewriteChapter(options: RewriteOptions, operation: "rewrite" | "optimize" = "rewrite") {
    if (!token || !selectedChapter) return;
    if (draftBuffer !== selectedChapter.content) await confirmChapter();
    setRewriting(true);
    setIsGenerating(true);
    setActiveGenerationChapter(selectedChapter.chapter_sequence);
    setActiveGenerationOperation(operation);
    replaceOnNextChunkRef.current = true;
    setStatusText(`${operation === "optimize" ? "正在优化" : "正在重写"}第 ${selectedChapter.chapter_sequence} 章`);
    setNotice(null);
    generationOperationRef.current = operation;
    try {
      await apiFetch(`/projects/${projectId}/chapters/${selectedChapter.chapter_sequence}/rewrite`, {
        method: "POST",
        body: JSON.stringify({ ...options, operation, request_key: createRequestKey("rewrite") }),
      }, token);
      setNotice(operation === "optimize" ? "AI 优化已开始，完成后会自动提示并保存新版本" : "已开始按你的要求重写，原稿会保留在历史版本中");
      await reloadChapters();
    } catch (err) {
      setIsGenerating(false);
      setActiveGenerationChapter(null);
      setActiveGenerationOperation(null);
      setRewriting(false);
      replaceOnNextChunkRef.current = false;
      setStatusText("重写未启动");
      setNotice(err instanceof Error ? err.message : "重写启动失败");
      generationOperationRef.current = null;
    }
  }

  async function optimizeChapterLight(options: RewriteOptions) {
    if (!token || !selectedChapter) return;
    if (draftBuffer !== selectedChapter.content) await confirmChapter();
    setRewriting(true);
    setStatusText(`正在快速修改第 ${selectedChapter.chapter_sequence} 章`);
    setNotice(null);
    try {
      const result = await apiFetch<{ chapter: Chapter; edits: { find: string; replace: string; reason?: string }[]; message: string }>(
        `/projects/${projectId}/chapters/${selectedChapter.chapter_sequence}/optimize-light`,
        { method: "POST", body: JSON.stringify(options) },
        token,
      );
      setSelectedChapter(result.chapter);
      setDraftBuffer(result.chapter.content);
      await reloadChapters();
      setNotice(result.edits.length ? `${result.message}，原版本已保留` : result.message);
      setStatusText("待机");
    } catch (err) {
      setStatusText("快速修改未完成");
      setNotice(err instanceof Error ? err.message : "快速修改失败");
    } finally {
      setRewriting(false);
    }
  }

  async function rewriteCurrentChapter() {
    await rewriteChapter({
      focus: ["重新创作正文"],
      preserve: ["当前章纲", "关键事件", "人物关系", "章末悬念"],
      instruction: "依据当前已确认章纲重新写成本章，不沿用旧稿措辞；保留章纲中的关键因果、人物选择与结尾推动。",
    }, "rewrite");
  }

  async function deleteCurrentChapter() {
    if (!token || !selectedChapter) return;
    if (!window.confirm(`删除第 ${selectedChapter.chapter_sequence} 章正文？\n\n章名和章纲会保留，历史版本不会物理删除。`)) return;
    setDeleting(true);
    try {
      const saved = await apiFetch<Chapter>(`/projects/${projectId}/chapters/${selectedChapter.chapter_sequence}/content`, { method: "DELETE" }, token);
      setSelectedChapter(saved);
      setDraftBuffer("");
      await reloadChapters();
      setNotice("正文已删除，章纲仍然保留，可以修改后重新写作");
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "删除正文失败");
    } finally {
      setDeleting(false);
    }
  }

  const handleChunk = useCallback((chunk: string, chapterSequence?: number) => {
    if (chapterSequence !== selectedSequenceRef.current) return;
    setDraftBuffer((prev) => {
      if (replaceOnNextChunkRef.current) {
        replaceOnNextChunkRef.current = false;
        return chunk;
      }
      return `${prev}${chunk}`;
    });
  }, []);

  const handleLog = useCallback((line: string) => {
    setStreamLog((prev) => [line, ...prev].slice(0, 18));
  }, []);

  const handleGenerationError = useCallback((message: string) => {
    setIsGenerating(false);
    setActiveGenerationChapter(null);
    setActiveGenerationOperation(null);
    setRewriting(false);
    replaceOnNextChunkRef.current = false;
    requestKeyRef.current = null;
    generationOperationRef.current = null;
    setStatusText("生成未完成");
    setNotice(friendlyGenerationError(message));
  }, []);

  const handleRefresh = useCallback(async () => {
    if (!token) return;
    requestKeyRef.current = null;
    replaceOnNextChunkRef.current = false;
    const chapterList = await apiFetch<Chapter[]>(`/projects/${projectId}/chapters`, {}, token);
    setChapters(chapterList);
    const currentSequence = selectedSequenceRef.current;
    if (currentSequence) {
      const refreshed = await apiFetch<Chapter>(`/projects/${projectId}/chapters/${currentSequence}`, {}, token);
      setSelectedChapter(refreshed);
      setDraftBuffer(refreshed.content);
    }
    const status = await apiFetch<StatusPayload>(`/projects/${projectId}/generate/status`, {}, token);
    applyGenerationStatus(status);
  }, [projectId, token]);

  const handleGenerationComplete = useCallback(async (chapterSequence: number, reviewRequired = false) => {
    const operation = generationOperationRef.current;
    const label = operation === "optimize" ? "AI 优化" : operation === "rewrite" ? "正文重写" : "正文生成";
    setNotice(reviewRequired ? `${label}已完成，但仍有问题需要你确认` : `${label}已完成，最新版本已经保存`);
    setActiveGenerationChapter(null);
    setActiveGenerationOperation(null);
    setIsGenerating(false);
    setRewriting(false);
    generationOperationRef.current = null;
    await handleRefresh();
  }, [handleRefresh]);

  const writtenChapters = chapters.filter((item) => item.content.trim()).length;
  const chapterProgress = project ? Math.min(100, (writtenChapters / Math.max(project.total_chapters, 1)) * 100) : 0;
  const progressLabel = writtenChapters > 0 && chapterProgress < 1 ? "<1%" : `${Math.round(chapterProgress)}%`;
  const nextSequence = selectedChapter && project && selectedChapter.chapter_sequence < project.total_chapters ? selectedChapter.chapter_sequence + 1 : null;
  const nextChapter = nextSequence ? chapters.find((item) => item.chapter_sequence === nextSequence) : undefined;

  return (
    <main className="min-h-screen pb-5">
      <header className="border-b border-black/10 bg-[#f8f5ee]/92 backdrop-blur-xl">
        <div className="app-frame flex min-h-16 flex-wrap items-center justify-between gap-3 py-2">
          <div className="flex min-w-0 items-center gap-3">
            <Link href="/bookshelf" className="icon-button shrink-0" title="返回书架" aria-label="返回书架"><ArrowLeft size={17} /></Link>
            <span className="hidden h-8 w-px bg-[#d6cfc2] sm:block" />
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-[11px] text-[#7f8078]"><BookOpenText size={13} /> 写作工作台</div>
              {editingProjectTitle ? <span className="mt-0.5 flex items-center gap-1"><input className="field h-8 max-w-64 font-editorial font-bold" value={projectTitle} onChange={(e) => setProjectTitle(e.target.value)} autoFocus /><button className="icon-button h-8 w-8" onClick={saveProjectTitle} title="保存书名"><Check size={15} /></button></span> : <button type="button" className="group mt-0.5 flex max-w-72 items-center gap-2 truncate font-editorial text-lg font-bold sm:text-xl" onClick={() => setEditingProjectTitle(true)} title="修改书名"><span className="truncate">{project?.title ?? "加载中..."}</span><Pencil className="shrink-0 opacity-0 group-hover:opacity-60" size={13} /></button>}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="mr-1 hidden items-center gap-2 text-xs text-[#676962] sm:inline-flex">
              <span className={`status-dot ${isGenerating ? "is-live" : ""}`} /> {statusText}
            </span>
            <button type="button" className="secondary-button" disabled={exporting} onClick={() => void exportTxt()} title="导出 TXT">
              {exporting ? <LoaderCircle className="animate-spin" size={16} /> : <Download size={16} />}
              <span className="hidden sm:inline">导出 TXT</span>
            </button>
            <Link href={`/settings/${projectId}`} className="secondary-button">
              <Settings2 size={16} />
              <span className="hidden sm:inline">设定管理</span>
            </Link>
            <Link href={`/projects/${projectId}/blueprint`} className="secondary-button">
              <GitBranch size={16} />
              <span className="hidden sm:inline">蓝图工作台</span>
            </Link>
          </div>
        </div>
      </header>

      <div className="app-frame pt-4">
        <div className="reveal mb-4 flex flex-wrap items-center justify-between gap-3 rounded-md border border-black/10 bg-white/55 px-4 py-2.5 text-xs text-[#74766f]">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-2"><LibraryBig size={14} /> 全书进度</span>
            <span>已写 {writtenChapters} / {project?.total_chapters ?? 0} 章</span>
          </div>
          <div className="flex min-w-40 items-center gap-3">
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[#dfd9ce]"><div className="h-full bg-[#a63f2f] transition-[width] duration-700" style={{ width: `${Math.max(chapterProgress, writtenChapters ? 0.5 : 0)}%` }} /></div>
            <span className="tabular-nums">{progressLabel}</span>
          </div>
        </div>

        {pageError ? <div className="mb-4 rounded-md border border-[#a63f2f]/25 bg-[#fff0ed] px-4 py-3 text-sm text-[#8e3327]">{pageError}</div> : null}

        <div className="grid gap-4 xl:grid-cols-[260px_minmax(500px,1fr)_360px]">
        <ChapterSidebar
          chapters={chapters}
          currentChapter={selectedSequence}
          isGenerating={isGenerating}
          onSelect={selectChapter}
          onWriteNext={writeNextChapter}
          autoWrite={autoWrite}
          onAutoWriteChange={changeAutoWrite}
          totalChapters={project?.total_chapters ?? 0}
        />
        <ChapterEditor
          chapter={selectedChapter}
          draftBuffer={draftBuffer}
          onChange={setDraftBuffer}
          onContentSave={confirmChapter}
          onTitleChange={changeChapterTitle}
          onTitleSave={saveChapterTitle}
          onPlan={(instruction) => planChapter(selectedSequence, instruction)}
          onApplyPlan={applyPlan}
          onEditPlan={(sequence, plan, title) => setPlanEditor({ sequence, plan, title })}
          onGenerate={startGeneration}
          onRewrite={() => void rewriteCurrentChapter()}
          onDelete={() => void deleteCurrentChapter()}
          onContinue={() => void continueAfterCurrentChapter()}
          sceneContract={sceneContract}
          onSceneContractSave={saveSceneContract}
          nextSequence={nextSequence}
          nextHasPlan={Boolean(nextChapter?.beat_sheet?.beats?.length)}
          deleting={deleting}
          planning={Boolean(planningChapters[selectedSequence])}
          pendingPlan={planCandidates[selectedSequence] ?? null}
          generating={isGenerating && activeGenerationChapter === selectedSequence}
          rewriting={isGenerating && activeGenerationChapter === selectedSequence && activeGenerationOperation !== "write"}
        />
        <ProjectInfoPanel projectId={projectId} chapter={selectedChapter} bible={bible} foreshadowing={foreshadowing} onOptimize={optimizeChapterLight} onDeepOptimize={(options) => rewriteChapter(options, "optimize")} optimizing={rewriting && activeGenerationChapter === selectedSequence} />
        </div>

        {notice ? (
          <div
            className="fixed bottom-5 left-1/2 z-[60] flex w-[min(560px,calc(100vw_-_24px))] -translate-x-1/2 items-center gap-3 rounded-md bg-[#22251f] px-4 py-3 text-sm text-white shadow-xl"
            role="status"
            aria-live="polite"
          >
            <span className="min-w-0 flex-1">{notice}</span>
            <button type="button" className="flex h-7 w-7 shrink-0 items-center justify-center text-white/70 hover:text-white" onClick={() => setNotice(null)} title="关闭提示" aria-label="关闭提示">
              <X size={15} />
            </button>
          </div>
        ) : null}
      </div>

      <SseListener
        projectId={projectId}
        token={token}
        onChunk={handleChunk}
        onLog={handleLog}
        onRefresh={handleRefresh}
        onComplete={handleGenerationComplete}
        onError={handleGenerationError}
      />
      {planEditor ? <ChapterPlanDialog sequence={planEditor.sequence} initialPlan={planEditor.plan} initialTitle={planEditor.title} onClose={() => setPlanEditor(null)} onSave={applyPlan} /> : null}
    </main>
  );
}

function SseListener({
  projectId,
  token,
  onChunk,
  onLog,
  onRefresh,
  onComplete,
  onError,
}: {
  projectId: string;
  token: string | null;
  onChunk: (value: string, chapterSequence?: number) => void;
  onLog: (value: string) => void;
  onRefresh: () => Promise<void>;
  onComplete: (chapterSequence: number, reviewRequired?: boolean) => Promise<void>;
  onError: (message: string) => void;
}) {
  useEffect(() => {
    if (!token) {
      return;
    }
    const accessToken = token;
    const controller = new AbortController();
    let lastEventId = window.sessionStorage.getItem(`fushengliunian:sse:${projectId}`) ?? "0";

    async function connect() {
      let retryDelay = 1000;
      while (!controller.signal.aborted) {
        try {
          const response = await projectStreamRequest(projectId, accessToken, lastEventId, controller.signal);
          if (!response.ok || !response.body) {
            throw new Error(`SSE HTTP ${response.status}`);
          }
          retryDelay = 1000;
          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = "";

          while (!controller.signal.aborted) {
            const result = await reader.read();
            if (result.done) break;
            buffer = (buffer + decoder.decode(result.value, { stream: true })).replace(/\r\n/g, "\n");
            const chunks = buffer.split("\n\n");
            buffer = chunks.pop() ?? "";
            for (const raw of chunks) {
              const lines = raw.split("\n");
              const event = lines.find((line) => line.startsWith("event:"))?.slice(6).trim();
              const eventId = lines.find((line) => line.startsWith("id:"))?.slice(3).trim();
              const data = lines
                .filter((line) => line.startsWith("data:"))
                .map((line) => line.slice(5).trimStart())
                .join("\n");
              if (!event || !data || event === "heartbeat") continue;
              if (eventId) {
                lastEventId = eventId;
                window.sessionStorage.setItem(`fushengliunian:sse:${projectId}`, eventId);
              }
              const parsed = JSON.parse(data) as {
                chapter_sequence?: number;
                text?: string;
                progress?: number;
                step?: string;
                error?: string;
              };
              if (event === "generation_chunk" && parsed.text) onChunk(parsed.text, parsed.chapter_sequence);
              if (event === "generation_progress") {
                onLog(`第 ${parsed.chapter_sequence} 章 · ${generationStepLabel(parsed.step)} · ${parsed.progress}%`);
              }
              if (event === "generation_retry") {
                onLog(`模型响应较慢，系统正在从失败节点继续重试，不会重复已完成步骤`);
                await onRefresh();
              }
              if (event === "generation_draft_ready") {
                onLog(`第 ${parsed.chapter_sequence} 章正文已生成，正在记录人物与设定`);
                await onRefresh();
              }
              if (event === "generation_complete") {
                onLog(`第 ${parsed.chapter_sequence} 章生成完成`);
                await onComplete(parsed.chapter_sequence ?? 0);
              }
              if (event === "generation_review_required") {
                onLog(`第 ${parsed.chapter_sequence} 章已完成修订，还有问题需要确认`);
                await onComplete(parsed.chapter_sequence ?? 0, true);
              }
              if (event === "generation_error") {
                const message = parsed.error ?? "AI 暂时没有返回可用内容";
                onLog(message);
                await onRefresh();
                onError(message);
              }
            }
          }
        } catch (error) {
          if (controller.signal.aborted) return;
          onLog(error instanceof Error ? `实时连接中断：${error.message}` : "实时连接中断");
        }
        await new Promise((resolve) => window.setTimeout(resolve, retryDelay));
        retryDelay = Math.min(retryDelay * 2, 15000);
      }
    }

    connect().catch(() => undefined);
    return () => controller.abort();
  }, [onChunk, onComplete, onError, onLog, onRefresh, projectId, token]);

  return null;
}

function createRequestKey(prefix: string) {
  if (typeof globalThis.crypto !== "undefined" && typeof globalThis.crypto.randomUUID === "function") {
    return `${prefix}-${globalThis.crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
}

function friendlyGenerationError(message: string) {
  if (/Observer|Skill|JSON|contract|必须是|pipeline/i.test(message)) {
    return "正文已经保留，但人物与设定检查暂时没有完成。系统会保留成功结果，重新生成时只重试未完成部分。";
  }
  if (message.includes("正文已经保留")) return message;
  return `本次生成没有完成：${message}。可以直接重新生成。`;
}

function generationStepLabel(step?: string) {
  return ({
    "world-simulator": "整理本章上下文",
    "novel-architect": "整理章纲节奏",
    "novel-guardian": "检查写作边界",
    "novel-writer": "正在写作",
    "novel-editor-humanize": "调整叙述质感",
    "novel-editor": "正在优化正文",
    "novel-humanizer": "优化自然表达",
    "novel-critic-draft": "检查正文",
    "observer-social": "核对人物与关系",
    "observer-environment": "核对时间、地点与物品",
    "observer-narrative": "检查冲突与伏笔",
    "novel-verifier": "汇总质量检查",
    "novel-critic-final": "复查润色稿",
    "novel-editor-repair": "按审稿意见再次修订",
    "novel-critic-recheck": "确认最终质量",
  } as Record<string, string>)[step ?? ""] ?? "处理本章";
}
