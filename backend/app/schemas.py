import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserRead"


class UserCreate(BaseModel):
    nickname: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=6, max_length=128)


class UserLogin(BaseModel):
    nickname: str
    password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nickname: str
    created_at: datetime


class AcceptedOpeningPilot(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=200, max_length=50_000)
    summary: str = Field(min_length=5, max_length=2000)
    scene_contract: dict[str, Any] = Field(default_factory=dict)


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    genre: str = Field(min_length=1, max_length=50)
    one_sentence: str = Field(min_length=10, max_length=2000)
    protagonist_name: str = Field(min_length=1, max_length=100)
    protagonist_gender: str = Field(min_length=1, max_length=20)
    protagonist_personality: str = Field(min_length=2, max_length=2000)
    target_words: int = Field(default=1_000_000, ge=100_000, le=8_000_000)
    creation_mode: str = Field(
        default="inspired",
        pattern=r"^(inspired|guided|continuation|fanfic|imitation|immersive|lazy)$",
    )
    channel: str | None = None
    track: str | None = None
    source_work_id: uuid.UUID | None = None
    planning_profile: dict[str, Any] = Field(default_factory=dict)
    opening_pilot: AcceptedOpeningPilot | None = None
    golden_finger: str | None = None
    intent_brief: dict[str, Any] | None = None
    creation_session_id: uuid.UUID | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    genre: str
    one_sentence: str
    protagonist_name: str
    protagonist_gender: str
    protagonist_personality: str
    target_words: int
    total_chapters: int
    status: str
    current_chapter: int
    style_profile: dict[str, Any]
    generation_state: dict[str, Any]
    creation_mode: str
    channel: str | None
    track: str | None
    source_work_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: str | None = Field(default=None, pattern=r"^(draft|planning|writing|paused|completed)$")
    style_profile: dict[str, Any] | None = None


class StoryWikiRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    category: str
    title: str
    content: str
    aliases: list[str]
    wikilinks: list[str]
    last_updated_chapter: int
    source_chapters: list[int]
    visibility: str


class StoryWikiUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    aliases: list[str] | None = None
    wikilinks: list[str] | None = None
    visibility: str | None = None


class StoryWikiCreate(BaseModel):
    category: str = Field(pattern=r"^(character|worldview|canon_rule|timeline|location)$")
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=10_000)
    aliases: list[str] = Field(default_factory=list)


class OutlineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    parent_id: uuid.UUID | None
    level: str
    sequence: int
    title: str
    content: dict[str, Any]
    is_sealed: bool


class OutlineUpdate(BaseModel):
    title: str | None = None
    content: dict[str, Any] | None = None
    is_sealed: bool | None = None


class ChapterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    volume_sequence: int
    chapter_sequence: int
    title: str
    content: str
    summary: str
    word_count: int
    status: str
    quality_scores: dict[str, Any]
    beat_sheet: dict[str, Any]
    generation_log: dict[str, Any]
    updated_at: datetime


class ChapterUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    summary: str | None = None
    beat_sheet: dict[str, Any] | None = None


class ChapterRewriteRequest(BaseModel):
    focus: list[str] = Field(default_factory=list, max_length=5)
    preserve: list[str] = Field(default_factory=list, max_length=5)
    instruction: str = Field(default="", max_length=1000)
    request_key: str | None = Field(default=None, max_length=100)
    operation: Literal["rewrite", "optimize"] = "rewrite"


class ChapterLightOptimizeRequest(BaseModel):
    focus: list[str] = Field(default_factory=list, max_length=8)
    preserve: list[str] = Field(default_factory=list, max_length=8)
    instruction: str = Field(min_length=2, max_length=3000)


class ChapterPlanGenerateRequest(BaseModel):
    instruction: str = Field(default="", max_length=1000)


class ChapterPlanWindowItem(BaseModel):
    chapter_sequence: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=200)
    plan: dict[str, Any]


class ChapterPlanWindowUpdate(BaseModel):
    chapters: list[ChapterPlanWindowItem] = Field(min_length=1, max_length=10)


class ForeshadowingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    content: str
    planted_chapter: int
    target_chapter: int | None
    resolved_chapter: int | None
    importance: str
    status: str
    escalation_count: int
    related_characters: list[str]


class StateLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chapter_sequence: int
    dimension: str
    entity_name: str
    field: str | None
    old_value: str | None
    new_value: str | None
    confidence: float
    source: str
    created_at: datetime


class GenerateStatusRead(BaseModel):
    status: str
    current_chapter: int
    total_chapters: int
    active: bool
    last_event: dict[str, Any] | None = None
    run_id: uuid.UUID | None = None
    run_status: str | None = None
    current_node: str | None = None
    attempt: int = 0
    error: str | None = None
    auto_write: bool = False
    operation: Literal["write", "rewrite", "optimize"] | None = None


class GenerateStartRead(BaseModel):
    run_id: uuid.UUID
    status: str
    chapter_sequence: int
    reused: bool = False


class ExportRead(BaseModel):
    filename: str
    content: str


class MemorySearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    mode: Literal["hybrid", "pageindex", "both"] = "both"
    entities: list[str] = Field(default_factory=list, max_length=20)
    limit: int = Field(default=12, ge=1, le=50)


class MemorySearchResponse(BaseModel):
    hybrid: list[dict[str, Any]] = Field(default_factory=list)
    pageindex: list[dict[str, Any]] = Field(default_factory=list)


class WikiLintResponse(BaseModel):
    issues: list[dict[str, Any]]
    issue_count: int


class ChapterRevisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chapter_sequence: int
    revision: int
    status: str
    title: str
    summary: str
    word_count: int
    body_sha256: str
    quality_scores: dict[str, Any]
    created_at: datetime
    published_at: datetime | None


class ImportedWorkCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    author: str | None = None
    source_platform: str | None = None
    content: str = Field(min_length=100)


class ImportedWorkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    author: str | None
    source_platform: str | None
    total_chapters: int
    total_words: int
    genre: str | None
    sub_genre: str | None
    analysis_status: str
    analysis_progress: float
    breakpoint_analysis: dict[str, Any] | None
    style_profile: dict[str, Any] | None
    rights_status: str
    created_at: datetime


class ImportedWorkReport(BaseModel):
    work: "ImportedWorkRead"
    characters: list[dict[str, Any]]
    world_rules: list[dict[str, Any]]
    foreshadowing: list[dict[str, Any]]
    power_system: dict[str, Any] | None
    thrill_formula: str | None
    style_summary: str | None


class MarketTrackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    track_name: str
    channel: str
    genre: str
    sub_genre: str | None
    heat: int
    heat_trend: str
    competition: str
    difficulty: str
    monetization: list[Any]
    benchmark_works: list[Any]
    taste_tags: list[str]
    golden_formula: str | None
    platform_tips: str | None


class TropeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trope_name: str
    pattern: str
    hook_template: str | None
    pacing_formula: str | None
    source_works: list[str]
    channel: str | None
    genre: str | None
    tags: list[str]


class HotNovelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    author: str | None
    platform: str | None
    genre: str | None
    tags: list[str]
    synopsis: str | None
    rank_position: int | None
    reviews_summary: str | None
    sample_hook: str | None


class TasteMatchRequest(BaseModel):
    taste_tags: list[str] = Field(default_factory=list)
    channel: str | None = None
    feeling: str | None = None
    reader_wish: str | None = Field(default=None, max_length=1000)
    primary_category: str | None = Field(default=None, max_length=50)
    primary_categories: list[str] = Field(default_factory=list, max_length=5)
    favorite_works: str | None = Field(default=None, max_length=500)
    avoid_elements: str | None = Field(default=None, max_length=500)
    target_words: int = Field(default=800_000, ge=100_000, le=8_000_000)


class TasteMatchResponse(BaseModel):
    tracks: list[MarketTrackRead]
    ai_commentary: str | None = None


