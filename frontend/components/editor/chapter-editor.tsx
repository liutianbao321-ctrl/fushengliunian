"use client";

import {
  ArrowDown,
  ArrowRight,
  ArrowUp,
  Check,
  FilePenLine,
  LoaderCircle,
  Maximize2,
  Minimize2,
  PenLine,
  Plus,
  RotateCcw,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";

import { SceneContract } from "@/components/workspace/scene-contract";
import type { BeatCard, BeatCardFields } from "@/lib/blueprint";

type Chapter = {
  id?: string;
  chapter_sequence: number;
  title: string;
  content: string;
  status: string;
  summary?: string;
  beat_sheet?: ChapterPlan;
};

export type ScenePlan = {
  segment: string; event: string; purpose?: string; immediate_goal?: string; obstacle?: string;
  strategy?: string; turn?: string; outcome?: string; sensory_anchor?: string; location?: string;
  characters?: string[]; trigger?: string;
};
export type ChapterPlan = {
  title_candidates: string[]; reader_experience?: string; goal: string; conflict: string; characters: string[];
  protagonist_change?: { start?: string; desire?: string; decision?: string; cost?: string; end?: string };
  opening?: { situation?: string; pressure?: string; first_action?: string };
  beats: ScenePlan[];
  style_direction?: { narrative_distance?: string; rhythm?: string; dialogue?: string; information_release?: string; prose_texture?: string };
  hook: string; ending_image?: string; must_avoid?: string[];
  creation_brief?: {
    why_this_chapter: string;
    position?: { volume_title?: string; arc_title?: string };
    due_foreshadowing?: { content: string; urgency: "overdue" | "due" | "active" }[];
    character_states?: Record<string, { field?: string; value?: unknown }[]>;
  };
};
export type RewriteOptions = { focus: string[]; preserve: string[]; instruction: string };

export function ChapterEditor({
  chapter, draftBuffer, onChange, onContentSave, onTitleChange, onTitleSave,
  onPlan, onApplyPlan, onEditPlan, onGenerate, onRewrite, onDelete, onContinue, onSceneContractSave, sceneContract, nextSequence, nextHasPlan, deleting, planning, pendingPlan, generating, rewriting,
}: {
  chapter: Chapter | null;
  draftBuffer: string;
  onChange: (value: string) => void;
  onContentSave: () => void;
  onTitleChange: (title: string) => void;
  onTitleSave: () => void;
  onPlan: (instruction?: string) => void;
  onApplyPlan: (sequence: number, plan: ChapterPlan, title: string) => void;
  onEditPlan: (sequence: number, plan: ChapterPlan, title: string) => void;
  onGenerate: () => void;
  onRewrite: () => void;
  onDelete: () => void;
  onContinue: () => void;
  sceneContract: BeatCard | null;
  onSceneContractSave: (fields: BeatCardFields, status: "draft" | "confirmed") => Promise<void>;
  nextSequence: number | null;
  nextHasPlan: boolean;
  deleting: boolean;
  planning: boolean;
  pendingPlan: ChapterPlan | null;
  generating: boolean;
  rewriting: boolean;
}) {
  const [focusMode, setFocusMode] = useState(false);
  const [selectedTitle, setSelectedTitle] = useState("");
  const [showAiPlanEdit, setShowAiPlanEdit] = useState(false);
  const [planInstruction, setPlanInstruction] = useState("");
  const dirty = chapter ? draftBuffer !== chapter.content : false;

  useEffect(() => {
    setSelectedTitle(pendingPlan?.title_candidates[0] ?? "");
  }, [pendingPlan]);

  if (!chapter) {
    return (
      <section className="tool-panel flex min-h-[520px] flex-col items-center justify-center p-8 text-center">
        <span className="flex h-12 w-12 items-center justify-center rounded-full bg-[#eee7da] text-[#a63f2f]"><FilePenLine size={22} /></span>
        <h2 className="mt-4 font-editorial text-xl font-bold">选择一章开始创作</h2>
        <p className="mt-2 text-sm text-[#7a7b74]">正文、章纲和 AI 建议会在这里展开。</p>
      </section>
    );
  }

  const hasPlan = Boolean(chapter.beat_sheet?.beats?.length);
  const hasDraft = draftBuffer.trim().length > 0;
  return (
    <>
      <section className={`${focusMode ? "fixed inset-3 z-50 shadow-2xl sm:inset-6" : "relative min-h-[620px] xl:h-[calc(100vh-164px)]"} tool-panel flex flex-col overflow-hidden transition-all`}>
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[#ded8cd] px-5 py-4">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 text-xs text-[#7d7d75]">
              <span>第 {chapter.chapter_sequence} 章</span><span>·</span>
              <span className={dirty ? "text-[#a63f2f]" : "text-[#74756e]"}>{dirty ? "有未保存修改" : "已同步"}</span>
            </div>
            <input className="mt-1 w-full min-w-0 border-0 bg-transparent font-editorial text-2xl font-bold outline-none" value={chapter.title} onChange={(event) => onTitleChange(event.target.value)} onBlur={onTitleSave} aria-label="章节名称" />
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {hasDraft ? <>
              <button className="secondary-button min-h-9 px-3 text-xs" type="button" onClick={onRewrite} disabled={generating || deleting} title="按当前章纲重新生成，保留旧版本"><RotateCcw size={15} />重写正文</button>
              <button className="icon-button text-[#a63f2f]" type="button" onClick={onDelete} disabled={generating || deleting} title="删除正文，保留章纲" aria-label="删除正文">{deleting ? <LoaderCircle className="animate-spin" size={16} /> : <Trash2 size={16} />}</button>
            </> : null}
            <button className="icon-button" type="button" title={focusMode ? "退出专注模式" : "进入专注模式"} aria-label={focusMode ? "退出专注模式" : "进入专注模式"} onClick={() => setFocusMode((value) => !value)}>
              {focusMode ? <Minimize2 size={17} /> : <Maximize2 size={17} />}
            </button>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto bg-[#f3efe7] p-3 sm:p-5">
          {planning ? <PlanLoading /> : null}

          {!hasDraft && !pendingPlan && !hasPlan && !planning ? (
            <div className="mb-4 border border-[#d8d0c2] bg-white px-6 py-8 text-center">
              <FilePenLine className="mx-auto text-[#a63f2f]" size={24} />
              <h3 className="mt-3 font-editorial text-xl font-bold">先想清楚这一章写什么</h3>
              <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-[#74756e]">AI 会结合全书路线、上一章和人物设定，先给你一份可确认的章纲。</p>
              <div className="mt-5 flex flex-wrap justify-center gap-2">
                <button className="primary-button" type="button" onClick={() => onPlan()}><Sparkles size={16} />AI 生成章纲</button>
                <button className="secondary-button" type="button" onClick={() => document.getElementById("chapter-body")?.focus()}><PenLine size={16} />直接写正文</button>
              </div>
            </div>
          ) : null}

          {pendingPlan ? (
            <div className="mb-4 border border-[#d8d0c2] bg-white p-5 sm:p-6">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div><div className="text-xs font-semibold text-[#a63f2f]">AI 章纲候选</div><h3 className="mt-1 font-editorial text-lg font-bold">看看是否符合你想写的方向</h3></div>
                <div className="flex gap-2"><button className="secondary-button min-h-9 px-3 text-xs" type="button" onClick={() => onEditPlan(chapter.chapter_sequence, pendingPlan, selectedTitle || chapter.title)}><FilePenLine size={14} />先手动调整</button><button className="secondary-button min-h-9 px-3 text-xs" type="button" onClick={() => onPlan()} disabled={planning}><RotateCcw size={14} />换一版</button></div>
              </div>
              <div className="mt-4 grid gap-2 sm:grid-cols-3">
                {pendingPlan.title_candidates.map((title) => <button key={title} className={`min-h-11 rounded-md border px-3 py-2 text-sm ${selectedTitle === title ? "border-[#a63f2f] bg-[#fff4ef] text-[#8e3327]" : "border-[#d8d1c4] hover:border-[#a63f2f]"}`} type="button" onClick={() => setSelectedTitle(title)}>{title}</button>)}
              </div>
              <div className="mt-5 border-y border-[#e4ded3] py-4"><div className="text-xs font-semibold text-[#81735f]">这一章主要写</div><p className="mt-1 text-sm leading-6">{pendingPlan.goal || pendingPlan.reader_experience}</p>{pendingPlan.conflict ? <p className="mt-2 text-xs leading-5 text-[#7b625b]"><strong>主要矛盾：</strong>{pendingPlan.conflict}</p> : null}</div>
              <ol className="relative mt-5 pl-1"><span className="absolute bottom-4 left-[13px] top-2 w-px bg-[#d7c9b7]" />{pendingPlan.beats.map((beat, index) => <li className="relative pb-5 pl-9 text-sm leading-6 last:pb-1" key={`${beat.segment}-${index}`}><span className="absolute left-0 top-0 flex h-6 w-6 items-center justify-center rounded-full bg-[#4e6859] text-[11px] font-bold text-white">{index + 1}</span><div className="text-xs font-semibold text-[#81735f]">{beat.segment || `情节段 ${index + 1}`}</div><p className="mt-1 text-[#444741]">{beat.event}</p></li>)}</ol>
              <p className="mt-4 border-l-2 border-[#b88937] pl-3 text-sm leading-6"><strong>结尾悬念：</strong>{pendingPlan.hook}</p>
              <button className="primary-button mt-5 w-full" type="button" disabled={!selectedTitle} onClick={() => onApplyPlan(chapter.chapter_sequence, pendingPlan, selectedTitle)}><Check size={16} />采用这份章纲</button>
            </div>
          ) : null}

          {hasPlan && !pendingPlan ? (
            <div className="mb-4 border border-[#4e6859]/25 bg-[#edf1ec] p-4">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div className="min-w-0"><div className="flex items-center gap-2"><Check className="text-[#4e6859]" size={16} /><strong className="text-sm">章纲已采用</strong></div><p className="mt-1 line-clamp-2 text-xs leading-5 text-[#676962]">{chapter.beat_sheet?.goal || chapter.summary || "本章方向已经明确"}</p></div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  <button className="secondary-button min-h-10 px-3 text-xs" type="button" onClick={() => onEditPlan(chapter.chapter_sequence, chapter.beat_sheet!, chapter.title)} disabled={planning || generating}><FilePenLine size={14} />人工修改</button>
                  <button className="secondary-button min-h-10 px-3 text-xs" type="button" onClick={() => setShowAiPlanEdit((value) => !value)} disabled={planning || generating}><Sparkles size={14} />AI 修改</button>
                  <button className="secondary-button min-h-10 px-3 text-xs" type="button" onClick={() => onPlan()} disabled={planning || generating} title="生成一份全新的候选，不会直接覆盖当前章纲"><RotateCcw size={14} />重新生成</button>
                  {!hasDraft ? <button className="primary-button min-h-10 px-4" type="button" onClick={onGenerate} disabled={generating || planning || sceneContract?.status !== "confirmed"} title={sceneContract?.status === "confirmed" ? "开始写作" : "请先确认下方场景契约"}>{generating ? <LoaderCircle className="animate-spin" size={16} /> : <Sparkles size={16} />}{generating ? "正在写作" : sceneContract?.status === "confirmed" ? "开始写作" : "先确认场景契约"}</button> : null}
                </div>
              </div>
              {showAiPlanEdit ? <div className="mt-4 border-t border-[#cfd8d0] pt-4"><label className="block text-xs font-semibold text-[#555d56]">告诉 AI 要怎么改<textarea className="field mt-2 min-h-20 bg-white p-3 font-normal leading-6" value={planInstruction} onChange={(event) => setPlanInstruction(event.target.value)} placeholder="例如：保留物理超度这条主线，把第二段冲突改得更合理，结尾不要出现新人物。" /></label><div className="mt-3 flex justify-end"><button className="primary-button min-h-9 px-3 text-xs" type="button" disabled={planning || planInstruction.trim().length < 2} onClick={() => { onPlan(planInstruction.trim()); setPlanInstruction(""); setShowAiPlanEdit(false); }}><Sparkles size={14} />生成修改候选</button></div></div> : null}
            </div>
          ) : null}

          {hasPlan && !pendingPlan && !hasDraft ? <SceneContract card={sceneContract} plan={chapter.beat_sheet} disabled={planning || generating} onSave={onSceneContractSave} /> : null}

          {generating && (rewriting || !draftBuffer) ? <div className="mb-3 flex items-center gap-3 border-l-2 border-[#a63f2f] bg-white px-4 py-3 text-sm"><LoaderCircle className="animate-spin text-[#a63f2f]" size={17} /><span><strong>{rewriting ? "正在按要求优化本章" : "正在自动写本章"}</strong><span className="ml-2 text-xs text-[#74756e]">AI 正在读取章纲、前情与人物设定</span></span></div> : null}
          <textarea id="chapter-body" className="scrollbar-thin h-full min-h-[460px] w-full resize-none rounded-md border border-[#d8d0c2] bg-[#fffefa] px-5 py-6 font-editorial text-[17px] leading-9 text-[#292b27] shadow-[0_4px_18px_rgba(51,44,35,0.05)] outline-none transition focus:border-[#a63f2f]/55 focus:shadow-[0_0_0_4px_rgba(166,63,47,0.06)] sm:px-8 md:text-lg" spellCheck={false} value={draftBuffer} onChange={(event) => onChange(event.target.value)} onBlur={() => { if (dirty && !generating) onContentSave(); }} placeholder={`从第 ${chapter.chapter_sequence} 章的第一句话开始...`} />
        </div>

        <div className="flex min-h-14 flex-wrap items-center justify-between gap-3 border-t border-[#ded8cd] bg-[#fbfaf6] px-4 py-3 sm:px-5">
          <span className="text-xs tabular-nums text-[#818179]">{draftBuffer.replace(/\s/g, "").length.toLocaleString()} 字</span>
          {hasDraft && nextSequence ? <button className="secondary-button min-h-9 px-3 text-xs" type="button" onClick={onContinue} disabled={generating || planning}><ArrowRight size={15} />{nextHasPlan ? `查看第 ${nextSequence} 章规划` : `规划第 ${nextSequence} 章`}</button> : null}
        </div>
      </section>
    </>
  );
}

function PlanLoading() {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const startedAt = Date.now();
    const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - startedAt) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const detail = elapsed < 20
    ? "正在读取前情与本卷任务"
    : elapsed < 60
      ? "正在生成可直接写作的情节"
      : "首选模型响应较慢，正在切换备用模型";
  return <div className="mb-4 border border-[#d8d0c2] bg-white p-6" aria-live="polite"><div className="flex items-center gap-3"><span className="relative flex h-10 w-10 items-center justify-center rounded-full bg-[#fff0e9] text-[#a63f2f]"><Sparkles className="animate-pulse" size={19} /><span className="absolute inset-0 animate-ping rounded-full border border-[#a63f2f]/20" /></span><div><h3 className="font-editorial text-lg font-bold">正在生成本章章纲</h3><p className="mt-1 text-xs text-[#74756e]">{detail} · 已用时 {elapsed} 秒</p></div></div><div className="mt-5 grid gap-2 sm:grid-cols-3">{["读取全书路线与前情", "安排人物行动与冲突", "设计章名与结尾悬念"].map((step, index) => <div className="flex items-center gap-2 border-t border-[#e4ded3] pt-3 text-xs text-[#666861]" key={step}><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#a63f2f]" style={{ animationDelay: `${index * 220}ms` }} />{step}</div>)}</div></div>;
}

export function ChapterPlanDialog({
  sequence, initialPlan, initialTitle, onClose, onSave,
}: {
  sequence: number;
  initialPlan: ChapterPlan;
  initialTitle: string;
  onClose: () => void;
  onSave: (sequence: number, plan: ChapterPlan, title: string) => Promise<void>;
}) {
  const sourceBeats = (initialPlan.beats ?? []).map((beat, index) => ({ ...beat, segment: beat.segment || `情节段 ${index + 1}` }));
  const [title, setTitle] = useState(initialTitle);
  const [plan, setPlan] = useState<ChapterPlan>(() => ({
    ...JSON.parse(JSON.stringify(initialPlan)),
    title_candidates: initialPlan.title_candidates?.length ? [...initialPlan.title_candidates] : [initialTitle],
    characters: [...(initialPlan.characters ?? [])],
    beats: sourceBeats,
    goal: initialPlan.goal || initialPlan.reader_experience || sourceBeats[0]?.event || "",
    conflict: initialPlan.conflict || sourceBeats.find((beat) => beat.obstacle)?.obstacle || "",
    hook: initialPlan.hook || sourceBeats[sourceBeats.length - 1]?.outcome || sourceBeats[sourceBeats.length - 1]?.event || "",
    reader_experience: initialPlan.reader_experience || initialPlan.goal || sourceBeats[0]?.event || "",
  }));
  const [saving, setSaving] = useState(false);

  function updateBeat(index: number, field: keyof ScenePlan, value: string | string[]) {
    setPlan((current) => ({
      ...current,
      beats: current.beats.map((beat, beatIndex) => beatIndex === index ? { ...beat, [field]: value } : beat),
    }));
  }

  function moveBeat(index: number, direction: -1 | 1) {
    setPlan((current) => {
      const target = index + direction;
      if (target < 0 || target >= current.beats.length) return current;
      const beats = [...current.beats];
      [beats[index], beats[target]] = [beats[target], beats[index]];
      return { ...current, beats };
    });
  }

  function addBeat() {
    setPlan((current) => ({
      ...current,
      beats: [...current.beats, {
        segment: `情节段 ${current.beats.length + 1}`,
        location: "",
        characters: [],
        event: "",
        obstacle: "",
        outcome: "",
      }],
    }));
  }

  const canSave = Boolean(title.trim() && plan.beats.length >= 1 && plan.beats.length <= 8 && plan.beats.every((beat) => beat.event.trim()));
  return <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/45 p-3 backdrop-blur-sm sm:p-6" role="dialog" aria-modal="true" aria-label={`修改第 ${sequence} 章章纲`}>
    <div className="flex max-h-[94vh] w-full max-w-4xl flex-col overflow-hidden bg-[#fbfaf6] shadow-2xl sm:rounded-md">
      <div className="flex items-start justify-between border-b border-[#ded8cd] px-5 py-4 sm:px-6">
        <div><div className="text-xs font-semibold text-[#a63f2f]">第 {sequence} 章</div><h2 className="mt-1 font-editorial text-xl font-bold">这一章准备怎么写</h2></div>
        <button className="icon-button" type="button" onClick={onClose} title="关闭" aria-label="关闭"><X size={17} /></button>
      </div>
      <div className="scrollbar-thin flex-1 overflow-y-auto px-5 py-5 sm:px-6">
        <section>
          <h3 className="font-editorial text-lg font-bold">先看整体</h3>
          <p className="mt-1 text-xs leading-5 text-[#77786f]">只要主线和情节顺序清楚，就可以保存。其他细节都不是必填。</p>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
          <PlanInput label="章名" value={title} onChange={setTitle} />
            <PlanInput label="主要人物（选填）" value={(plan.characters ?? []).join("、")} onChange={(value) => setPlan((current) => ({ ...current, characters: value.split(/[、,，]/).map((item) => item.trim()).filter(Boolean) }))} />
            <PlanTextarea label="这一章主要写什么" value={plan.goal} onChange={(value) => setPlan((current) => ({ ...current, goal: value, reader_experience: value }))} />
            <PlanTextarea label="主要矛盾（选填）" value={plan.conflict} onChange={(value) => setPlan((current) => ({ ...current, conflict: value }))} />
            <div className="md:col-span-2"><PlanTextarea label="结尾留下什么悬念（选填）" value={plan.hook} onChange={(value) => setPlan((current) => ({ ...current, hook: value }))} /></div>
          </div>
        </section>

        <section className="mt-6 border-t border-[#ded8cd] pt-5">
          <div className="flex items-center justify-between gap-4"><div><h3 className="font-editorial text-lg font-bold">故事按什么顺序发生</h3><p className="mt-1 text-xs text-[#77786f]">每段用一两句话写清楚人物做了什么、局面怎么变；一个章节可以只保留一段完整现场。</p></div><button className="secondary-button min-h-9 shrink-0 px-3 text-xs" type="button" onClick={addBeat} disabled={plan.beats.length >= 8}><Plus size={14} />添加情节</button></div>
          <div className="mt-4">
            {plan.beats.map((beat, index) => <article className="border-t border-[#ded8cd] py-5 first:border-t-0 first:pt-1" key={index}>
              <div className="flex items-center gap-3"><span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#a63f2f] text-xs font-bold text-white">{index + 1}</span><input className="min-w-0 flex-1 border-0 bg-transparent font-editorial text-lg font-bold outline-none" value={beat.segment} onChange={(event) => updateBeat(index, "segment", event.target.value)} aria-label={`情节段 ${index + 1} 名称`} /><div className="flex gap-1"><button className="icon-button h-8 w-8" type="button" onClick={() => moveBeat(index, -1)} disabled={index === 0} title="上移"><ArrowUp size={14} /></button><button className="icon-button h-8 w-8" type="button" onClick={() => moveBeat(index, 1)} disabled={index === plan.beats.length - 1} title="下移"><ArrowDown size={14} /></button><button className="icon-button h-8 w-8 text-[#a63f2f]" type="button" onClick={() => setPlan((current) => ({ ...current, beats: current.beats.filter((_, beatIndex) => beatIndex !== index) }))} disabled={plan.beats.length <= 1} title="删除"><Trash2 size={14} /></button></div></div>
              <label className="mt-3 block text-xs font-semibold text-[#64665f]">这一段发生什么<textarea className="field mt-1.5 min-h-24 resize-y p-3 font-normal leading-6 text-[#292b27]" value={beat.event} onChange={(event) => updateBeat(index, "event", event.target.value)} placeholder="例如：沈晚烟尝试关闭面板，却触发首个任务的倒计时。" /></label>
              <details className="mt-3 border-l-2 border-[#d8d0c2] pl-3"><summary className="cursor-pointer text-xs font-semibold text-[#77786f]">更多细节（选填）</summary><div className="mt-3 grid gap-3 md:grid-cols-2"><PlanInput label="地点" value={beat.location ?? ""} onChange={(value) => updateBeat(index, "location", value)} /><PlanInput label="出场人物" value={(beat.characters ?? []).join("、")} onChange={(value) => updateBeat(index, "characters", value.split(/[、,，]/).map((item) => item.trim()).filter(Boolean))} /><PlanTextarea label="遇到什么阻碍" value={beat.obstacle ?? ""} onChange={(value) => updateBeat(index, "obstacle", value)} /><PlanTextarea label="最后局面变成什么样" value={beat.outcome ?? ""} onChange={(value) => updateBeat(index, "outcome", value)} /></div></details>
            </article>)}
          </div>
        </section>
      </div>
      <div className="flex items-center justify-between gap-3 border-t border-[#ded8cd] px-5 py-4 sm:px-6"><p className="text-xs text-[#8a8174]">{canSave ? "修改会直接用于本章写作" : "至少保留一段情节，并写清发生什么"}</p><div className="flex gap-2"><button className="secondary-button" type="button" onClick={onClose}>取消</button><button className="primary-button" type="button" disabled={!canSave || saving} onClick={async () => { const first = plan.beats[0]; setSaving(true); try { await onSave(sequence, { ...plan, goal: plan.goal.trim() || first.event, reader_experience: plan.reader_experience?.trim() || plan.goal.trim() || first.event, hook: plan.hook.trim() || plan.beats[plan.beats.length - 1].outcome || plan.beats[plan.beats.length - 1].event, opening: { situation: plan.opening?.situation || first.location || first.event, pressure: plan.opening?.pressure || first.obstacle || "", first_action: plan.opening?.first_action || first.event }, title_candidates: [title.trim(), ...plan.title_candidates.filter((item) => item !== title.trim())].slice(0, 3) }, title.trim()); } finally { setSaving(false); } }}>{saving ? <LoaderCircle className="animate-spin" size={16} /> : <Check size={16} />}{saving ? "正在保存" : "保存修改"}</button></div></div>
    </div>
  </div>;
}

function PlanInput({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label className="block text-xs font-semibold text-[#64665f]">{label}<input className="field mt-1.5 h-10 px-3 font-normal text-[#292b27]" value={value} onChange={(event) => onChange(event.target.value)} /></label>;
}

function PlanTextarea({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label className="block text-xs font-semibold text-[#64665f]">{label}<textarea className="field mt-1.5 min-h-20 resize-y p-3 font-normal leading-6 text-[#292b27]" value={value} onChange={(event) => onChange(event.target.value)} /></label>;
}
