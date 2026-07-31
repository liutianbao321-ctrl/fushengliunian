"use client";

import { Check, Save } from "lucide-react";
import { useEffect, useState } from "react";

import type { ChapterPlan } from "@/components/editor/chapter-editor";
import type { BeatCard, BeatCardFields } from "@/lib/blueprint";

const FIELDS: { key: keyof BeatCardFields; label: string; placeholder: string }[] = [
  { key: "entry_state", label: "从哪个未完瞬间进入", placeholder: "承接上一章最后的动作、对白或压力" },
  { key: "pov", label: "视角人物", placeholder: "谁在感受和判断这个场景" },
  { key: "desire", label: "此刻真正想得到什么", placeholder: "一个具体、眼前、可以失败的目标" },
  { key: "opposition", label: "谁或什么在阻止", placeholder: "阻力必须能迫使人物调整行动" },
  { key: "knowledge_boundary", label: "人物知道与不知道什么", placeholder: "避免人物凭空获得信息" },
  { key: "turn", label: "什么让局面转向", placeholder: "新事实、误判、选择或代价" },
  { key: "exit_state", label: "结束时局面怎样改变", placeholder: "写清本章真正造成的变化" },
  { key: "emotional_residue", label: "人物带走什么余波", placeholder: "未说出口的话、羞耻、误会、恐惧或决心" },
  { key: "promise_movement", label: "读者接下来等待什么", placeholder: "推进、提醒或兑现哪项期待" },
];

function normalizeFields(card: BeatCard | null, plan?: ChapterPlan): BeatCardFields {
  const source = card?.fields ?? {};
  const first = plan?.beats?.[0];
  const last = plan?.beats?.[plan.beats.length - 1];
  return {
    entry_state: source.entry_state || source.setup || plan?.opening?.situation || first?.event || "",
    pov: source.pov || plan?.characters?.[0] || "",
    desire: source.desire || source.protagonist_goal || plan?.protagonist_change?.desire || plan?.goal || "",
    opposition: source.opposition || source.external_conflict || plan?.conflict || first?.obstacle || "",
    knowledge_boundary: source.knowledge_boundary || "只使用已发布正文、现场观察与本章章纲允许的信息",
    turn: source.turn || source.twist || last?.turn || last?.event || "",
    exit_state: source.exit_state || source.gain || last?.outcome || plan?.protagonist_change?.end || "",
    emotional_residue: source.emotional_residue || source.internal_conflict || plan?.protagonist_change?.end || plan?.ending_image || "",
    promise_movement: source.promise_movement || source.expectation || plan?.hook || "",
  };
}
export function SceneContract({
  card,
  plan,
  disabled,
  onSave,
}: {
  card: BeatCard | null;
  plan?: ChapterPlan;
  disabled?: boolean;
  onSave: (fields: BeatCardFields, status: "draft" | "confirmed") => Promise<void>;
}) {
  const [fields, setFields] = useState<BeatCardFields>(() => normalizeFields(card, plan));
  const [saving, setSaving] = useState(false);

  useEffect(() => setFields(normalizeFields(card, plan)), [card, plan]);

  const complete = FIELDS.every(({ key }) => String(fields[key] ?? "").trim());
  const confirmed = card?.status === "confirmed";

  async function save(status: "draft" | "confirmed") {
    setSaving(true);
    try {
      await onSave(fields, status);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="mb-4 border border-[#d8d0c2] bg-white p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold text-[#a63f2f]">
            {confirmed ? <Check size={14} /> : null}
            {confirmed ? "场景契约已确认" : "写正文前先校准场景"}
          </div>
          <h3 className="mt-1 font-editorial text-lg font-bold">人物为什么行动，行动后留下什么</h3>
        </div>
        <div className="flex gap-2">
          <button className="secondary-button min-h-9 px-3 text-xs" type="button" disabled={disabled || saving} onClick={() => void save("draft")}>
            <Save size={14} />保存草稿
          </button>
          <button className="primary-button min-h-9 px-3 text-xs" type="button" disabled={disabled || saving || !complete} onClick={() => void save("confirmed")}>
            <Check size={14} />确认契约
          </button>
        </div>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        {FIELDS.map(({ key, label, placeholder }, index) => (
          <label className={index >= 4 ? "md:col-span-2 text-xs font-semibold text-[#64665f]" : "text-xs font-semibold text-[#64665f]"} key={key}>
            {label}
            <textarea
              className="field mt-1.5 min-h-20 resize-y p-3 font-normal leading-6 text-[#292b27]"
              value={String(fields[key] ?? "")}
              placeholder={placeholder}
              disabled={disabled}
              onChange={(event) => setFields((current) => ({ ...current, [key]: event.target.value }))}
            />
          </label>
        ))}
      </div>
    </section>
  );
}