class StorySeedRequest(BaseModel):
    request_id: uuid.UUID | None = None
    taste_tags: list[str] = Field(default_factory=list)
    channel: str | None = None
    reader_wish: str | None = Field(default=None, max_length=1000)
    primary_category: str | None = Field(default=None, max_length=50)
    primary_categories: list[str] = Field(default_factory=list, max_length=5)
    favorite_works: str | None = Field(default=None, max_length=500)
    avoid_elements: str | None = Field(default=None, max_length=500)
    style_description: str | None = Field(default=None, max_length=3000)
    author_intent: dict[str, str] = Field(default_factory=dict)
    world_engine: dict[str, Any] = Field(default_factory=dict)
    target_words: int = Field(default=800_000, ge=100_000, le=8_000_000)
    count: int = Field(default=3, ge=1, le=5)


class StorySeed(BaseModel):
    title: str
    one_sentence: str
    protagonist_name: str
    protagonist_gender: str
    protagonist_personality: str
    hook: str
    genre: str
    core_conflict: str = ""
    market_reason: str = ""
    taste_reason: str = ""
    difference: str = ""
    reader_promise: str = ""
    story_engine: str = ""
    long_term_growth: str = ""
    relationship_hook: str = ""
    opening_event: str = ""
    risk_note: str = ""
    story_question: str = ""
    protagonist_method: str = ""
    protagonist_cost: str = ""


class StorySeedResponse(BaseModel):
    seeds: list[StorySeed]


class StoryRefineRequest(BaseModel):
    seed: StorySeed
    adjustments: dict[str, str] = Field(default_factory=dict)


class BookBlueprintRequest(BaseModel):
    seed: StorySeed
    channel: str | None = None
    primary_category: str
    primary_categories: list[str] = Field(default_factory=list, max_length=5)
    taste_tags: list[str] = Field(default_factory=list)
    reader_wish: str | None = Field(default=None, max_length=1000)
    target_words: int = Field(default=800_000, ge=100_000, le=8_000_000)
    style_description: str | None = Field(default=None, max_length=3000)
    characters: list[dict[str, Any]] = Field(default_factory=list, max_length=10)
    author_intent: dict[str, str] = Field(default_factory=dict)
    world_engine: dict[str, Any] = Field(default_factory=dict)
    story_question: str | None = Field(default=None, max_length=500)


class WorldEngineRequest(BaseModel):
    genre: str = Field(min_length=1, max_length=50)
    channel: str | None = Field(default=None, max_length=20)
    primary_categories: list[str] = Field(default_factory=list, max_length=5)
    reader_wish: str | None = Field(default=None, max_length=1000)
    favorite_works: str | None = Field(default=None, max_length=500)
    avoid_elements: str | None = Field(default=None, max_length=500)
    author_intent: dict[str, str] = Field(default_factory=dict)
    world_engine: dict[str, Any] = Field(default_factory=dict)


class WorldEngineResponse(BaseModel):
    world_engine: dict[str, Any]
    validation: dict[str, Any]
    research_sources: list[dict[str, str]] = Field(default_factory=list)


class StylePolishRequest(BaseModel):
    description: str = Field(min_length=1, max_length=3000)
    genre: str | None = Field(default=None, max_length=100)


class StylePolishResponse(BaseModel):
    description: str


class StyleAnalyzeRequest(BaseModel):
    title: str = Field(default="", max_length=200)
    text: str = Field(min_length=50, max_length=200000)
    genre: str | None = Field(default=None, max_length=100)
    focus: Literal["style", "world", "both"] = "both"


class CharacterCastRequest(BaseModel):
    seed: StorySeed
    primary_categories: list[str] = Field(default_factory=list, max_length=5)
    reader_wish: str | None = Field(default=None, max_length=1000)
    existing_characters: list[dict[str, Any]] = Field(default_factory=list, max_length=10)
    author_intent: dict[str, str] = Field(default_factory=dict)
    world_engine: dict[str, Any] = Field(default_factory=dict)
    story_question: str | None = Field(default=None, max_length=500)
    mode: Literal["full", "names"] = "full"


class CreationFoundationRequest(BaseModel):
    idea: str = Field(min_length=20, max_length=12_000)
    genre: str | None = Field(default=None, max_length=50)
    genres: list[str] = Field(default_factory=list, max_length=3)
    channel: Literal["男频", "女频", "不限"] = "不限"
    target_words: int = Field(default=1_000_000, ge=100_000, le=8_000_000)
    reader_wish: str | None = Field(default=None, max_length=2000)
    avoid_elements: str | None = Field(default=None, max_length=2000)
    style_reference: str | None = Field(default=None, max_length=6000)


