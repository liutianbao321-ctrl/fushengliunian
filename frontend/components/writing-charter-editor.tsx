"use client";

import { ChevronDown, ChevronRight, LoaderCircle, Plus, Save, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";

type Charter = {
  narrative_focus: string;
  red_lines: string[];
  mandates: string[];
  target_readers: string;
  tone_reference: string;
};

export function CharterEditor({
  projectId,
  token,
}: {
  projectId: string;
  token: string | null;
}) {
  const [charter, setCharter] = useState<Charter>({
    narrative_focus: "",
    red_lines: [],
    mandates: [],
    target_readers: "",
    tone_reference: "",
  });
  const [expanded, setExpanded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!token) return;
    apiFetch<Charter>(`/projects/${projectId}/charter`, {}, token)
      .then((data) => {
        if (data && typeof data === "object" && !Array.isArray(data)) {
          setCharter({
            narrative_focus: data.narrative_focus || "",
            red_lines: Array.isArray(data.red_lines) ? data.red_lines : [],
            mandates: Array.isArray(data.mandates) ? data.mandates : [],
            target_readers: data.target_readers || "",
            tone_reference: data.tone_reference || "",
          });
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [projectId, token]);

  const save = useCallback(async () => {
    setSaving(true);
    setMessage("");
    try {
      await apiFetch(`/projects/${projectId}/charter`, {
        method: "PUT",
        body: JSON.stringify(charter),
      }, token);
      setMessage("创作宪章已保存");
    } catch {
      setMessage("保存失败");
    } finally {
      setSaving(false);
    }
  }, [projectId, token, charter]);

  return (
    <div className="mt-6 rounded-lg border border-[#d9d0c1] bg-white">
      <button
        className="flex w-full items-center gap-2 px-4 py-3 text-left font-medium text-[#4e6859]"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        创作宪章
        <span className="ml-auto text-xs text-gray-400">
          {loading ? "加载中..." : `红线 ${charter.red_lines.length} 条 / 要求 ${charter.mandates.length} 条`}
        </span>
      </button>
      {expanded && (
        <div className="space-y-4 border-t border-[#d9d0c1] px-4 py-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">叙事焦点</label>
            <textarea
              className="w-full rounded border border-gray-300 p-2 text-sm"
              rows={3}
              placeholder="例：强情节快节奏，爽点密集，古风仙侠"
              value={charter.narrative_focus}
              onChange={(e) => setCharter({ ...charter, narrative_focus: e.target.value })}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">目标读者</label>
            <input
              className="w-full rounded border border-gray-300 p-2 text-sm"
              placeholder="例：男频 25-35 岁，喜欢仙侠和升级文"
              value={charter.target_readers}
              onChange={(e) => setCharter({ ...charter, target_readers: e.target.value })}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">风格参考</label>
            <input
              className="w-full rounded border border-gray-300 p-2 text-sm"
              placeholder="例：凡人修仙传、仙逆"
              value={charter.tone_reference}
              onChange={(e) => setCharter({ ...charter, tone_reference: e.target.value })}
            />
          </div>
          <StringListEditor
            label="红线（绝对禁止）"
            items={charter.red_lines}
            placeholder="例：不写绿帽"
            onChange={(items) => setCharter({ ...charter, red_lines: items })}
          />
          <StringListEditor
            label="强制要求"
            items={charter.mandates}
            placeholder="例：每章至少一个爽点"
            onChange={(items) => setCharter({ ...charter, mandates: items })}
          />
          <div className="flex items-center gap-3">
            <button className="primary-button flex items-center gap-1" onClick={save} disabled={saving}>
              {saving ? <LoaderCircle size={14} className="animate-spin" /> : <Save size={14} />}
              保存宪章
            </button>
            {message && <span className="text-sm text-[#4e6859]">{message}</span>}
          </div>
        </div>
      )}
    </div>
  );
}

function StringListEditor({
  label,
  items,
  placeholder,
  onChange,
}: {
  label: string;
  items: string[];
  placeholder: string;
  onChange: (items: string[]) => void;
}) {
  const add = () => onChange([...items, ""]);
  const remove = (i: number) => onChange(items.filter((_, idx) => idx !== i));
  const set = (i: number, v: string) => {
    const next = [...items];
    next[i] = v;
    onChange(next);
  };
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-gray-700">{label}</label>
      <div className="space-y-2">
        {items.map((item, i) => (
          <div key={i} className="flex items-center gap-2">
            <input
              className="flex-1 rounded border border-gray-300 p-2 text-sm"
              placeholder={placeholder}
              value={item}
              onChange={(e) => set(i, e.target.value)}
            />
            <button className="text-red-400 hover:text-red-600" onClick={() => remove(i)}>
              <X size={16} />
            </button>
          </div>
        ))}
        <button className="flex items-center gap-1 text-sm text-[#4e6859] hover:text-[#3a5246]" onClick={add}>
          <Plus size={14} /> 添加
        </button>
      </div>
    </div>
  );
}
