"use client";

import { BookOpenText, ChevronDown, ChevronRight, LoaderCircle, Save } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import { useAppStore } from "@/lib/store";

type MethodCard = {
  id: string; slug: string; title: string; principle: string;
  when_to_use: string; procedure: string[]; checks: string[]; anti_patterns: string[];
};

type SceneTemplate = {
  id: string; slug: string; title: string; scene_type: string;
  tension_arc: string; beats: string[]; pov_suggestion: string;
  entry_condition: string; exit_condition: string; emotional_shift: string;
  anti_patterns: string[];
};

type PlotDevice = {
  id: string; slug: string; title: string; device_type: string;
  description: string; setup: string[]; escalation: string[]; payoff: string[];
  common_mistakes: string[];
};

type GenrePack = {
  genre: string;
  method_cards: MethodCard[];
  scene_templates: SceneTemplate[];
  plot_devices: PlotDevice[];
};

export default function KnowledgePage() {
  const { token } = useAppStore();
  const [packs, setPacks] = useState<GenrePack[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedGenre, setExpandedGenre] = useState<string | null>(null);
  const [expandedSection, setExpandedSection] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!token) return;
    apiFetch<{ packs: GenrePack[] }>("/knowledge/genre-packs", {}, token)
      .then((data) => setPacks(data?.packs || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [token]);

  const toggleSection = (genre: string, section: string) => {
    const key = `${genre}:${section}`;
    setExpandedSection((prev) => ({ ...prev, [key]: prev[key] === "open" ? "" : "open" }));
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-8 flex items-center gap-3">
        <Link href="/bookshelf" className="text-sm text-gray-500 hover:text-gray-700">← 返回书架</Link>
        <h1 className="text-2xl font-bold text-[#4e6859]">知识库管理</h1>
      </div>

      {loading ? (
        <div className="flex justify-center py-12"><LoaderCircle className="animate-spin text-[#4e6859]" size={32} /></div>
      ) : (
        <div className="space-y-6">
          {packs.map((pack) => (
            <div key={pack.genre} className="rounded-lg border border-[#d9d0c1] bg-white">
              <button
                className="flex w-full items-center gap-2 px-5 py-4 text-left text-lg font-semibold text-[#4e6859]"
                onClick={() => setExpandedGenre(expandedGenre === pack.genre ? null : pack.genre)}
              >
                {expandedGenre === pack.genre ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                {pack.genre}
                <span className="ml-auto text-sm font-normal text-gray-400">
                  {pack.method_cards.length} 卡 · {pack.scene_templates.length} 场景 · {pack.plot_devices.length} 桥段
                </span>
              </button>

              {expandedGenre === pack.genre && (
                <div className="border-t border-[#d9d0c1] px-5 py-4">
                  {/* Method cards */}
                  <SectionBlock
                    title="写作方法卡"
                    count={pack.method_cards.length}
                    expanded={expandedSection[`${pack.genre}:cards`] === "open"}
                    onToggle={() => toggleSection(pack.genre, "cards")}
                  >
                    {pack.method_cards.map((card) => (
                      <EditableCard
                        key={card.slug}
                        title={card.title}
                        fields={[
                          { label: "原理", value: card.principle },
                          { label: "适用场景", value: card.when_to_use },
                          { label: "步骤", value: card.procedure.join(" → ") },
                          { label: "检查清单", value: card.checks.join("\n") },
                          { label: "避免", value: card.anti_patterns.join("\n") },
                        ]}
                      />
                    ))}
                  </SectionBlock>

                  {/* Scene templates */}
                  <SectionBlock
                    title="场景模板"
                    count={pack.scene_templates.length}
                    expanded={expandedSection[`${pack.genre}:scenes`] === "open"}
                    onToggle={() => toggleSection(pack.genre, "scenes")}
                  >
                    {pack.scene_templates.map((scene) => (
                      <EditableCard
                        key={scene.slug}
                        title={`${scene.title}（${scene.scene_type}）`}
                        fields={[
                          { label: "张力弧", value: scene.tension_arc },
                          { label: "节拍", value: scene.beats.join(" → ") },
                          { label: "视角建议", value: scene.pov_suggestion },
                          { label: "入口条件", value: scene.entry_condition },
                          { label: "出口条件", value: scene.exit_condition },
                          { label: "情绪变化", value: scene.emotional_shift },
                          { label: "避免", value: scene.anti_patterns.join("\n") },
                        ]}
                      />
                    ))}
                  </SectionBlock>

                  {/* Plot devices */}
                  <SectionBlock
                    title="桥段"
                    count={pack.plot_devices.length}
                    expanded={expandedSection[`${pack.genre}:devices`] === "open"}
                    onToggle={() => toggleSection(pack.genre, "devices")}
                  >
                    {pack.plot_devices.map((device) => (
                      <EditableCard
                        key={device.slug}
                        title={`${device.title}（${device.device_type}）`}
                        fields={[
                          { label: "描述", value: device.description },
                          { label: "铺垫", value: device.setup.join("\n") },
                          { label: "升级", value: device.escalation.join("\n") },
                          { label: "收束", value: device.payoff.join("\n") },
                          { label: "常见错误", value: device.common_mistakes.join("\n") },
                        ]}
                      />
                    ))}
                  </SectionBlock>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SectionBlock({
  title, count, expanded, onToggle, children,
}: {
  title: string; count: number; expanded: boolean; onToggle: () => void; children: React.ReactNode;
}) {
  return (
    <div className="mb-4">
      <button
        className="flex items-center gap-1 py-2 text-sm font-medium text-gray-600 hover:text-gray-800"
        onClick={onToggle}
      >
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        {title}（{count}）
      </button>
      {expanded && <div className="ml-4 space-y-3">{children}</div>}
    </div>
  );
}

function EditableCard({ title, fields }: { title: string; fields: { label: string; value: string }[] }) {
  return (
    <details className="rounded border border-gray-200">
      <summary className="cursor-pointer px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">
        {title}
      </summary>
      <div className="space-y-2 border-t border-gray-100 px-3 py-3">
        {fields.filter((f) => f.value).map((f) => (
          <div key={f.label}>
            <div className="text-xs font-medium text-gray-500">{f.label}</div>
            <div className="whitespace-pre-wrap text-sm text-gray-800">{f.value}</div>
          </div>
        ))}
      </div>
    </details>
  );
}
