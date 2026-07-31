"use client";

import { Check, ChevronDown, LoaderCircle, X } from "lucide-react";
import { useState } from "react";

import type { ChapterPlan } from "@/components/editor/chapter-editor";

export type ChapterWindowItem = {
  chapter_sequence: number;
  title: string;
  plan: ChapterPlan;
};

export function ChapterWindowDialog({
  initialItems,
  onClose,
  onSave,
}: {
  initialItems: ChapterWindowItem[];
  onClose: () => void;
  onSave: (items: ChapterWindowItem[]) => Promise<void>;
}) {
  const [items, setItems] = useState<ChapterWindowItem[]>(() => JSON.parse(JSON.stringify(initialItems)));
  const [saving, setSaving] = useState(false);

  function updateItem(index: number, updater: (item: ChapterWindowItem) => ChapterWindowItem) {
    setItems((current) => current.map((item, itemIndex) => itemIndex === index ? updater(item) : item));
  }

  async function save() {
    setSaving(true);
    try {
      await onSave(items);
    } finally {
      setSaving(false);
    }
  }

  const valid = items.every((item) => item.title.trim() && item.plan.goal.trim() && item.plan.beats.some((beat) => beat.event.trim()));
  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/45 p-3 sm:p-6" role="dialog" aria-modal="true" aria-label="调整十章目录与大纲">
      <div className="flex max-h-[94vh] w-full max-w-5xl flex-col overflow-hidden rounded-md bg-[#f8f5ee] shadow-2xl">
        <header className="flex items-center justify-between border-b border-[#d8d0c2] px-5 py-4">
          <div><div className="text-xs font-semibold text-[#a63f2f]">滚动故事规划</div><h2 className="mt-1 font-editorial text-xl font-bold">调整接下来 {items.length} 章</h2></div>
          <button className="icon-button" type="button" onClick={onClose} title="关闭" aria-label="关闭"><X size={18} /></button>
        </header>
        <div className="scrollbar-thin flex-1 overflow-y-auto px-4 py-3 sm:px-6">
          <p className="mb-4 text-xs leading-5 text-[#74756e]">先确认这一段故事怎样连续推进。修改章名、每章任务和场景后统一保存，再逐章写正文。</p>
          <div className="divide-y divide-[#ded8cd] border-y border-[#ded8cd]">
            {items.map((item, index) => (
              <details key={item.chapter_sequence} className="group bg-white/45" open={index === 0}>
                <summary className="flex cursor-pointer list-none items-center gap-3 px-3 py-3">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded bg-[#252821] text-xs font-bold text-white">{item.chapter_sequence}</span>
                  <span className="min-w-0 flex-1 truncate text-sm font-semibold">{item.title}</span>
                  <span className="hidden max-w-[45%] truncate text-xs text-[#777970] sm:block">{item.plan.goal}</span>
                  <ChevronDown className="shrink-0 transition group-open:rotate-180" size={16} />
                </summary>
                <div className="grid gap-4 border-t border-[#e7e1d7] px-4 py-4 sm:grid-cols-2">
                  <PlanField label="章名" value={item.title} onChange={(value) => updateItem(index, (current) => ({ ...current, title: value, plan: { ...current.plan, title_candidates: [value] } }))} />
                  <PlanField label="本章任务" value={item.plan.goal} onChange={(value) => updateItem(index, (current) => ({ ...current, plan: { ...current.plan, goal: value } }))} />
                  <PlanField label="主要矛盾" multiline value={item.plan.conflict} onChange={(value) => updateItem(index, (current) => ({ ...current, plan: { ...current.plan, conflict: value } }))} />
                  <PlanField label="章末推动" multiline value={item.plan.hook} onChange={(value) => updateItem(index, (current) => ({ ...current, plan: { ...current.plan, hook: value } }))} />
                  <div className="sm:col-span-2">
                    <div className="mb-2 text-xs font-semibold text-[#64665f]">因果场景</div>
                    <div className="space-y-2">
                      {item.plan.beats.map((beat, beatIndex) => (
                        <label className="grid grid-cols-[24px_1fr] items-start gap-2" key={beatIndex}>
                          <span className="mt-2 text-center text-xs font-bold text-[#a63f2f]">{beatIndex + 1}</span>
                          <textarea className="field min-h-16 resize-y p-2.5 text-sm leading-5" value={beat.event} onChange={(event) => updateItem(index, (current) => ({ ...current, plan: { ...current.plan, beats: current.plan.beats.map((value, valueIndex) => valueIndex === beatIndex ? { ...value, event: event.target.value } : value) } }))} />
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
              </details>
            ))}
          </div>
        </div>
        <footer className="flex items-center justify-end gap-2 border-t border-[#d8d0c2] bg-white/60 px-5 py-4">
          <button className="secondary-button" type="button" onClick={onClose}>取消</button>
          <button className="primary-button" type="button" disabled={saving || !valid} onClick={save}>{saving ? <LoaderCircle className="animate-spin" size={16} /> : <Check size={16} />}{saving ? "正在保存" : `保存这 ${items.length} 章`}</button>
        </footer>
      </div>
    </div>
  );
}

function PlanField({ label, value, multiline = false, onChange }: { label: string; value: string; multiline?: boolean; onChange: (value: string) => void }) {
  return <label className="block text-xs font-semibold text-[#64665f]">{label}{multiline ? <textarea className="field mt-1.5 min-h-20 resize-y p-3 font-normal leading-5 text-[#292b27]" value={value} onChange={(event) => onChange(event.target.value)} /> : <input className="field mt-1.5 h-10 px-3 font-normal text-[#292b27]" value={value} onChange={(event) => onChange(event.target.value)} />}</label>;
}