class StoryDirection(BaseModel):
    key: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=2, max_length=100)
    logline: str = Field(min_length=20, max_length=1000)
    reader_payoff: str = Field(min_length=20, max_length=1200)
    differentiation: str = Field(min_length=20, max_length=1200)
    protagonist_engine: str = Field(min_length=20, max_length=1200)
    serial_engine: str = Field(min_length=20, max_length=1600)
    emotional_throughline: str = Field(min_length=20, max_length=1200)
    cost_and_risk: str = Field(min_length=20, max_length=1200)


class CreationStudioStartRequest(CreationFoundationRequest):
    pass


class CreationDirectionSelectRequest(BaseModel):
    selected_indices: list[int] = Field(min_length=2, max_length=6)
    primary_index: int | None = Field(default=None, ge=0, le=5)
    user_note: str | None = Field(default=None, max_length=3000)

    @model_validator(mode="after")
    def validate_pillar_selection(self) -> "CreationDirectionSelectRequest":
        if len(set(self.selected_indices)) != len(self.selected_indices):
            raise ValueError("创作支柱不能重复选择")
        if any(index < 0 or index > 5 for index in self.selected_indices):
            raise ValueError("创作支柱序号无效")
        if self.primary_index is not None and self.primary_index not in self.selected_indices:
            raise ValueError("主支柱必须包含在已选支柱中")
        return self


class CreativeSynthesis(BaseModel):
    kind: Literal["pillar_synthesis"] = "pillar_synthesis"
    pillars: list[StoryDirection] = Field(min_length=2, max_length=6)
    primary_keys: list[str] = Field(default_factory=list, min_length=1, max_length=2)
    synthesis_note: str = Field(default="", max_length=3000)


class ViabilityEvidence(BaseModel):
    reader_payoff: str = Field(min_length=20)
    differentiation: str = Field(min_length=20)
    protagonist_engine: str = Field(min_length=20)
    story_engine_variations: list[str] = Field(min_length=3, max_length=6)
    relationship_engine: str = Field(min_length=20)
    antagonist_agency: str = Field(min_length=20)
    escalation_capacity: str = Field(min_length=20)
    simulated_arcs: list[dict[str, Any]] = Field(min_length=3, max_length=6)
    promise_ledger: list[dict[str, Any]] = Field(min_length=4, max_length=12)
    opening_strategy: dict[str, str]
    endgame_direction: str = Field(min_length=20)


class ViabilityReviewData(BaseModel):
    verdict: Literal["pass", "revise"]
    evidence: ViabilityEvidence
    blocking_issues: list[str] = Field(default_factory=list, max_length=12)
    warnings: list[str] = Field(default_factory=list, max_length=12)


class ResearchSource(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=8, max_length=2000)
    snippet: str = Field(default="", max_length=1000)


class StoryResearchData(BaseModel):
    status: Literal["completed", "unavailable"]
    query: str = Field(default="", max_length=4000)
    memo: str = Field(default="", max_length=12_000)
    sources: list[ResearchSource] = Field(default_factory=list, max_length=12)
    warning: str | None = Field(default=None, max_length=1000)


class CreationStudioRead(BaseModel):
    session_id: uuid.UUID
    state: str
    directions: list[StoryDirection] = Field(default_factory=list)
    selected_direction: StoryDirection | CreativeSynthesis | None = None
    foundation: "CreationFoundation | None" = None
    foundation_version: int = 0
    viability: ViabilityReviewData | None = None
    research: StoryResearchData | None = None
    author_confirmed: bool = False
    error: str | None = None


class CreationStudioConfirmRequest(BaseModel):
    foundation: "CreationFoundation"
    author_note: str | None = Field(default=None, max_length=3000)


class StoryCore(BaseModel):
    title_candidates: list[str] = Field(min_length=1, max_length=5)
    premise: str
    reader_promise: str
    central_question: str
    emotional_core: str
    ending_direction: str


class StoryEngine(BaseModel):
    engine_type: str
    primary_genre: str
    long_term_loop: str
    progression_dimensions: list[str] = Field(min_length=1, max_length=6)
    escalation_rule: str


