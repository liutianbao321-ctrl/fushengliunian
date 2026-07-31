"use client";

import { LoaderCircle, X } from "lucide-react";
import { useEffect, useState } from "react";

import type { PacingConfig } from "@/lib/blueprint";

const DEFAULT_CONFIG: PacingConfig = {
  minor_climax_cycle: 3,
  major_climax_cycle: 5,
  sweet_density: 0.4,
  mode: "ladder",
  opening_mode: true,
};

export function PacingDrawer({
  open,
  initial,
  saving,
  onClose,
  onSave,
}: {
  open: boolean;
  initial: PacingConfig | null;
  saving: boolean;
  onClose: () => void;
  onSave: (config: PacingConfig) => void;
}) {
  const [config, setConfig] = useState<PacingConfig>(initial ?? DEFAULT_CONFIG);

  useEffect(() => {
    if (open) setConfig(initial ?? DEFAULT_CONFIG);
  }, [open, initial]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[80] flex justify-end bg-black/40 p-3 backdrop-blur-sm sm:p-6" role="dialog" aria-modal="true" aria-label="节奏参数">
      <div className="flex w-full max-w-md flex-col overflow-hidden bg-[#fbfaf6] shadow-2xl sm:rounded-md">
        <div className="flex items-start justify-between border-b border-[#ded8cd] px-5 py-4">
          <div>
            <div className="text-xs font-semibold text-[#a63f2f]">节奏引擎</div>
            <h2 className="mt-1 font-editorial text-xl font-bold">节拍与爽点参数</h2>
            <p className="mt-1 text-xs text-[#77786f]">这些参数会作为硬约束注入到大纲与正文生成。</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} title="关闭" aria-label="关闭"><X size={17} /></button>
        </div>

        <div className="scrollbar-thin flex-1 space-y-5 overflow-y-auto px-5 py-5">
          <NumberField label="小高潮周期（章）" hint="每几章安排一次小高潮" value={config.minor_climax_cycle} min={1} onChange={(value) => setConfig((c) => ({ ...c, minor_climax_cycle: value }))} />
          <NumberField label="大高潮周期（章）" hint="每几章安排一次大高潮" value={config.major_climax_cycle} min={1} onChange={(value) => setConfig((c) => ({ ...c, major_climax_cycle: value }))} />
          <div>
            <div className="text-xs font-semibold text-[#64665f]">爽点密度</div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={config.sweet_density}
              onChange={(event) => setConfig((c) => ({ ...c, sweet_density: Number(event.target.value) }))}
              className="mt-2 w-full accent-[#a63f2f]"
            />
            <div className="mt-1 text-xs text-[#8a8174]">{Math.round(config.sweet_density * 100)}% · 越高说明每章越密集地安排爽点</div>
          </div>
          <div>
            <div className="text-xs font-semibold text-[#64665f]">节奏形态</div>
            <div className="mt-2 grid grid-cols-2 gap-2">
              {([["ladder", "男频阶梯式"], ["ecg", "女频心电图式"]] as const).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  className={`rounded-md border px-3 py-2 text-sm font-semibold transition ${config.mode === value ? "border-[#a63f2f] bg-[#fff4ef] text-[#8e3327]" : "border-[#d8d1c4] text-[#41433f] hover:border-[#a63f2f]"}`}
                  onClick={() => setConfig((c) => ({ ...c, mode: value }))}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <label className="flex items-center justify-between rounded-md border border-[#d8d1c4] bg-white px-3 py-3">
            <span>
              <span className="text-sm font-semibold text-[#3e413c]">开篇模式</span>
              <span className="mt-0.5 block text-xs text-[#8a8174]">前 10 章自动加严开篇四要素校验</span>
            </span>
            <input
              type="checkbox"
              checked={config.opening_mode}
              onChange={(event) => setConfig((c) => ({ ...c, opening_mode: event.target.checked }))}
              className="h-5 w-5 accent-[#a63f2f]"
            />
          </label>
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-[#ded8cd] px-5 py-4">
          <button className="secondary-button" type="button" onClick={onClose}>取消</button>
          <button className="primary-button" type="button" disabled={saving} onClick={() => onSave(config)}>
            {saving ? <LoaderCircle size={16} className="animate-spin" /> : null}{saving ? "保存中" : "保存节奏参数"}
          </button>
        </div>
      </div>
    </div>
  );
}

function NumberField({ label, hint, value, min, onChange }: { label: string; hint?: string; value: number; min?: number; onChange: (value: number) => void }) {
  return (
    <label className="block">
      <span className="text-xs font-semibold text-[#64665f]">{label}</span>
      {hint ? <span className="mt-0.5 block text-[11px] text-[#8a8174]">{hint}</span> : null}
      <input
        type="number"
        min={min}
        value={value}
        onChange={(event) => onChange(Math.max(min ?? 1, Number(event.target.value) || (min ?? 1)))}
        className="field mt-1.5 h-10 w-28 px-3 font-normal tabular-nums"
      />
    </label>
  );
}
