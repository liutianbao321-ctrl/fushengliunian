"use client";

import { AlertTriangle, CheckCircle2, ClipboardCheck, LoaderCircle, Quote, RotateCcw, XCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import { useAppStore } from "@/lib/store";

type AuditCheck = {
  category: string;
  status: "pass" | "warning" | "fail";
  finding?: string;
  quote?: string;
  reason?: string;
  suggestion?: string;
  blocking?: boolean;
};
type ReaderFeedback = {
  id: string;
  chapter_sequence: number;
  summary: string | null;
  thrill_analysis: { verdict?: "pass" | "needs_revision"; checks?: AuditCheck[] };
  created_at: string;
};

export function ReaderPanel({ projectId, chapterSequence, onFeedback }: { projectId: string; chapterSequence: number; onFeedback?: (feedback: ReaderFeedback | null) => void }) {
  const token = useAppStore((state) => state.token);
  const [feedbacks, setFeedbacks] = useState<ReaderFeedback[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const feedback = feedbacks.find((item) => item.id === selectedId) ?? feedbacks[0] ?? null;

  useEffect(() => {
    if (!token) return;
    setFeedbacks([]);
    setSelectedId(null);
    setError(null);
    apiFetch<ReaderFeedback[]>(`/projects/${projectId}/reader-feedback?chapter_sequence=${chapterSequence}`, {}, token).then((items) => {
      setFeedbacks(items);
      onFeedback?.(items[0] ?? null);
    }).catch(() => undefined);
  }, [chapterSequence, onFeedback, projectId, token]);

  async function runAudit() {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const result = await apiFetch<ReaderFeedback>(`/projects/${projectId}/reader-feedback/${chapterSequence}`, { method: "POST" }, token);
      setFeedbacks((items) => [result, ...items]);
      setSelectedId(result.id);
      onFeedback?.(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "检查失败");
    } finally {
      setLoading(false);
    }
  }

  if (!feedback) {
    return <div className="border border-[#d8d1c4] bg-[#faf9f6] p-5">
      <h3 className="flex items-center gap-2 text-sm font-bold"><ClipboardCheck size={16} className="text-[#a63f2f]" />章节审查</h3>
      <p className="mt-2 text-xs leading-5 text-[#74756e]">对照章纲、前情、人物状态和世界设定逐项核验。发现问题时必须附上正文原句。</p>
      {error ? <p className="mt-3 text-xs text-[#a63f2f]">{error}</p> : null}
      <button className="primary-button mt-4 w-full" type="button" disabled={loading} onClick={runAudit}>{loading ? <LoaderCircle className="animate-spin" size={15} /> : <ClipboardCheck size={15} />}{loading ? "正在核验" : "开始真实检查"}</button>
    </div>;
  }

  const checks = feedback.thrill_analysis?.checks ?? [];
  const blockingCount = checks.filter((item) => item.status === "fail" && item.blocking).length;
  const warningCount = checks.filter((item) => item.status === "warning" || (item.status === "fail" && !item.blocking)).length;
  return <div className="space-y-4">
    <section className={`border-l-2 px-4 py-3 ${blockingCount ? "border-[#a63f2f] bg-[#fff0ed]" : "border-[#4e6859] bg-[#edf1ec]"}`}>
      <div className="flex items-center gap-2 text-sm font-bold">{blockingCount ? <XCircle size={16} className="text-[#a63f2f]" /> : <CheckCircle2 size={16} className="text-[#4e6859]" />}{blockingCount ? `${blockingCount} 项硬伤需要处理` : "未发现阻断性问题"}</div>
      {feedback.summary ? <p className="mt-2 text-xs leading-5 text-[#585a54]">{feedback.summary}</p> : null}
      <div className="mt-2 text-[11px] text-[#777970]">{checks.length} 项检查 · {warningCount} 项建议</div>
    </section>

    <div className="space-y-3">
      {checks.length ? checks.map((item, index) => <AuditRow item={item} key={`${item.category}-${index}`} />) : <div className="border border-[#d8d1c4] bg-white p-4 text-xs leading-5 text-[#74756e]">本次没有返回具体问题。</div>}
    </div>

    {error ? <p className="text-xs text-[#a63f2f]">{error}</p> : null}
    <button className="secondary-button w-full" type="button" disabled={loading} onClick={runAudit}>{loading ? <LoaderCircle className="animate-spin" size={14} /> : <RotateCcw size={14} />}{loading ? "正在重新核验" : "重新检查当前正文"}</button>

    {feedbacks.length > 1 ? <section className="border-t border-[#e4ded3] pt-3">
      <div className="text-[11px] font-semibold text-[#85857d]">历次检查 · {feedbacks.length}</div>
      <div className="mt-2 grid gap-2">{feedbacks.map((item, index) => {
        const itemChecks = item.thrill_analysis?.checks ?? [];
        const itemBlocking = itemChecks.filter((check) => check.status === "fail" && check.blocking).length;
        return <button key={item.id} type="button" className={`flex items-center justify-between border px-3 py-2 text-left text-xs ${feedback.id === item.id ? "border-[#a63f2f] bg-[#fff4ef]" : "border-[#ded8cd] bg-white"}`} onClick={() => setSelectedId(item.id)}><span>第 {feedbacks.length - index} 次</span><span className="text-[#74756e]">{itemBlocking ? `${itemBlocking} 项硬伤` : "通过"} · {new Date(item.created_at).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}</span></button>;
      })}</div>
    </section> : null}
  </div>;
}

function AuditRow({ item }: { item: AuditCheck }) {
  const hardFailure = item.status === "fail" && item.blocking;
  const Icon = item.status === "pass" ? CheckCircle2 : hardFailure ? XCircle : AlertTriangle;
  const color = item.status === "pass" ? "text-[#4e6859]" : hardFailure ? "text-[#a63f2f]" : "text-[#9a671d]";
  return <section className="border border-[#d8d1c4] bg-[#faf9f6] p-4">
    <div className="flex items-start gap-2"><Icon className={`mt-0.5 shrink-0 ${color}`} size={15} /><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><h4 className="text-xs font-bold">{item.category}</h4>{hardFailure ? <span className="bg-[#fff0ed] px-1.5 py-0.5 text-[10px] font-semibold text-[#a63f2f]">硬伤</span> : null}</div>{item.finding ? <p className="mt-1 text-xs leading-5 text-[#555852]">{item.finding}</p> : null}</div></div>
    {item.quote ? <blockquote className="mt-3 border-l-2 border-[#c6b59e] bg-white px-3 py-2 text-xs leading-5 text-[#555852]"><Quote className="mr-1 inline text-[#9a8a76]" size={12} />{item.quote}</blockquote> : null}
    {item.reason ? <p className="mt-2 text-xs leading-5 text-[#686a64]"><strong>为什么：</strong>{item.reason}</p> : null}
    {item.suggestion ? <p className="mt-1 text-xs leading-5 text-[#686a64]"><strong>怎么改：</strong>{item.suggestion}</p> : null}
  </section>;
}
