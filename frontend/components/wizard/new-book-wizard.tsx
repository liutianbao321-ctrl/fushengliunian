"use client";

import {
  ArrowLeft,
  ArrowRight,
  BookOpenText,
  Check,
  Compass,
  ExternalLink,
  Globe2,
  Lightbulb,
  LoaderCircle,
  Lock,
  Plus,
  RefreshCw,
  Sparkles,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { apiFetch } from "@/lib/api";
import { useAppStore } from "@/lib/store";

type StoryCore = {
  title_candidates: string[];
  premise: string;
  reader_promise: string;
  central_question: string;
  emotional_core: string;
  ending_direction: string;
};
type StoryEngine = {
  engine_type: string;
  primary_genre: string;
  long_term_loop: string;
  progression_dimensions: string[];
  escalation_rule: string;
};
type StoryWorld = {
  genre_flavor?: string;
  power_system?: string;
  factions?: string;
  geography?: string;
  daily_life?: string;
  history_pressure?: string;
  core_rule: string;
  social_order: string;
  scarce_resource: string;
  cost: string;
  opening_locality: string;
  visible_rules: string[];
  reserve: string[];
};
type Protagonist = {
  name: string;
  gender: string;
  starting_state: string;
  desire: string;
  fear: string;
  belief: string;
  method: string;
  bottom_line: string;
  contradiction: string;
};
type StoryCharacter = {
  name: string;
  role: string;
  desire: string;
  method: string;
  leverage: string;
  relationship: string;
  offstage_action: string;
};
type CreativeBriefItem = {
  title: string;
  content: string;
};
type StoryStage = {
  name: string;
  chapter_range: number[];
  starting_state: string;
  goal: string;
  pressure: string;
  irreversible_choice: string;
  changed_state: string;
  promise_payoff: string;
};
type ScalePlan = {
  target_words: number;
  estimated_chapters: number;
  planned_volumes: number;
  average_chapters_per_volume: number;
  opening_window_chapters: number;
  progression_ladders: string[];
  pacing_boundaries: string[];
};
type FirstVolume = {
  sequence: number;
  title: string;
  chapter_range: number[];
  reader_promise: string;
  starting_state: string;
  volume_goal: string;
  central_pressure: string;
  midpoint_change: string;
  climax_choice: string;
  ending_state: string;
  progression_gain: string;
  relationship_change: string;
  protected_reveals: string[];
};
type ChapterDirection = {
  sequence: number;
  title: string;
  function: "orient" | "deepen" | "attempt" | "complicate" | "partial_payoff";
  focus_character: string;
  location: string;
  reader_orientation: string;
  immediate_goal: string;
  obstacle: string;
  main_action: string;
  information_gain: string;
  relationship_movement: string;
  immediate_consequence: string;
  ending_beat: string;
};
type OpeningWindow = {
  title: string;
  chapter_range: number[];
  purpose: string;
  reader_anchor: string;
  local_goal: string;
  scope_boundary: string;
  ending_change: string;
  introduced_characters: string[];
  introduced_rules: string[];
  chapter_directions: ChapterDirection[];
};
type Foundation = {
  core: StoryCore;
  engine: StoryEngine;
  scale_plan: ScalePlan;
  world: StoryWorld;
  protagonist: Protagonist;
  creative_brief?: CreativeBriefItem[];
  characters: StoryCharacter[];
  stages: StoryStage[];
  first_volume: FirstVolume;
  opening_window: OpeningWindow;
};
type FoundationTask = { task_id: string; status: string };
type PilotTaskStatus = {
  status: "queued" | "running" | "completed" | "failed";
  phase?: string;
  pilot?: Pilot;
  error?: string;
};
type FoundationTaskStatus = {
  status: "queued" | "running" | "completed" | "failed";
  foundation?: Foundation;
  method_cards?: string[];
  scope?: string;
  error?: string;
};
type StoryDirection = {
  key: string;
  title: string;
  logline: string;
  reader_payoff: string;
  differentiation: string;
  protagonist_engine: string;
  serial_engine: string;
  emotional_throughline: string;
  cost_and_risk: string;
};
type CreativeSynthesis = {
  kind: "pillar_synthesis";
  pillars: StoryDirection[];
  primary_keys: string[];
  synthesis_note: string;
};
type ViabilityReview = {
  verdict: "pass" | "revise";
  evidence: {
    reader_payoff: string;
    differentiation: string;
    protagonist_engine: string;
    story_engine_variations: string[];
    relationship_engine: string;
    antagonist_agency: string;
    escalation_capacity: string;
    simulated_arcs: Record<string, string>[];
    promise_ledger: Record<string, string>[];
    opening_strategy: Record<string, string>;
    endgame_direction: string;
  };
  blocking_issues: string[];
  warnings: string[];
};
type StoryResearch = {
  status: "completed" | "unavailable";
  query: string;
  memo: string;
  sources: { title: string; url: string; snippet: string }[];
  warning?: string | null;
};
type CreationStudio = {
  session_id: string;
  state: string;
  directions: StoryDirection[];
  selected_direction: StoryDirection | CreativeSynthesis | null;
  foundation: Foundation | null;
  foundation_version: number;
  viability: ViabilityReview | null;
  research: StoryResearch | null;
  author_confirmed: boolean;
  error?: string | null;
};
type SceneContract = {
  viewpoint: string;
  starting_state: string;
  immediate_goal: string;
  resistance: string;
  action: string;
  decision: string;
  immediate_consequence: string;
  changed_state: string;
  next_promise: string;
  scenes: Record<string, string>[];
};
type Pilot = {
  title: string;
  content: string;
  summary: string;
  scene_contract: SceneContract;
  method_cards: string[];
};
type Draft = {
  step: number;
  idea: string;
  storyTypes: string[];
  channel: string;
  targetWords: number;
  readerWish: string;
  avoidElements: string;
  styleReference: string;
  foundation: Foundation | null;
  selectedTitle: string;
  pilot: Pilot | null;
  foundationVersion: string;
  pilotFoundationVersion: string;
  goldenFinger: string;
  sourceMode: SourceMode;
  sourceFanficType: string;
  sourceStrategy: string;
  creationSessionId: string;
  directions: StoryDirection[];
  selectedDirection: StoryDirection | CreativeSynthesis | null;
  selectedPillarIndices: number[];
  primaryPillarIndex: number;
  viability: ViabilityReview | null;
  research: StoryResearch | null;
  reviewedFoundationSnapshot: string;
};
type SourceMode = "none" | "imitation" | "continuation" | "fanfic";

const STEPS = ["说出想写的故事", "融合创作支柱", "验证长篇生命力", "读完第一章再建立"];
const GENRE_GROUPS = {
  男频: ["玄幻", "奇幻", "武侠", "仙侠", "都市", "现实", "军事", "历史", "游戏", "体育", "科幻", "末世", "诸天无限", "悬疑灵异", "轻小说"],
  女频: ["古代言情", "宫斗宅斗", "种田经商", "仙侠奇缘", "现代言情", "豪门总裁", "青春校园", "浪漫青春", "玄幻言情", "悬疑推理", "科幻空间", "游戏竞技", "女生剧场", "短篇", "轻小说", "现实生活"],
};
const TARGETS = [
  { label: "50万字", value: 500_000 },
  { label: "百万字长篇", value: 1_000_000 },
  { label: "200万字", value: 2_000_000 },
  { label: "300万字", value: 3_000_000 },
  { label: "500万字", value: 5_000_000 },
  { label: "800万字", value: 8_000_000 },
];
const DRAFT_KEY = "fushengliunian:creation-v4-draft";
const LEGACY_DRAFT_KEY = "fushengliunian:creation-v2-draft";
const FUNCTION_LABELS: Record<ChapterDirection["function"], string> = {
  orient: "让读者认清",
  deepen: "加深人物或处境",
  attempt: "尝试眼前目标",
  complicate: "让事情更复杂",
  partial_payoff: "局部兑现",
};

function stableFoundation(value: Foundation | null): string {
  return value ? JSON.stringify(value) : "";
}

function updateAt<T>(items: T[], index: number, change: Partial<T>): T[] {
  return items.map((item, itemIndex) => itemIndex === index ? { ...item, ...change } : item);
}

export function NewBookWizard() {
  const router = useRouter();
  const { token, hydrate } = useAppStore();
  const [step, setStep] = useState(0);
  const [idea, setIdea] = useState("");
  const [storyTypes, setStoryTypes] = useState<string[]>([]);
  const [channel, setChannel] = useState("不限");
  const [targetWords, setTargetWords] = useState(1_000_000);
  const [readerWish, setReaderWish] = useState("");
  const [avoidElements, setAvoidElements] = useState("");
  const [styleReference, setStyleReference] = useState("");
  const [sourceWorkId, setSourceWorkId] = useState<string | null>(null);
  const [sourceWorkTitle, setSourceWorkTitle] = useState("");
  const [sourceMode, setSourceMode] = useState<SourceMode>("none");
  const [sourceFanficType, setSourceFanficType] = useState("");
  const [sourceStrategy, setSourceStrategy] = useState("");
  const [foundation, setFoundation] = useState<Foundation | null>(null);
  const [selectedTitle, setSelectedTitle] = useState("");
  const [pilot, setPilot] = useState<Pilot | null>(null);
  const [pilotFoundationVersion, setPilotFoundationVersion] = useState("");
  const [goldenFinger, setGoldenFinger] = useState("");
  const [briefOpen, setBriefOpen] = useState(false);
  const [authorNote, setAuthorNote] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingText, setLoadingText] = useState("");
  const [loadingSeconds, setLoadingSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  // 分节生成状态
  const [sectionLoading, setSectionLoading] = useState<string | null>(null);
  const [sectionError, setSectionError] = useState<Record<string, string>>({});
  const [sectionMessage, setSectionMessage] = useState<Record<string, string>>({});
  const [creationSessionId, setCreationSessionId] = useState("");
  const [directions, setDirections] = useState<StoryDirection[]>([]);
  const [selectedDirection, setSelectedDirection] = useState<StoryDirection | CreativeSynthesis | null>(null);
  const [selectedPillarIndices, setSelectedPillarIndices] = useState<number[]>([]);
  const [primaryPillarIndex, setPrimaryPillarIndex] = useState(0);
  const [viability, setViability] = useState<ViabilityReview | null>(null);
  const [research, setResearch] = useState<StoryResearch | null>(null);
  const [reviewedFoundationSnapshot, setReviewedFoundationSnapshot] = useState("");

  const foundationVersion = useMemo(() => stableFoundation(foundation), [foundation]);
  const pilotIsCurrent = Boolean(pilot && pilotFoundationVersion === foundationVersion);
  const availableGenres = useMemo(() => channel === "男频"
    ? GENRE_GROUPS.男频
    : channel === "女频"
      ? GENRE_GROUPS.女频
      : [...GENRE_GROUPS.男频, ...GENRE_GROUPS.女频.filter((item) => !GENRE_GROUPS.男频.includes(item))], [channel]);

  useEffect(() => {
    hydrate();
    try {
      const raw = window.localStorage.getItem(DRAFT_KEY) ?? window.localStorage.getItem(LEGACY_DRAFT_KEY);
      if (raw) {
        const draft = JSON.parse(raw) as Partial<Draft> & { genre?: string };
        const compatibleFoundation = draft.foundation?.scale_plan ? draft.foundation : null;
        setStep(draft.creationSessionId ? Math.min(draft.step ?? 0, 3) : 0);
        setIdea(draft.idea ?? "");
        setStoryTypes(draft.storyTypes ?? (draft.genre ? [draft.genre] : []));
        setChannel(draft.channel ?? "不限");
        setTargetWords(draft.targetWords ?? 1_000_000);
        setReaderWish(draft.readerWish ?? "");
        setAvoidElements(draft.avoidElements ?? "");
        setStyleReference(draft.styleReference ?? "");
        setSourceMode(draft.sourceMode ?? "none");
        setSourceFanficType(draft.sourceFanficType ?? "");
        setSourceStrategy(draft.sourceStrategy ?? "");
        setFoundation(compatibleFoundation);
        setSelectedTitle(draft.selectedTitle ?? compatibleFoundation?.core.title_candidates?.[0] ?? "");
        setPilot(compatibleFoundation ? draft.pilot ?? null : null);
        setPilotFoundationVersion(compatibleFoundation ? draft.pilotFoundationVersion ?? "" : "");
        setGoldenFinger(draft.goldenFinger ?? "");
        setCreationSessionId(draft.creationSessionId ?? "");
        setDirections(draft.directions ?? []);
        setSelectedDirection(draft.selectedDirection ?? null);
        setSelectedPillarIndices(draft.selectedPillarIndices ?? []);
        setPrimaryPillarIndex(draft.primaryPillarIndex ?? 0);
        setViability(draft.viability ?? null);
        setResearch(draft.research ?? null);
        setReviewedFoundationSnapshot(draft.reviewedFoundationSnapshot ?? "");
      }
    } catch {
      window.localStorage.removeItem(DRAFT_KEY);
    } finally {
      setReady(true);
    }
  }, [hydrate]);

  useEffect(() => {
    if (!ready) return;
    const params = new URLSearchParams(window.location.search);
    const importedWorkId = params.get("sourceWork");
    if (!importedWorkId) return;
    const mode = (params.get("mode") || "imitation") as SourceMode;
    const safeMode: SourceMode = ["imitation", "continuation", "fanfic"].includes(mode) ? mode : "imitation";
    const fanficType = params.get("fanficType") || "";
    const strategyValue = params.get("strategy") || "";
    const target = Number(params.get("targetWords"));
    const seed = params.get("seed") || "";
    setSourceMode(safeMode);
    setSourceFanficType(fanficType);
    setSourceStrategy(strategyValue);
    if (Number.isFinite(target) && target >= 100_000 && target <= 8_000_000) {
      setTargetWords(target);
    }
    const currentToken = token ?? window.localStorage.getItem("fushengliunian.token");
    if (!currentToken) return;
    apiFetch<{
      work: { title: string; genre: string | null; style_profile: Record<string, unknown> | null };
      style_summary: string | null;
    }>(`/imported-works/${importedWorkId}/report`, {}, currentToken)
      .then((report) => {
        setSourceWorkId(importedWorkId);
        setSourceWorkTitle(report.work.title);
        const modeLine = safeMode === "continuation"
          ? `续写《${report.work.title}》：从原作断点之后开一本新书，继承人物、世界、未收伏笔和终点状态，但后续章纲以工作台确认为准。`
          : safeMode === "fanfic"
            ? `基于《${report.work.title}》写同人：继承可用人物、世界规则与文风约束，重新建立本书主线；只有“同人续写”继承原作断点叙事。`
            : `参考《${report.work.title}》的叙事技法，但不复用其人物、世界观和情节。`;
        setStyleReference([
          modeLine,
          report.style_summary ?? "",
          report.work.style_profile ? JSON.stringify(report.work.style_profile, null, 2) : "",
        ].filter(Boolean).join("\n"));
        if (!storyTypes.length && report.work.genre) setStoryTypes([report.work.genre]);
        if (!idea.trim()) {
          const seedText = seed || (safeMode === "continuation"
            ? `我想续写《${report.work.title}》，从原作断点继续推进未完成承诺，同时允许后续章纲滚动修正。`
            : safeMode === "fanfic"
              ? `我想基于《${report.work.title}》写一部同人新书，类型是${fanficType || "同人"}，但主线要由这本新书自己成立。`
              : `我想借鉴《${report.work.title}》的叙事技法，重新写一本自己的新书。`);
          setIdea(seedText);
        }
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "来源作品加载失败"));
  }, [ready, token]);

  useEffect(() => {
    if (!ready || !creationSessionId) return;
    const currentToken = token ?? window.localStorage.getItem("fushengliunian.token");
    if (!currentToken) return;
    apiFetch<CreationStudio>(`/ai/creation-studio/sessions/${creationSessionId}`, {}, currentToken)
      .then((session) => {
        applyStudio(session);
        if (session.state === "DIRECTIONS_PROPOSED") setStep((current) => Math.max(current, 1));
        if (["STORY_ENGINE_PROVEN", "REVIEW_REQUIRED", "REVIEW_RETRY_REQUIRED", "OPENING_STRATEGY_CONFIRMED"].includes(session.state)) {
          setStep((current) => Math.max(current, 2));
        }
        if (session.state === "PILOT_GENERATED" && pilot) setStep(3);
      })
      .catch(() => undefined);
  }, [ready, token, creationSessionId]);

  useEffect(() => {
    if (!ready) return;
    const draft: Draft = {
      step, idea, storyTypes, channel, targetWords, readerWish, avoidElements, styleReference,
      foundation, selectedTitle, pilot, foundationVersion, pilotFoundationVersion, goldenFinger,
      sourceMode, sourceFanficType, sourceStrategy, creationSessionId, directions,
      selectedDirection, selectedPillarIndices, primaryPillarIndex, viability, reviewedFoundationSnapshot,
      research,
    };
    window.localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
  }, [ready, step, idea, storyTypes, channel, targetWords, readerWish, avoidElements, styleReference, foundation, selectedTitle, pilot, foundationVersion, pilotFoundationVersion, goldenFinger, sourceMode, sourceFanficType, sourceStrategy, creationSessionId, directions, selectedDirection, selectedPillarIndices, primaryPillarIndex, viability, research, reviewedFoundationSnapshot]);

  function toggleStoryType(value: string) {
    setStoryTypes((current) => current.includes(value)
      ? current.filter((item) => item !== value)
      : current.length < 2 ? [...current, value] : [current[0], value]);
  }

  function authToken(): string | null {
    const value = token ?? window.localStorage.getItem("fushengliunian.token");
    if (!value) setError("登录状态已失效，请重新登录后继续");
    return value;
  }

  async function run<T>(label: string, operation: (currentToken: string) => Promise<T>): Promise<T | null> {
    const currentToken = authToken();
    if (!currentToken) return null;
    setLoading(true);
    setLoadingText(label);
    setLoadingSeconds(0);
    setError(null);
    const startedAt = Date.now();
    const timer = window.setInterval(() => setLoadingSeconds(Math.floor((Date.now() - startedAt) / 1000)), 1000);
    try {
      return await operation(currentToken);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "生成失败，请稍后重试");
      return null;
    } finally {
      window.clearInterval(timer);
      setLoading(false);
    }
  }

  async function pollCreationStudio(
    sessionId: string,
    currentToken: string,
    terminalStates: string[],
  ): Promise<CreationStudio> {
    for (let attempt = 0; attempt < 600; attempt += 1) {
      const session = await apiFetch<CreationStudio>(`/ai/creation-studio/sessions/${sessionId}`, {}, currentToken);
      if (session.state.startsWith("FAILED_")) throw new Error(session.error || "建书任务失败，请重试");
      if (terminalStates.includes(session.state)) return session;
      if (session.state === "DIRECTION_SELECTED") setLoadingText("正在把多个创作支柱融合成因果统一的故事根基…");
      if (session.state === "STORY_RESEARCHING") setLoadingText("正在联网查找题材事实、职业细节和现实依据…");
      if (session.state === "SERIALIZATION_SIMULATING") setLoadingText("正在模拟开篇、中期和后期的连载压力…");
      await new Promise((resolve) => window.setTimeout(resolve, 2000));
    }
    throw new Error("建书任务等待超时，请稍后恢复这个会话");
  }

  function applyStudio(session: CreationStudio) {
    setCreationSessionId(session.session_id);
    setDirections(session.directions ?? []);
    setSelectedDirection(session.selected_direction);
    setViability(session.viability);
    setResearch(session.research);
    if (session.state === "REVIEW_RETRY_REQUIRED" && session.error) setError(session.error);
    if (session.foundation) {
      setFoundation(session.foundation);
      setSelectedTitle((current) => current || session.foundation?.core.title_candidates[0] || "未命名作品");
      setReviewedFoundationSnapshot(stableFoundation(session.foundation));
    }
  }

  async function generateFoundation() {
    if (idea.trim().length < 20) {
      setError("请多说一点：你想写谁、他正面对什么，或者你最想留下什么感受。");
      return;
    }
    const result = await run<CreationStudio>("故事总监正在拆解这本书需要共同成立的创作支柱…", async (currentToken) => {
      const session = await apiFetch<CreationStudio>("/ai/creation-studio/sessions", {
        method: "POST",
        body: JSON.stringify({
          idea: idea.trim(), genre: storyTypes[0] || null, genres: storyTypes, channel, target_words: targetWords,
          reader_wish: readerWish.trim() || null,
          avoid_elements: avoidElements.trim() || null,
          style_reference: styleReference.trim() || null,
        }),
      }, currentToken);
      setCreationSessionId(session.session_id);
      return pollCreationStudio(session.session_id, currentToken, ["DIRECTIONS_PROPOSED"]);
    });
    if (!result) return;
    applyStudio(result);
    setSelectedPillarIndices(result.directions.map((_, index) => index));
    setPrimaryPillarIndex(0);
    setFoundation(null);
    setResearch(null);
    setSelectedTitle("");
    setPilot(null);
    setPilotFoundationVersion("");
    setSectionError({});
    setStep(1);
  }

  function togglePillar(index: number) {
    setSelectedPillarIndices((current) => {
      if (current.includes(index)) {
        if (current.length <= 2) return current;
        const next = current.filter((item) => item !== index);
        if (primaryPillarIndex === index) setPrimaryPillarIndex(next[0]);
        return next;
      }
      return [...current, index].sort((a, b) => a - b);
    });
  }

  async function synthesizePillars() {
    if (!creationSessionId) return;
    if (selectedPillarIndices.length < 2) {
      setError("至少保留两个创作支柱，才能让故事同时具备情节、人物或情感的纵深。");
      return;
    }
    const result = await run<CreationStudio>("长篇架构师正在融合创作支柱并建立故事根基…", async (currentToken) => {
      await apiFetch<CreationStudio>(`/ai/creation-studio/sessions/${creationSessionId}/direction`, {
        method: "POST",
        body: JSON.stringify({
          selected_indices: selectedPillarIndices,
          primary_index: primaryPillarIndex,
          user_note: authorNote.trim() || null,
        }),
      }, currentToken);
      return pollCreationStudio(creationSessionId, currentToken, ["STORY_ENGINE_PROVEN", "REVIEW_REQUIRED", "REVIEW_RETRY_REQUIRED"]);
    });
    if (!result) return;
    applyStudio(result);
    setPilot(null);
    setPilotFoundationVersion("");
    setStep(2);
  }

  async function reviewFoundation() {
    if (!creationSessionId || !foundation) return;
    const result = await run<CreationStudio>("正在用当前版本重新模拟长篇连载…", async (currentToken) => {
      await apiFetch<CreationStudio>(`/ai/creation-studio/sessions/${creationSessionId}/review`, {
        method: "POST",
        body: JSON.stringify({ foundation, author_note: authorNote.trim() || null }),
      }, currentToken);
      return pollCreationStudio(creationSessionId, currentToken, ["STORY_ENGINE_PROVEN", "REVIEW_REQUIRED", "REVIEW_RETRY_REQUIRED"]);
    });
    if (result) applyStudio(result);
  }

  async function generateSection(section: string) {
    if (!foundation) return;
    const labels: Record<string, string> = {
      creative_brief: "正在按这本书的题材重新设计创作蓝图…",
      engine: "正在重新设计故事引擎…",
      world: "正在重新构建世界观…",
      scale_volume: "正在重新规划规模与第一卷…",
      characters: "正在设计配角阵容…",
      stages: "正在规划全书阶段方向…",
      opening_window: "正在预想可随时推翻的开篇方向…",
    };
    setSectionLoading(section);
    setSectionError((prev) => ({ ...prev, [section]: "" }));
    setSectionMessage((prev) => ({ ...prev, [section]: "" }));
    try {
      const snapshot = foundation;
      const result = await run<{ section: string; patch: Partial<Foundation> }>(labels[section] ?? "正在生成…", async (currentToken) => {
        return apiFetch("/ai/creation-v2/foundation/section", {
          method: "POST",
          body: JSON.stringify({
            idea: idea.trim(),
            section,
            current: snapshot,
            genre: storyTypes[0] || null,
            genres: storyTypes,
            channel,
            target_words: targetWords,
            reader_wish: readerWish.trim() || null,
            avoid_elements: avoidElements.trim() || null,
            style_reference: styleReference.trim() || null,
            golden_finger_hint: null,
          }),
        }, currentToken);
      });
      if (!result) {
        setSectionError((prev) => ({ ...prev, [section]: "生成失败，请看页面底部错误信息后重试。" }));
        return;
      }
      if (!result.patch || Object.keys(result.patch).length === 0) {
        setSectionError((prev) => ({ ...prev, [section]: "AI 返回了空内容，未能应用到当前蓝图。请重试这一节。" }));
        return;
      }
      setFoundation((prev) => {
        if (!prev) return prev;
        return { ...prev, ...result.patch } as Foundation;
      });
      setPilot(null);
      setPilotFoundationVersion("");
      setSectionMessage((prev) => ({ ...prev, [section]: "已更新到当前蓝图；后续生成会使用这版内容。" }));
    } finally {
      setSectionLoading((current) => (current === section ? null : current));
    }
  }

  async function generatePilot() {
    if (!foundation || !creationSessionId) return;
    if (reviewedFoundationSnapshot !== foundationVersion || viability?.verdict !== "pass" || viability.blocking_issues.length) {
      await reviewFoundation();
      return;
    }
    const brief = foundation.creative_brief ?? [];
    if (brief.length === 0 || brief.some((item) => !item.title.trim() || !item.content.trim())) {
      setError("请先确认动态蓝图：至少保留一项，并补全每项的栏目名称和具体内容。");
      setStep(2);
      return;
    }
    const version = stableFoundation(foundation);
    const result = await run<Pilot>("正在规划连续场景并写第一章…", async (currentToken) => {
      await apiFetch(`/ai/creation-studio/sessions/${creationSessionId}/confirm`, {
        method: "POST",
        body: JSON.stringify({ foundation, author_note: authorNote.trim() || null }),
      }, currentToken);
      const task = await apiFetch<FoundationTask>("/ai/creation-v2/pilot/start", {
        method: "POST",
        body: JSON.stringify({
          foundation,
          author_note: authorNote.trim() || null,
          style_reference: styleReference.trim() || null,
          creation_session_id: creationSessionId,
        }),
      }, currentToken);
      for (let attempt = 0; attempt < 180; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 2000));
        const status = await apiFetch<PilotTaskStatus>(`/ai/creation-v2/pilot/task/${task.task_id}`, {}, currentToken);
        if (status.phase) setLoadingText(status.phase);
        if (status.status === "completed" && status.pilot) return status.pilot;
        if (status.status === "failed") throw new Error(status.error || "第一章生成失败，请重试");
      }
      throw new Error("第一章生成超过6分钟，已停止等待，请重试");
    });
    if (!result) return;
    setPilot(result);
    setPilotFoundationVersion(version);
    setStep(3);
  }

  function planningProfile(current: Foundation) {
    const protagonist = current.protagonist;
    const supporting = current.characters.map((item) => ({
      ...item,
      gender: "未限定",
      personality: item.leverage,
      flaw: item.leverage,
      bottom_line: "由后续行动确认",
      pressure_action: item.offstage_action,
    }));
    return {
      creation_v2: current,
      creation_direction: selectedDirection,
      viability_review: viability,
      web_research: research,
      story_question: current.core.central_question,
      creative_brief: current.creative_brief ?? [],
      world_engine: {
        primary_genre: current.engine.primary_genre,
        engine_name: current.engine.engine_type,
        reader_promise: current.core.reader_promise,
        genre_flavor: current.world.genre_flavor,
        core_rule: current.world.core_rule,
        power_system: current.world.power_system,
        power_source: current.world.scarce_resource,
        scarcity: current.world.scarce_resource,
        factions: current.world.factions,
        geography: current.world.geography,
        history_pressure: current.world.history_pressure,
        social_order: current.world.social_order,
        progression_axes: current.engine.progression_dimensions,
        conflict_generators: [current.engine.long_term_loop, current.engine.escalation_rule],
        limitations: current.world.visible_rules,
        core_cost: current.world.cost,
        daily_life_effects: [current.world.daily_life, ...current.world.visible_rules].filter(Boolean),
        escalation_model: current.engine.escalation_rule,
        opening_pressure: current.opening_window.reader_anchor,
        pressure_tests: current.stages.slice(0, 3).map((stage) => ({
          desire: stage.goal,
          rule_pressure: stage.pressure,
          costly_choice: stage.irreversible_choice,
        })),
      },
      characters: [{
        name: protagonist.name,
        gender: protagonist.gender,
        role: "主角",
        personality: `${protagonist.belief}；${protagonist.contradiction}`,
        desire: protagonist.desire,
        flaw: protagonist.fear,
        relationship: "故事视角核心",
        method: protagonist.method,
        bottom_line: protagonist.bottom_line,
        pressure_action: protagonist.method,
      }, ...supporting],
      book_blueprint: {
        creative_brief: current.creative_brief ?? [],
        scale_plan: current.scale_plan,
        reader_promise: current.core.reader_promise,
        story_question: current.core.central_question,
        story_engine: current.engine.long_term_loop,
        story_engine_variations: viability?.evidence.story_engine_variations ?? [],
        promise_ledger: viability?.evidence.promise_ledger ?? [],
        opening_strategy: viability?.evidence.opening_strategy ?? {},
        endgame_direction: viability?.evidence.endgame_direction ?? current.core.ending_direction,
        major_arcs: current.stages.map((stage) => ({
          title: stage.name, chapter_range: stage.chapter_range, goal: stage.goal,
          turn: stage.irreversible_choice, result: stage.changed_state,
        })),
      },
      first_volume: {
        title: current.first_volume.title,
        goal: current.first_volume.volume_goal,
        opening: current.opening_window.reader_anchor,
        turning_points: [current.first_volume.midpoint_change, current.first_volume.ending_state],
        climax: current.first_volume.climax_choice,
        ending_hook: current.first_volume.ending_state,
        protected_reveals: current.first_volume.protected_reveals,
      },
      writing_style: { description_raw: styleReference, description_effective: styleReference },
      author_constitution: {
        why_write: idea,
        reader_promise: current.core.reader_promise,
        lasting_feeling: current.core.emotional_core,
        non_negotiables: avoidElements,
        ai_mandate: "在作者确认的故事根基内滚动规划和起草；改变核心承诺前必须询问作者",
        chapter_test: "读者是否清楚跟着谁、在哪里、人物眼前要什么；本章是否只完成当前层级的一步",
      },
    };
  }

  async function createProject() {
    if (!foundation || !pilot || !pilotIsCurrent) {
      setError("故事根基已经修改，请先按当前版本重新生成并确认第一章。");
      return;
    }
    const project = await run<{ id: string }>("正在建立作品，并保存你确认的第一章…", (currentToken) =>
      apiFetch("/projects", {
        method: "POST",
        body: JSON.stringify({
          title: selectedTitle.trim() || foundation.core.title_candidates[0],
          genre: foundation.engine.primary_genre,
          one_sentence: foundation.core.premise,
          protagonist_name: foundation.protagonist.name,
          protagonist_gender: foundation.protagonist.gender || "未限定",
          protagonist_personality: `${foundation.protagonist.belief}；${foundation.protagonist.contradiction}`,
          target_words: targetWords,
          channel: channel === "不限" ? null : channel,
          creation_mode: sourceWorkId ? (sourceMode === "continuation" ? "continuation" : sourceMode === "fanfic" ? "fanfic" : "imitation") : "inspired",
          source_work_id: sourceWorkId,
          planning_profile: planningProfile(foundation),
          opening_pilot: pilot,
          creation_session_id: creationSessionId,
          golden_finger: null,
          intent_brief: {
            idea,
            genre: foundation.engine.primary_genre,
            style: styleReference,
            world_rule: foundation.world.core_rule,
            protagonist_desire: foundation.protagonist.desire,
            golden_finger: null,
            source_derivative: sourceWorkId ? {
              mode: sourceMode,
              fanfic_type: sourceFanficType || null,
              strategy: sourceStrategy || null,
              source_work_id: sourceWorkId,
            } : null,
          },
        }),
      }, currentToken),
    );
    if (!project) return;
    window.localStorage.removeItem(DRAFT_KEY);
    router.push(`/workspace/${project.id}`);
  }

  // ─── Step 0: 只有一个按钮 ──────────────────────────────────
  const step0Ready = idea.trim().length >= 20;

  // ─── Step 1: 摘要快捷栏数据 ────────────────────────────────
  const f = foundation; // shorthand for step 1

  return (
    <div className="wizard-shell surface reveal reveal-delay-1">
      <nav className="wizard-progress" aria-label="创建进度">
        {STEPS.map((label, index) => (
          <button
            type="button"
            key={label}
            disabled={index > step || loading}
            className={index === step ? "is-current" : index < step ? "is-done" : ""}
            onClick={() => index < step && setStep(index)}
          >
            <span>{index < step ? <Check size={13} /> : index + 1}</span><small>{label}</small>
          </button>
        ))}
      </nav>

      <div className="wizard-content">
        {/* ═══════════════ STEP 0 ═══════════════ */}
        {step === 0 && (
          <section>
            <Heading kicker="作者先开口" title="先别填设定表，告诉我你真正想写什么" text="可以说一个画面、一个人、一段关系，也可以说你一直想读却没读到的故事。先写想法，其他都可以稍后再补。" />
            {sourceWorkId ? (
              <div className="mt-5 rounded-md border border-[#9eb0a4] bg-[#edf1ec] px-4 py-3 text-sm text-[#3f5749]">
                {sourceMode === "continuation"
                  ? `已载入《${sourceWorkTitle}》的断点、人物、世界与未完成伏笔。这里仍是新书创建流程，后续章纲以你在工作台确认的版本为准。`
                  : sourceMode === "fanfic"
                    ? `已载入《${sourceWorkTitle}》的人物、世界与文风。普通同人会新开主线，不把原作章节正文当作本书前文。`
                    : `已载入《${sourceWorkTitle}》的文风与叙事技法。新书不会继承原作人物、世界规则或情节事实。`}
              </div>
            ) : null}
            <label className="form-label mt-6 block">你的故事想法
              <textarea className="field mt-2 min-h-36 resize-y p-4 font-normal leading-7" value={idea} onChange={(event) => setIdea(event.target.value)} placeholder="例如：我想写一个……我最在意的是……我不确定世界和情节怎么搭，但希望读者最后感到……" />
            </label>

            {/* 实时反馈——根据输入动态变化 */}
            {idea.trim().length > 5 && (
              <div className={`mt-4 rounded-lg border p-3.5 ${step0Ready ? "border-[#4e6859] bg-[#edf1ec]" : "border-[#e0c98a] bg-[#fdf8ec]"}`}>
                <div className="flex items-center gap-2 text-xs font-bold">
                  <Lightbulb size={14} />
                  {idea.trim().length < 20 ? `再写一点就好（${idea.trim().length}/20 字）` : "已捕捉到你的核心意图 ✓"}
                </div>
                {idea.trim().length >= 20 && (
                  <p className="mt-1.5 text-xs leading-6 text-[#5a6b60]">
                    关键词：{[...new Set(idea.match(/[\u4e00-\u9fff]{2,}/g) || [])].slice(0, 6).join("、") || "通用"}
                    {storyTypes.length ? ` · 类型：${storyTypes.join("+")}` : ""}
                    {` · ${targetWords >= 1_000_000 ? "长篇" : "中短篇"}`}
                  </p>
                )}
              </div>
            )}

            {/* 选填设定——默认收起 */}
            <details className="mt-5 border-t border-[#ded8cc] pt-4">
              <summary className="cursor-pointer text-sm font-semibold text-[#656760]">补充类型、篇幅和文风偏好（选填）</summary>
              <div className="mt-4 grid gap-4 md:grid-cols-[minmax(0,1fr)_300px]">
                <div>
                  <div className="form-label">作品分类</div>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">{availableGenres.map((item) => { const idx = storyTypes.indexOf(item); return <button type="button" key={item} className={`tag-button ${idx >= 0 ? "is-active is-red" : ""}`} onClick={() => toggleStoryType(item)}>{idx >= 0 && <span>{idx + 1}</span>}{item}</button>; })}</div>
                  <p className="mt-1.5 text-[11px] text-[#999]">最多选 2 个，第一个为主类型</p>
                </div>
                <div>
                  <div className="form-label">频道</div>
                  <div className="segmented mt-1.5">{["不限", "男频", "女频"].map((item) => <button type="button" key={item} className={channel === item ? "is-active" : ""} onClick={() => setChannel(item)}>{item}</button>)}</div>
                </div>
              </div>
              <div className="mt-4"><div className="form-label">预计篇幅</div><div className="mt-1.5 flex flex-wrap gap-2">{TARGETS.map((item) => <button type="button" key={item.value} className={`tag-button ${targetWords === item.value ? "is-active is-green" : ""}`} onClick={() => setTargetWords(item.value)}>{item.label}</button>)}</div></div>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <TextField label="希望读者持续获得什么" value={readerWish} onChange={setReaderWish} rows={2} />
                <TextField label="明确不要出现什么" value={avoidElements} onChange={setAvoidElements} rows={2} />
                <div className="md:col-span-2"><TextField label="文风要求或参考作品的叙事特点（选填）" value={styleReference} onChange={setStyleReference} rows={3} /></div>
              </div>
            </details>

            <Footer loading={loading} loadingText={loadingText} loadingSeconds={loadingSeconds} error={error}
              nextLabel="和我一起定下这本书" onNext={generateFoundation} disabled={!step0Ready}
            />
          </section>
        )}

        {/* ═══════════════ STEP 1 ═══════════════ */}
        {step === 1 && directions.length > 0 && (
          <section>
            <Heading kicker="故事总监拆解" title="把这本书需要成立的力量组合起来" text="这些不是互相排斥的故事方向，而是同一本书的不同创作支柱。默认全部纳入；你可以删去不想写的部分，并指定一个主支柱来决定篇幅和节奏重心。" />
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-y border-[#ded8cc] py-3 text-sm">
              <span>已纳入 <strong>{selectedPillarIndices.length}</strong> 个支柱，至少保留 2 个</span>
              <span className="text-[#777]">圆点表示主支柱，勾选表示纳入全书</span>
            </div>
            <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {directions.map((direction, index) => (
                <article className={`flex min-h-[390px] flex-col rounded-md border p-5 ${selectedPillarIndices.includes(index) ? "border-[#809789] bg-[#f2f5f1]" : "border-[#d9d2c6] bg-[#f8f6f1] opacity-70"}`} key={direction.key}>
                  <div className="flex items-center justify-between gap-3">
                    <label className="flex cursor-pointer items-center gap-2 text-xs font-bold text-[#a63f2f]">
                      <input type="checkbox" checked={selectedPillarIndices.includes(index)} onChange={() => togglePillar(index)} />
                      创作支柱 {index + 1}
                    </label>
                    <label className="flex cursor-pointer items-center gap-1.5 text-xs text-[#656760]">
                      <input type="radio" name="primary-pillar" checked={primaryPillarIndex === index} disabled={!selectedPillarIndices.includes(index)} onChange={() => setPrimaryPillarIndex(index)} />
                      主支柱
                    </label>
                  </div>
                  <h3 className="mt-2 font-editorial text-xl font-bold leading-7">{direction.title}</h3>
                  <p className="mt-3 text-sm leading-6 text-[#4b4e48]">{direction.logline}</p>
                  <Info label="读者持续得到什么" value={direction.reader_payoff} />
                  <Info label="它在全书中承担什么" value={direction.differentiation} />
                  <Info label="怎样连续写很多卷" value={direction.serial_engine} />
                  <Info label="最危险的写崩点" value={direction.cost_and_risk} />
                </article>
              ))}
            </div>
            <div className="mt-5">
              <TextField label="告诉架构师这些支柱如何取舍（选填）" value={authorNote} onChange={setAuthorNote} rows={2} />
            </div>
            <Footer loading={loading} loadingText={loadingText} loadingSeconds={loadingSeconds} error={error} onBack={() => setStep(0)} nextLabel="融合支柱，建立故事根基" onNext={synthesizePillars} disabled={selectedPillarIndices.length < 2 || !selectedPillarIndices.includes(primaryPillarIndex)} />
          </section>
        )}

        {/* ═══════════════ STEP 2 ═══════════════ */}
        {step === 2 && f && (
          <section>
            <Heading kicker="长篇生命力验证" title="先证明它能持续写，再试写第一章" text="系统已经模拟开篇、中期和后期的压力变化。这里展示的是推演证据和阻断问题，不是模型给自己的质量分数。你修改任何蓝图内容后，都需要用新版本重新测试。" />

            {selectedDirection && "kind" in selectedDirection && selectedDirection.kind === "pillar_synthesis" && (
              <div className="mt-5 border-l-2 border-[#4e6859] bg-[#edf1ec] px-4 py-3 text-sm leading-6 text-[#3f5749]">
                <strong>已融合 {selectedDirection.pillars.length} 个创作支柱</strong><br />
                {selectedDirection.pillars.map((pillar) => pillar.title).join(" · ")}
              </div>
            )}
            {research?.status === "completed" && (
              <details className="mt-5 border-l-2 border-[#587a8a] bg-[#eef4f6] px-4 py-3 text-sm text-[#385763]">
                <summary className="flex cursor-pointer items-center gap-2 font-semibold">
                  <Globe2 size={16} />联网题材研究 · {research.sources.length} 个来源
                </summary>
                <div className="mt-3 whitespace-pre-wrap leading-7">{research.memo}</div>
                {research.sources.length > 0 && (
                  <div className="mt-4 grid gap-2 md:grid-cols-2">
                    {research.sources.map((source) => (
                      <a className="flex min-w-0 items-start gap-2 border-t border-[#cadbdf] pt-2 text-xs font-semibold hover:underline" href={source.url} target="_blank" rel="noreferrer" key={source.url}>
                        <ExternalLink className="mt-0.5 shrink-0" size={13} />
                        <span className="min-w-0 break-words">{source.title}</span>
                      </a>
                    ))}
                  </div>
                )}
                <p className="mt-3 text-xs font-normal text-[#667b84]">这些是现实资料，不会自动成为小说设定；只有写入蓝图或正文后才属于本书事实。</p>
              </details>
            )}
            {research?.status === "unavailable" && research.warning && (
              <div className="mt-5 border-l-2 border-[#b7791f] bg-[#fff8e8] px-4 py-3 text-sm text-[#76551d]">
                联网题材研究暂不可用，本次仍按作者设定继续建书：{research.warning}
              </div>
            )}
            {error && foundation && !viability && (
              <div className="mt-5 border-l-2 border-[#b7791f] bg-[#fff8e8] px-4 py-3 text-sm leading-6 text-[#76551d]">
                <strong>故事根基已经保存</strong><br />{error} 你可以检查和修改蓝图，然后点击页面底部重新进行长篇压力测试。
              </div>
            )}
            {viability && (
              <section className={`mt-5 border-l-2 px-4 py-4 ${viability.verdict === "pass" && viability.blocking_issues.length === 0 ? "border-[#4e6859] bg-[#edf1ec]" : "border-[#a63f2f] bg-[#fff3ed]"}`}>
                <div className="flex items-center gap-2 text-sm font-bold">
                  {viability.verdict === "pass" && viability.blocking_issues.length === 0 ? <Check size={16} /> : <Compass size={16} />}
                  {viability.verdict === "pass" && viability.blocking_issues.length === 0 ? "长篇压力测试通过" : "这版蓝图还不能进入首章"}
                </div>
                {viability.blocking_issues.length > 0 && (
                  <ul className="mt-3 space-y-2 text-sm leading-6">{viability.blocking_issues.map((item) => <li key={item}>• {item}</li>)}</ul>
                )}
                <details className="mt-4">
                  <summary className="cursor-pointer text-sm font-semibold">查看跨卷推演证据</summary>
                  <div className="mt-3 grid gap-3 md:grid-cols-2">
                    <Info label="读者持续回报" value={viability.evidence.reader_payoff} />
                    <Info label="同类差异" value={viability.evidence.differentiation} />
                    <Info label="主角行动发动机" value={viability.evidence.protagonist_engine} />
                    <Info label="关系如何持续变化" value={viability.evidence.relationship_engine} />
                    <Info label="对手如何主动行动" value={viability.evidence.antagonist_agency} />
                    <Info label="中后期如何升级" value={viability.evidence.escalation_capacity} />
                  </div>
                  <div className="mt-3 grid gap-3 lg:grid-cols-3">
                    {viability.evidence.simulated_arcs.map((arc, index) => (
                      <div className="chapter-plan" key={`${arc.stage}-${index}`}>
                        <span>故事弧 {index + 1}</span><strong>{arc.stage}</strong>
                        <Info label="新压力" value={arc.new_pressure} />
                        <Info label="不可逆代价" value={arc.irreversible_cost} />
                        <Info label="结束后的变化" value={arc.changed_state} />
                      </div>
                    ))}
                  </div>
                </details>
              </section>
            )}

            {/* ── 快捷摘要栏（始终可见，一眼看全局） ── */}
            <div className="mt-6 rounded-lg border border-[#d9d2c6] bg-[#f8f6f1] p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
                  <span className="font-bold text-[#3e413c]">{f.engine.primary_genre || "待定"}</span>
                  <span className="text-[#888]">·</span>
                  <span>约 <strong>{f.scale_plan.estimated_chapters}</strong> 章 · <strong>{f.scale_plan.planned_volumes}</strong> 卷</span>
                  <span className="text-[#888]">·</span>
                  <span>目标 <strong>{(f.scale_plan.target_words / 10000).toFixed(0)}万</strong> 字</span>
                </div>
                <button type="button" className="shrink-0 text-xs font-semibold text-[#4e6859] hover:underline" onClick={() => setBriefOpen(true)}>
                  <Lock size={12} className="mr-1 inline" />查看创作依据
                </button>
              </div>
            </div>

            {/* ── 书名候选（横向标签） ── */}
            <div className="mt-5"><div className="form-label">暂定书名 <span className="font-normal text-[#999]">（从候选中选一个，或自己改）</span></div>
              <div className="mt-2 flex flex-wrap gap-2">{f.core.title_candidates.map((title) => <button type="button" className={`name-option ${selectedTitle === title ? "ring-2 ring-[#a63f2f]" : ""}`} key={title} onClick={() => setSelectedTitle(title)}>{title}</button>)}</div>
              <input className="field mt-2 h-10 px-3 font-normal" value={selectedTitle} onChange={(e) => setSelectedTitle(e.target.value)} placeholder="或直接输入书名…" />
            </div>

            <div className="mt-6">
              <TextField label="一句话故事" value={f.core.premise} onChange={(v) => setFoundation({ ...f, core: { ...f.core, premise: v } })} rows={3} />
            </div>

            <div className="mt-7 border-t border-[#ded8cc] pt-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 className="text-base font-semibold text-[#3e413c]">AI 为这本书决定的创作蓝图</h3>
                  <p className="mt-1 text-xs leading-5 text-[#888]">栏目会随题材变化，不要求每本书都填写同一套设定。</p>
                </div>
                <button type="button" className="secondary-button text-xs" disabled={loading || sectionLoading === "creative_brief"} onClick={() => generateSection("creative_brief")}>{sectionLoading === "creative_brief" ? <LoaderCircle size={14} className="animate-spin" /> : <Sparkles size={14} />} {sectionLoading === "creative_brief" ? "生成中" : "AI 重新设计这些栏目"}</button>
              </div>
              <div className="mt-4 grid gap-4 lg:grid-cols-2">
                {(f.creative_brief ?? []).map((item, index) => (
                  <div className="character-row" key={`${index}-${item.title}`}>
                    <div className="character-row-head">
                      <span>创作块 {index + 1}</span>
                      <button type="button" className="icon-button" title="删除这一项" aria-label="删除这一项" onClick={() => setFoundation({ ...f, creative_brief: (f.creative_brief ?? []).filter((_, itemIndex) => itemIndex !== index) })}><X size={14} /></button>
                    </div>
                    <div className="grid gap-3">
                      <TextField label="栏目名称" value={item.title} onChange={(v) => setFoundation({ ...f, creative_brief: updateAt(f.creative_brief ?? [], index, { title: v }) })} rows={1} />
                      <TextField label="具体内容" value={item.content} onChange={(v) => setFoundation({ ...f, creative_brief: updateAt(f.creative_brief ?? [], index, { content: v }) })} rows={5} />
                    </div>
                  </div>
                ))}
              </div>
              {(f.creative_brief ?? []).length === 0 && <p className="mt-4 text-sm text-[#999]">当前草稿来自旧版。点击“AI 重新设计这些栏目”，即可转换为动态蓝图。</p>}
              <button type="button" className="mt-4 secondary-button text-xs" onClick={() => setFoundation({ ...f, creative_brief: [...(f.creative_brief ?? []), { title: "自定义栏目", content: "" }] })}><Plus size={14} /> 新增一项</button>
              {(sectionMessage.creative_brief || sectionError.creative_brief) && <p className={`mt-2 text-sm ${sectionError.creative_brief ? "text-[#a63f2f]" : "text-[#4e6859]"}`}>{sectionError.creative_brief || sectionMessage.creative_brief}</p>}
            </div>

            {/* ── 规模与卷结构（默认收起，支持单独AI生成） ── */}
            <details className="hidden" aria-hidden="true">
              <summary className="flex cursor-pointer items-center gap-2 text-sm font-semibold text-[#656760]">
                规模规划与第一卷
                <button type="button" className="ml-2 rounded-md bg-[#edf1ec] px-2.5 py-1 text-xs font-semibold text-[#4e6859] hover:bg-[#dce4db]" disabled={loading || sectionLoading === "scale_volume"} onClick={(e) => { e.preventDefault(); e.currentTarget.closest("details")?.setAttribute("open", ""); generateSection("scale_volume"); }}>
                  {sectionLoading === "scale_volume" ? <LoaderCircle size={12} className="mr-1 inline animate-spin" /> : <Sparkles size={12} className="mr-1 inline" />}{sectionLoading === "scale_volume" ? "生成中" : "AI 重新规划"}
                </button>
              </summary>
              <div className="mt-4 blueprint-grid">
                <Info label="预计总章数" value={`约 ${f.scale_plan.estimated_chapters} 章`} />
                <Info label="全书卷数" value={`${f.scale_plan.planned_volumes} 卷，每卷约 ${f.scale_plan.average_chapters_per_volume} 章`} />
                <Info label="当前详细规划" value={`第1卷第1—${f.opening_window.chapter_directions.length}章`} />
                <Info label="成长分层" value={f.scale_plan.progression_ladders.join("；")} />
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <TextField label="卷名" value={f.first_volume.title} onChange={(v) => setFoundation({ ...f, first_volume: { ...f.first_volume, title: v } })} rows={1} />
                <TextField label="这一卷给读者的承诺" value={f.first_volume.reader_promise} onChange={(v) => setFoundation({ ...f, first_volume: { ...f.first_volume, reader_promise: v } })} rows={2} />
                <TextField label="整卷目标" value={f.first_volume.volume_goal} onChange={(v) => setFoundation({ ...f, first_volume: { ...f.first_volume, volume_goal: v } })} rows={2} />
                <TextField label="卷中点变化" value={f.first_volume.midpoint_change} onChange={(v) => setFoundation({ ...f, first_volume: { ...f.first_volume, midpoint_change: v } })} rows={2} />
                <TextField label="卷末高潮选择" value={f.first_volume.climax_choice} onChange={(v) => setFoundation({ ...f, first_volume: { ...f.first_volume, climax_choice: v } })} rows={2} />
                <TextField label="卷末局面" value={f.first_volume.ending_state} onChange={(v) => setFoundation({ ...f, first_volume: { ...f.first_volume, ending_state: v } })} rows={2} />
              </div>
              <div className="mt-3 border-l-2 border-[#4e6859] bg-[#edf1ec] px-4 py-2.5 text-xs leading-5 text-[#4d5d52]"><strong>本卷暂不揭晓：</strong>{f.first_volume.protected_reveals.join("；")}</div>
              {(sectionMessage.scale_volume || sectionError.scale_volume) && (
                <p className={`mt-2 text-sm ${sectionError.scale_volume ? "text-[#a63f2f]" : "text-[#4e6859]"}`}>
                  {sectionError.scale_volume || sectionMessage.scale_volume}
                </p>
              )}
            </details>

            {/* ── 金手指（默认收起） ── */}
            <details className="hidden" aria-hidden="true">
              <summary className="cursor-pointer text-sm font-semibold text-[#656760]">金手指设定（选填）</summary>
              <p className="mt-2 text-xs text-[#999]">唯一、受限、保密、简单、成长——主角自身成长才是核心，金手指只是放大器。</p>
              <TextField label="你的金手指设想" value={goldenFinger} onChange={setGoldenFinger} rows={3} className="mt-3" />
            </details>

            {/* ── 配角（默认收起，支持单独AI生成） ── */}
            <details className="hidden" aria-hidden="true">
              <summary className="flex cursor-pointer items-center gap-2 text-sm font-semibold text-[#656760]">
                关键人物{f.characters.length > 0 && `（${f.characters.length} 位）`}
                {f.characters.length === 0 && (
                  <button type="button" className="ml-2 rounded-md bg-[#edf1ec] px-2.5 py-1 text-xs font-semibold text-[#4e6859] hover:bg-[#dce4db]" disabled={loading || sectionLoading === "characters"} onClick={(e) => { e.preventDefault(); e.currentTarget.closest("details")?.setAttribute("open", ""); generateSection("characters"); }}>
                    {sectionLoading === "characters" ? <LoaderCircle size={12} className="mr-1 inline animate-spin" /> : <Sparkles size={12} className="mr-1 inline" />}{sectionLoading === "characters" ? "生成中" : "AI 生成配角"}
                  </button>
                )}
              </summary>
              <div className="mt-4">
                {f.characters.length > 0 ? (
                  <div className="grid gap-4 lg:grid-cols-2">{f.characters.map((character, index) => (
                    <div className="character-row" key={`${character.name}-${index}`}>
                      <div className="character-row-head"><span>关键人物 {index + 1}</span></div>
                      <div className="grid gap-3 md:grid-cols-2">
                        <TextField label="名字" value={character.name} onChange={(v) => setFoundation({ ...f, characters: updateAt(f.characters, index, { name: v }) })} rows={1} />
                        <TextField label="身份" value={character.role} onChange={(v) => setFoundation({ ...f, characters: updateAt(f.characters, index, { role: v }) })} rows={1} />
                        <TextField label="自己想要什么" value={character.desire} onChange={(v) => setFoundation({ ...f, characters: updateAt(f.characters, index, { desire: v }) })} rows={2} />
                        <TextField label="离场后仍会做什么" value={character.offstage_action} onChange={(v) => setFoundation({ ...f, characters: updateAt(f.characters, index, { offstage_action: v }) })} rows={2} />
                      </div>
                    </div>
                  ))}</div>
                ) : (
                  <p className="text-sm text-[#999]">尚未生成配角。点击上方「AI 生成配角」根据已确定的主角和世界自动设计 2-3 位关键人物。</p>
                )}
                {f.characters.length > 0 && (
                  <button type="button" className="mt-3 secondary-button text-xs" disabled={loading || sectionLoading === "characters"} onClick={() => generateSection("characters")}>{sectionLoading === "characters" ? <LoaderCircle size={14} className="animate-spin" /> : <RefreshCw size={14} />} {sectionLoading === "characters" ? "生成中" : "重新生成配角"}</button>
                )}
                {(sectionMessage.characters || sectionError.characters) && <p className={`mt-2 text-sm ${sectionError.characters ? "text-[#a63f2f]" : "text-[#4e6859]"}`}>{sectionError.characters || sectionMessage.characters}</p>}
              </div>
            </details>

            {/* ── 全书阶段 + 章节方向（默认收起，分步生成） ── */}
            <details className="hidden" aria-hidden="true">
              <summary className="flex cursor-pointer items-center gap-2 text-sm font-semibold text-[#656760]">
                全书阶段方向与前 10 章细纲（高级）
                {f.stages.length === 0 && (
                  <button type="button" className="ml-2 rounded-md bg-[#edf1ec] px-2.5 py-1 text-xs font-semibold text-[#4e6859] hover:bg-[#dce4db]" disabled={loading || sectionLoading === "stages"} onClick={(e) => { e.preventDefault(); e.currentTarget.closest("details")?.setAttribute("open", ""); generateSection("stages"); }}>
                    {sectionLoading === "stages" ? <LoaderCircle size={12} className="mr-1 inline animate-spin" /> : <Sparkles size={12} className="mr-1 inline" />}{sectionLoading === "stages" ? "生成中" : "AI 规划全书阶段"}
                  </button>
                )}
              </summary>
              <div className="mt-4">
                {/* 阶段规划 */}
                <div className="mb-4 flex items-center justify-between">
                  <div className="text-xs font-semibold text-[#656760]">阶段规划</div>
                  {f.stages.length > 0 && (
                    <button type="button" className="text-xs font-semibold text-[#4e6859] hover:underline" disabled={loading || sectionLoading === "stages"} onClick={() => generateSection("stages")}>{sectionLoading === "stages" ? <LoaderCircle size={12} className="mr-1 inline animate-spin" /> : <RefreshCw size={12} className="mr-1 inline" />}{sectionLoading === "stages" ? "生成中" : "重新生成"}</button>
                  )}
                </div>
                {f.stages.length > 0 ? (
                  <div className="grid gap-3 lg:grid-cols-3">{f.stages.map((stage) => <div className="chapter-plan" key={stage.name}><span>第 {stage.chapter_range[0]}—{stage.chapter_range[1]} 章</span><strong>{stage.name}</strong><Info label="目标" value={stage.goal} /><Info label="结束才发生" value={stage.changed_state} /></div>)}</div>
                ) : (
                  <p className="mb-4 text-sm text-[#999]">尚未规划阶段。AI 将根据已确定的规模和引擎，把全书的远期格局分成 3-5 个大阶段。</p>
                )}

                {/* 可选开篇草案 */}
                <div className="mt-6 border-t border-[#eee] pt-4">
                  <div className="mb-3 flex items-center justify-between">
                    <div className="text-xs font-semibold text-[#656760]">开篇方向草案（可选）</div>
                    {f.opening_window.chapter_directions.length === 0 && (
                    <button type="button" className="rounded-md bg-[#edf1ec] px-2.5 py-1 text-xs font-semibold text-[#4e6859] hover:bg-[#dce4db]" disabled={loading || sectionLoading === "opening_window"} onClick={() => generateSection("opening_window")}>{sectionLoading === "opening_window" ? <LoaderCircle size={12} className="mr-1 inline animate-spin" /> : <Sparkles size={12} className="mr-1 inline" />}{sectionLoading === "opening_window" ? "生成中" : "AI 预想开篇"}
                    </button>
                    )}
                    {f.opening_window.chapter_directions.length > 0 && (
                      <button type="button" className="text-xs font-semibold text-[#4e6859] hover:underline" disabled={loading || sectionLoading === "opening_window"} onClick={() => generateSection("opening_window")}>{sectionLoading === "opening_window" ? <LoaderCircle size={12} className="mr-1 inline animate-spin" /> : <RefreshCw size={12} className="mr-1 inline" />}{sectionLoading === "opening_window" ? "生成中" : "重新生成"}
                      </button>
                    )}
                  </div>
                  {f.opening_window.chapter_directions.length > 0 ? (
                    <div className="grid gap-3 lg:grid-cols-2">{f.opening_window.chapter_directions.map((ch, i) => (
                      <div className="chapter-plan" key={ch.sequence}>
                        <span>第 {ch.sequence} 章 · {FUNCTION_LABELS[ch.function]}</span>
                        <TextField label="章名" value={ch.title} onChange={(v) => setFoundation({ ...f, opening_window: { ...f.opening_window, chapter_directions: updateAt(f.opening_window.chapter_directions, i, { title: v }) } })} rows={1} />
                        <details className="mt-2"><summary className="cursor-pointer text-[11px] text-[#999]">展开细节</summary>
                          <div className="mt-2 grid gap-2">
                            <TextField label="读者要明白什么" value={ch.reader_orientation} onChange={(v) => setFoundation({ ...f, opening_window: { ...f.opening_window, chapter_directions: updateAt(f.opening_window.chapter_directions, i, { reader_orientation: v }) } })} rows={1} />
                            <TextField label="眼前只做什么" value={ch.immediate_goal} onChange={(v) => setFoundation({ ...f, opening_window: { ...f.opening_window, chapter_directions: updateAt(f.opening_window.chapter_directions, i, { immediate_goal: v }) } })} rows={1} />
                            <TextField label="本章行动" value={ch.main_action} onChange={(v) => setFoundation({ ...f, opening_window: { ...f.opening_window, chapter_directions: updateAt(f.opening_window.chapter_directions, i, { main_action: v }) } })} rows={1} />
                            <TextField label="眼前后果" value={ch.immediate_consequence} onChange={(v) => setFoundation({ ...f, opening_window: { ...f.opening_window, chapter_directions: updateAt(f.opening_window.chapter_directions, i, { immediate_consequence: v }) } })} rows={1} />
                            <TextField label="新增信息" value={ch.information_gain} onChange={(v) => setFoundation({ ...f, opening_window: { ...f.opening_window, chapter_directions: updateAt(f.opening_window.chapter_directions, i, { information_gain: v }) } })} rows={1} />
                          </div>
                        </details>
                      </div>
                    ))}</div>
                  ) : (
                    <p className="text-sm text-[#999]">可以直接生成第一章；这里的预想不会约束工作台后续章纲。</p>
                  )}
                </div>
                {(sectionMessage.stages || sectionMessage.opening_window || sectionError.stages || sectionError.opening_window) && (
                  <p className={`mt-2 text-sm ${sectionError.stages || sectionError.opening_window ? "text-[#a63f2f]" : "text-[#4e6859]"}`}>
                    {sectionError.stages || sectionError.opening_window || sectionMessage.stages || sectionMessage.opening_window}
                  </p>
                )}
              </div>
            </details>

            {/* ── 底部操作 ── */}
            <div className="mt-7 flex justify-end border-t border-[#ded8cc] pt-5">
              <p className="text-xs text-[#999]">动态蓝图可增删改 · 后续以你最后确认的版本为准</p>
            </div>
            <Footer
              loading={loading}
              loadingText={loadingText}
              loadingSeconds={loadingSeconds}
              error={error}
              onBack={() => setStep(1)}
              nextLabel={reviewedFoundationSnapshot !== foundationVersion || viability?.verdict !== "pass" || Boolean(viability.blocking_issues.length) ? "用当前版本重新压力测试" : "确认开篇策略，试写第一章"}
              onNext={generatePilot}
            />
          </section>
        )}

        {/* ═══════════════ STEP 3 ═══════════════ */}
        {step === 3 && f && pilot && (
          <section>
            <Heading kicker="先读，再决定" title="第一章就是这套故事方法的试金石" text="你可以直接改正文，也可以写下不满意的地方让 AI 重写。只有你确认后，作品和长期记忆才会正式建立。" />
            {!pilotIsCurrent && <div className="mt-5 border-l-2 border-[#a63f2f] bg-[#fff3ed] px-4 py-3 text-sm text-[#8a493c]">故事根基已经改变，这一版正文已过期。请按当前设定重新生成。</div>}
            <div className="mt-6 grid gap-4 md:grid-cols-[minmax(0,1fr)_280px]">
              <div>
                <label className="form-label">章名<input className="field mt-2 h-11 px-3 font-normal" value={pilot.title} onChange={(event) => setPilot({ ...pilot, title: event.target.value })} /></label>
                <textarea className="field mt-4 min-h-[480px] resize-y p-5 font-editorial text-[15px] font-normal leading-8" value={pilot.content} onChange={(event) => setPilot({ ...pilot, content: event.target.value })} />
              </div>
              <aside className="border-l border-[#ded8cc] pl-5">
                <div className="flex items-center gap-2 text-sm font-bold"><Compass size={16} />这一章必须完成</div>
                <Info label="人物眼前要做什么" value={pilot.scene_contract.immediate_goal} />
                <Info label="眼前遇到什么阻力" value={pilot.scene_contract.resistance} />
                <Info label="主角采取什么行动" value={pilot.scene_contract.decision} />
                <Info label="行动造成什么眼前后果" value={pilot.scene_contract.immediate_consequence} />
                <Info label="读者接下来等什么" value={pilot.scene_contract.next_promise} />
                <label className="form-label mt-7">告诉 AI 哪里不对<textarea className="field mt-2 min-h-28 p-3 font-normal" value={authorNote} onChange={(event) => setAuthorNote(event.target.value)} placeholder="例如：主角太冷静了；开头解释太多；这段关系不像我想要的……" /></label>
                <button type="button" className="secondary-button mt-3 w-full" disabled={loading} onClick={generatePilot}><RefreshCw size={16} />按反馈重写整章</button>
              </aside>
            </div>
            <Footer loading={loading} loadingText={loadingText} loadingSeconds={loadingSeconds} error={error} onBack={() => setStep(2)} nextLabel="接受这一章，建立作品" onNext={createProject} disabled={!pilotIsCurrent || pilot.content.trim().length < 200} />
          </section>
        )}
        <IntentBrief
          open={briefOpen}
          onClose={() => setBriefOpen(false)}
          idea={idea}
          genre={f?.engine.primary_genre ?? ""}
          style={styleReference}
          creativeBrief={f?.creative_brief ?? []}
        />
      </div>
    </div>
  );
}

function Heading({ kicker, title, text }: { kicker: string; title: string; text: string }) {
  return <div className="max-w-3xl"><div className="flex items-center gap-2 text-xs font-bold text-[#a63f2f]"><BookOpenText size={15} />{kicker}</div><h2 className="mt-2 font-editorial text-2xl font-bold leading-tight md:text-3xl">{title}</h2><p className="mt-3 text-sm leading-7 text-[#6d6f68]">{text}</p></div>;
}

function TextField({ label, value, onChange = () => undefined, rows = 3, readOnly = false, className = "" }: { label: string; value: string; onChange?: (value: string) => void; rows?: number; readOnly?: boolean; className?: string }) {
  const roClass = readOnly ? "bg-[#f1eee7] text-[#6d6f68]" : "";
  return (
    <label className={`form-label ${className}`}>
      {label}
      <textarea rows={rows} readOnly={readOnly} className={`field mt-1.5 resize-y p-3 font-normal leading-6 ${roClass}`} value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return <div className="info-block"><div>{label}</div><p>{value}</p></div>;
}

function Footer({ loading, loadingText, loadingSeconds, error, onBack, onNext, nextLabel, disabled = false }: { loading: boolean; loadingText: string; loadingSeconds: number; error: string | null; onBack?: () => void; onNext: () => void; nextLabel: string; disabled?: boolean }) {
  const status = loadingSeconds >= 20 ? `${loadingText} 已等待 ${loadingSeconds} 秒` : loadingText;
  const statusEl = loading ? <span className="inline-flex items-center gap-2 text-[#4e6859]"><LoaderCircle className="animate-spin" size={16} />{status}</span> : error;
  const backBtn = onBack ? <button type="button" className="secondary-button" disabled={loading} onClick={onBack}><ArrowLeft size={16} />上一步</button> : <span />;
  return (
    <div className="wizard-footer">
      <div className="min-h-6 text-sm text-[#a63f2f]" aria-live="polite">{statusEl}</div>
      <div className="mt-3 flex justify-between gap-3">
        {backBtn}
        <button type="button" className="primary-button" disabled={loading || disabled} onClick={onNext}>
          {loading ? <LoaderCircle className="animate-spin" size={17} /> : <Sparkles size={17} />}
          {loading ? "生成中" : nextLabel}
          {!loading && !disabled && <ArrowRight size={16} />}
        </button>
      </div>
    </div>
  );
}

/** 意图书汇总页 */
function IntentBrief({
  open, onClose, idea, genre, style, creativeBrief,
}: {
  open: boolean; onClose: () => void; idea: string; genre: string; style: string;
  creativeBrief: CreativeBriefItem[];
}) {
  if (!open) return null;
  const sources = [
    { label: "一句话点子", value: idea },
    { label: "类型", value: genre },
    { label: "基调 / 文笔", value: style },
    ...creativeBrief.map((item) => ({ label: item.title, value: item.content })),
  ].filter((item) => item.value.trim());
  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/45 p-3 backdrop-blur-sm sm:p-6" role="dialog" aria-modal="true" aria-label="意图书">
      <div className="flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden bg-[#fbfaf6] shadow-2xl sm:rounded-md">
        <div className="flex items-start justify-between border-b border-[#ded8cd] px-5 py-4">
          <div>
            <div className="flex items-center gap-2 text-xs font-bold text-[#a63f2f]"><BookOpenText size={15} />创作依据</div>
            <h2 className="mt-1 font-editorial text-2xl font-bold">后续会优先使用这些内容</h2>
            <p className="mt-1 text-xs text-[#77786f]">它们不是不可变的锁。你在工作台修改章纲或正文后，后续写作以最新版为准。</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} title="关闭" aria-label="关闭"><X size={17} /></button>
        </div>
        <div className="scrollbar-thin flex-1 overflow-y-auto px-5 py-5">
          <div className="grid gap-3 sm:grid-cols-2">
            {sources.map((item, index) => (
              <div key={`${item.label}-${index}`} className="rounded-md border border-[#ded8cd] bg-[#f8f6f1] p-4">
                <div className="text-[11px] font-bold text-[#4e6859]">{item.label}</div>
                <p className="mt-2 text-sm leading-6 text-[#3e413c]">{item.value.trim() || <span className="text-[#a89b78]">（暂未填写，可继续编辑）</span>}</p>
              </div>
            ))}
          </div>
        </div>
        <div className="flex items-center justify-between gap-3 border-t border-[#ded8cd] px-5 py-4">
          <p className="text-xs text-[#8a8174]">这里汇总的是当前版本，不保存重复历史</p>
          <button className="primary-button" type="button" onClick={onClose}>我已知晓</button>
        </div>
      </div>
    </div>
  );
}
