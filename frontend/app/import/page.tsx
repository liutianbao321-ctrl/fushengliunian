"use client";

import { BookOpen, Clipboard, FileUp, LoaderCircle, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import { useAppStore } from "@/lib/store";

type ImportedWork = {
  id: string;
  title: string;
  author: string | null;
  source_platform: string | null;
  total_chapters: number;
  total_words: number;
  analysis_status: string;
  analysis_progress: number;
  created_at: string;
};

export default function ImportPage() {
  const token = useAppStore((s) => s.token);
  const [works, setWorks] = useState<ImportedWork[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [externalMode, setExternalMode] = useState(false);
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [content, setContent] = useState("");
  const [externalResult, setExternalResult] = useState("");
  const [externalPrompt, setExternalPrompt] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function loadWorks() {
    if (!token) return;
    try {
      const data = await apiFetch<ImportedWork[]>("/imported-works", {}, token);
      setWorks(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadWorks();
  }, [token]);

  async function handleUpload() {
    if (!title.trim() || !content.trim() || !token) {
      setError("请填写书名和内容");
      return;
    }
    setUploading(true);
    setError(null);
    try {
      await apiFetch(
        "/imported-works",
        {
          method: "POST",
          body: JSON.stringify({
            title: title.trim(),
            content: content.trim(),
            author: author.trim() || null,
          }),
        },
        token,
      );
      setTitle("");
      setAuthor("");
      setContent("");
      setShowForm(false);
      await loadWorks();
    } catch (err) {
      setError(err instanceof Error ? err.message : "上传失败");
    } finally {
      setUploading(false);
    }
  }

  async function openExternalMode() {
    setExternalMode(true); setShowForm(false); setError(null);
    if (token && !externalPrompt) {
      try {
        const data = await apiFetch<{ prompt: string }>("/imported-works/external-analysis-prompt", {}, token);
        setExternalPrompt(data.prompt);
      } catch (err) { setError(err instanceof Error ? err.message : "提示词加载失败"); }
    }
  }

  async function importExternalResult() {
    if (!token || !title.trim() || !externalResult.trim()) { setError("请填写书名，并粘贴网页端 AI 返回的 JSON"); return; }
    setUploading(true); setError(null);
    try {
      const work = await apiFetch<ImportedWork>("/imported-works/external-analysis", { method: "POST", body: JSON.stringify({ title: title.trim(), author: author.trim() || null, analysis_text: externalResult }) }, token);
      setTitle(""); setAuthor(""); setExternalResult(""); setExternalMode(false); await loadWorks();
      window.location.href = `/import/${work.id}`;
    } catch (err) { setError(err instanceof Error ? err.message : "逆向结果导入失败"); }
    finally { setUploading(false); }
  }

  async function handleDelete(id: string) {
    if (!token) return;
    try {
      await apiFetch(`/imported-works/${id}`, { method: "DELETE" }, token);
      setWorks((prev) => prev.filter((w) => w.id !== id));
    } catch {
      // ignore
    }
  }

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result;
      if (typeof text === "string") {
        setContent(text);
        if (!title) setTitle(file.name.replace(/\.(txt|md)$/i, ""));
      }
    };
    reader.readAsText(file);
  }

  const statusLabels: Record<string, { text: string; color: string }> = {
    pending: { text: "等待分析", color: "bg-[#f0e2cd] text-[#a63f2f]" },
    analyzing: { text: "分析中", color: "bg-[#e8f0e8] text-[#4e6859]" },
    completed: { text: "分析完成", color: "bg-[#edf1ec] text-[#4e6859]" },
    failed: { text: "分析失败", color: "bg-red-50 text-red-600" },
  };

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
          <Link href="/bookshelf" className="secondary-button">返回书架</Link>
        </div>
      </header>

      <div className="app-frame pt-8 md:pt-12">
        <div className="mb-8 flex items-end justify-between">
          <div>
            <div className="eyebrow">导入书架</div>
            <h1 className="page-title mt-4">导入外部小说</h1>
            <p className="mt-3 text-sm text-[#74756e]">导入已有小说，AI 帮你分析风格、角色、世界观，然后续写、同人、或代入体验。</p>
          </div>
          <div className="flex flex-wrap gap-2"><button type="button" className="secondary-button" onClick={openExternalMode}><Clipboard size={16} />用免费 AI 逆向</button><button type="button" className="primary-button" onClick={() => { setShowForm(!showForm); setExternalMode(false); }}><Plus size={17} />项目自己分析</button></div>
        </div>

        {externalMode && <div className="surface mb-8 p-6">
          <div className="eyebrow">免费逆向通道</div><h3 className="mt-2 text-lg font-bold">让 DeepSeek / 豆包等网页端帮你拆书</h3>
          <p className="mt-1 text-sm leading-6 text-[#74756e]">第一步复制提示词并连同小说交给免费网页端 AI；第二步把它最终返回的 JSON 粘回来。系统会校验后接入同一套续写/同人流程。</p>
          <div className="mt-4 grid gap-4 md:grid-cols-2"><label className="text-xs font-semibold text-[#585a54]">书名 *<input className="mt-1 w-full rounded-md border border-[#d8d1c4] bg-white px-3 py-2 text-sm" value={title} onChange={(e) => setTitle(e.target.value)} /></label><label className="text-xs font-semibold text-[#585a54]">作者<input className="mt-1 w-full rounded-md border border-[#d8d1c4] bg-white px-3 py-2 text-sm" value={author} onChange={(e) => setAuthor(e.target.value)} /></label></div>
          <div className="mt-4"><div className="flex items-center justify-between gap-3"><label className="text-xs font-semibold text-[#585a54]">第一步：通用逆向提示词</label><button className="secondary-button min-h-8 px-3 text-xs" type="button" onClick={() => navigator.clipboard.writeText(externalPrompt)}>复制提示词</button></div><textarea className="mt-2 w-full rounded-md border border-[#d8d1c4] bg-[#f8f5ee] px-3 py-2 text-xs leading-5" rows={8} readOnly value={externalPrompt} /></div>
          <div className="mt-4"><label className="text-xs font-semibold text-[#585a54]">第二步：粘贴网页端 AI 最终返回的 JSON *</label><textarea className="mt-2 w-full rounded-md border border-[#d8d1c4] bg-white px-3 py-2 text-xs leading-5" rows={10} value={externalResult} onChange={(e) => setExternalResult(e.target.value)} placeholder='从 {"metadata":... 开始粘贴' /></div>
          {error && <p className="mt-2 text-sm text-[#a63f2f]">{error}</p>}<div className="mt-4 flex gap-2"><button className="primary-button" type="button" disabled={uploading} onClick={importExternalResult}>{uploading ? <LoaderCircle className="animate-spin" size={16} /> : <Clipboard size={16} />}校验并导入结果</button><button className="secondary-button" type="button" onClick={() => setExternalMode(false)}>取消</button></div>
        </div>}

        {showForm && (
          <div className="surface mb-8 p-6">
            <h3 className="text-lg font-bold">上传小说文本</h3>
            <p className="mt-1 text-sm text-[#74756e]">粘贴文本或上传 .txt 文件，系统会自动识别章节</p>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs font-semibold text-[#585a54]">书名 *</label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full rounded-md border border-[#d8d1c4] bg-white px-3 py-2 text-sm focus:border-[#a63f2f] focus:outline-none"
                  placeholder="输入书名"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold text-[#585a54]">作者</label>
                <input
                  type="text"
                  value={author}
                  onChange={(e) => setAuthor(e.target.value)}
                  className="w-full rounded-md border border-[#d8d1c4] bg-white px-3 py-2 text-sm focus:border-[#a63f2f] focus:outline-none"
                  placeholder="原作者（选填）"
                />
              </div>
            </div>
            <div className="mt-4">
              <label className="mb-1 block text-xs font-semibold text-[#585a54]">小说内容 *</label>
              <div className="mb-2">
                <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-[#d8d1c4] px-3 py-2 text-sm hover:bg-[#f0ebe1]">
                  <FileUp size={15} />
                  上传 .txt 文件
                  <input type="file" accept=".txt,.md" onChange={handleFileSelect} className="hidden" />
                </label>
              </div>
              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                rows={8}
                className="w-full rounded-md border border-[#d8d1c4] bg-white px-3 py-2 text-sm focus:border-[#a63f2f] focus:outline-none"
                placeholder="粘贴小说全文..."
              />
              {content && <p className="mt-1 text-xs text-[#74756e]">已输入 {content.length} 字</p>}
            </div>
            {error && <p className="mt-2 text-sm text-[#a63f2f]">{error}</p>}
            <div className="mt-4 flex gap-3">
              <button type="button" className="primary-button" disabled={uploading} onClick={handleUpload}>
                {uploading ? <LoaderCircle className="animate-spin" size={17} /> : <FileUp size={17} />}
                {uploading ? "上传分析中..." : "开始导入分析"}
              </button>
              <button type="button" className="secondary-button" onClick={() => setShowForm(false)}>取消</button>
            </div>
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <LoaderCircle className="animate-spin text-[#a63f2f]" size={24} />
          </div>
        ) : works.length === 0 ? (
          <div className="surface py-20 text-center">
            <BookOpen className="mx-auto text-[#d8d1c4]" size={48} />
            <p className="mt-4 text-sm text-[#74756e]">还没有导入的作品</p>
            <button type="button" className="primary-button mx-auto mt-4" onClick={() => setShowForm(true)}>
              <Plus size={17} />
              导入第一本
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {works.map((work) => {
              const st = statusLabels[work.analysis_status] || statusLabels.pending;
              return (
                <div key={work.id} className="surface flex items-center justify-between p-5">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-3">
                      <Link
                        href={`/import/${work.id}`}
                        className="truncate text-base font-bold hover:text-[#a63f2f]"
                      >
                        {work.title}
                      </Link>
                      <span className={`shrink-0 rounded px-2 py-0.5 text-xs ${st.color}`}>{st.text}</span>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-3 text-xs text-[#74756e]">
                      {work.author && <span>作者：{work.author}</span>}
                      <span>{work.total_chapters} 章</span>
                      <span>{Math.round(work.total_words / 10000)} 万字</span>
                    </div>
                    {work.analysis_status === "analyzing" && (
                      <div className="mt-2 h-1.5 w-48 overflow-hidden rounded-full bg-[#ede9e0]">
                        <div
                          className="h-full bg-[#4e6859] transition-[width]"
                          style={{ width: `${Math.min(100, Math.max(0, work.analysis_progress <= 1 ? work.analysis_progress * 100 : work.analysis_progress))}%` }}
                        />
                      </div>
                    )}
                  </div>
                  <div className="flex shrink-0 gap-2">
                    {work.analysis_status === "completed" && (
                      <Link href={`/import/${work.id}`} className="secondary-button text-xs">
                        查看报告
                      </Link>
                    )}
                    <button
                      type="button"
                      onClick={() => handleDelete(work.id)}
                      className="flex h-9 w-9 items-center justify-center rounded-md text-[#74756e] hover:bg-red-50 hover:text-red-600"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </main>
  );
}