class FoundationWorld(BaseModel):
    genre_flavor: str = ""
    power_system: str = ""
    factions: str = ""
    geography: str = ""
    daily_life: str = ""
    history_pressure: str = ""
    core_rule: str
    social_order: str
    scarce_resource: str
    cost: str
    opening_locality: str
    visible_rules: list[str] = Field(min_length=1, max_length=8)
    reserve: list[str] = Field(default_factory=list, max_length=8)


class FoundationProtagonist(BaseModel):
    name: str
    gender: str
    starting_state: str
    desire: str
    fear: str
    belief: str
    method: str
    bottom_line: str
    contradiction: str


class FoundationCharacter(BaseModel):
    name: str
    role: str
    desire: str
    method: str
    leverage: str
    relationship: str
    offstage_action: str


class FoundationBriefItem(BaseModel):
    """AI 按题材自行决定的作者可见蓝图条目。"""

    title: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=6000)


class StoryStage(BaseModel):
    name: str
    chapter_range: list[int] = Field(min_length=2, max_length=2)
    starting_state: str
    goal: str
    pressure: str
    irreversible_choice: str
    changed_state: str
    promise_payoff: str


class ScalePlan(BaseModel):
    target_words: int = Field(ge=100_000, le=8_000_000)
    estimated_chapters: int = Field(ge=30, le=2500)
    planned_volumes: int = Field(ge=3, le=20)
    average_chapters_per_volume: int = Field(ge=20, le=100)
    opening_window_chapters: int = Field(ge=8, le=12)
    progression_ladders: list[str] = Field(min_length=2, max_length=6)
    pacing_boundaries: list[str] = Field(min_length=4, max_length=10)


class FirstVolume(BaseModel):
    sequence: int = 1
    title: str
    chapter_range: list[int] = Field(min_length=2, max_length=2)
    reader_promise: str
    starting_state: str
    volume_goal: str
    central_pressure: str
    midpoint_change: str
    climax_choice: str
    ending_state: str
    progression_gain: str
    relationship_change: str
    protected_reveals: list[str] = Field(min_length=2, max_length=8)


class ChapterDirection(BaseModel):
    sequence: int = Field(ge=1, le=20)
    title: str
    function: Literal["orient", "deepen", "attempt", "complicate", "partial_payoff"]
    focus_character: str
    location: str
    reader_orientation: str
    immediate_goal: str
    obstacle: str
    main_action: str
    information_gain: str
    relationship_movement: str
    immediate_consequence: str
    ending_beat: str


class OpeningWindow(BaseModel):
    """开篇 10 章阅读窗口。允许空字段——未补全时由用户选择让 AI 单独生成。"""

    title: str = ""
    chapter_range: list[int] = Field(default_factory=lambda: [1, 10], min_length=2, max_length=2)
    purpose: str = ""
    reader_anchor: str = ""
    local_goal: str = ""
    scope_boundary: str = ""
    ending_change: str = ""
    introduced_characters: list[str] = Field(default_factory=list, max_length=3)
    introduced_rules: list[str] = Field(default_factory=list, max_length=2)
    chapter_directions: list[ChapterDirection] = Field(default_factory=list, max_length=12)


class CreationFoundation(BaseModel):
    """故事根基。

    渐进式建模：核心、引擎、世界观、规模、第一卷、主角由 AI 一次生成。
    characters / stages / opening_window 在初次生成时可为空，由用户逐节补全。
    preflight 时若这些节仍为空，会给出明确提示而不是直接拒绝。
    """

    core: StoryCore
    engine: StoryEngine
    scale_plan: ScalePlan
    world: FoundationWorld
    protagonist: FoundationProtagonist
    creative_brief: list[FoundationBriefItem] = Field(default_factory=list, max_length=12)
    characters: list[FoundationCharacter] = Field(default_factory=list, max_length=4)
    stages: list[StoryStage] = Field(default_factory=list, max_length=12)
    first_volume: FirstVolume
    opening_window: OpeningWindow = Field(default_factory=lambda: _empty_opening_window())


def _empty_opening_window() -> dict[str, Any]:
    """未补全的开篇窗口占位：title/purpose 等空字符串，chapter_range [1,10]，chapter_directions 为空。"""
    return {
        "title": "",
        "chapter_range": [1, 10],
        "purpose": "",
        "reader_anchor": "",
        "local_goal": "",
        "scope_boundary": "",
        "ending_change": "",
        "introduced_characters": [],
        "introduced_rules": [],
        "chapter_directions": [],
    }


class CreationFoundationResponse(BaseModel):
    foundation: CreationFoundation
    method_cards: list[str] = Field(default_factory=list)


class FoundationSectionRequest(BaseModel):
    """按节补全请求：现有 foundation + 节名 + 上下文，只生成缺失的那一节。"""

    idea: str = Field(min_length=20, max_length=12_000)
    section: Literal[
        "creative_brief",  # AI 按题材动态决定作者需要确认的蓝图块
        "engine",          # 世界观 + 引擎
        "world",           # 单独再细化世界
        "scale_volume",    # 规模 + 第一卷
        "characters",      # 关键配角
        "stages",          # 全书阶段
        "opening_window",  # 前10章方向
    ]
    current: dict[str, Any] = Field(default_factory=dict)
    genre: str | None = Field(default=None, max_length=50)
    genres: list[str] = Field(default_factory=list, max_length=3)
    channel: Literal["男频", "女频", "不限"] = "不限"
    target_words: int = Field(default=1_000_000, ge=100_000, le=8_000_000)
    reader_wish: str | None = Field(default=None, max_length=2000)
    avoid_elements: str | None = Field(default=None, max_length=2000)
    style_reference: str | None = Field(default=None, max_length=6000)
    golden_finger_hint: str | None = Field(default=None, max_length=2000)


class FoundationSectionResponse(BaseModel):
    """返回该节补全结果。"""

    section: str
    patch: dict[str, Any] = Field(default_factory=dict)


class OpeningPilotRequest(BaseModel):
    foundation: CreationFoundation
    author_note: str | None = Field(default=None, max_length=3000)
    style_reference: str | None = Field(default=None, max_length=6000)
    creation_session_id: uuid.UUID | None = None


class SceneContract(BaseModel):
    viewpoint: str
    starting_state: str
    immediate_goal: str
    resistance: str
    action: str
    decision: str
    immediate_consequence: str
    changed_state: str
    next_promise: str
    scenes: list[dict[str, str]] = Field(min_length=1, max_length=8)


class OpeningPilotResponse(BaseModel):
    title: str
    content: str
    summary: str
    scene_contract: SceneContract
    method_cards: list[str] = Field(default_factory=list)


class ContinuationRequest(BaseModel):
    strategy: str = Field(pattern=r"^(faithful|accelerate|diverge)$")
    target_words: int = Field(default=1_000_000, ge=100_000, le=8_000_000)


class FanficRequest(BaseModel):
    fanfic_type: str = Field(
        pattern=r"^(new_protagonist|what_if|cp|ensemble|after_story|side_story|character_pov|au|immersive|fanfic_continuation)$"
    )
    seed_description: str = Field(min_length=2, max_length=2000)
    target_words: int = Field(default=300_000, ge=100_000, le=8_000_000)


class ImmersiveSessionCreate(BaseModel):
    work_id: uuid.UUID
    character_name: str = Field(min_length=1, max_length=200)
    experience_style: str = Field(default="action", pattern=r"^(action|romance|adventure|intrigue)$")


class ImmersiveSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    work_id: uuid.UUID
    character_name: str
    experience_style: str | None
    segments: list[Any]
    character_state: dict[str, Any]
    project_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ImmersiveChoiceRequest(BaseModel):
    choice_index: int = Field(ge=0, le=4)


class ImmersiveSegment(BaseModel):
    narrative: str
    choices: list[str]
    character_state: dict[str, Any]


class ReaderFeedbackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chapter_sequence: int
    source: str
    chase_score: int | None
    summary: str | None
    readers: list[Any]
    thrill_analysis: dict[str, Any]
    risk_points: list[Any]
    created_at: datetime


class HealthCheckResponse(BaseModel):
    overall_score: float
    pacing_verdict: str
    consistency_issues: list[str]
    improvement_suggestions: list[str]


UserRead.model_rebuild()
