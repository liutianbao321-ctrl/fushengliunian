import uuid
from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nickname: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    projects: Mapped[list["Project"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    genre: Mapped[str] = mapped_column(String(50), nullable=False)
    one_sentence: Mapped[str] = mapped_column(Text, nullable=False)
    protagonist_name: Mapped[str] = mapped_column(String(100), nullable=False)
    protagonist_gender: Mapped[str] = mapped_column(String(20), nullable=False)
    protagonist_personality: Mapped[str] = mapped_column(Text, nullable=False)
    target_words: Mapped[int] = mapped_column(Integer, default=1_000_000, nullable=False)
    total_chapters: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    current_chapter: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    style_profile: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    generation_state: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    creation_mode: Mapped[str] = mapped_column(String(20), default="inspired", nullable=False)
    channel: Mapped[str | None] = mapped_column(String(20))
    track: Mapped[str | None] = mapped_column(String(200))
    source_work_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("imported_works.id", ondelete="SET NULL", use_alter=True, name="fk_project_source_work")
    )
    # 蓝图域衔接：金手指设定与意图书（锁定字段），供大纲生成 prompt 注入
    golden_finger: Mapped[str] = mapped_column(Text, default="", nullable=False)
    intent_brief: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="projects")
    wiki_pages: Mapped[list["StoryWiki"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    outlines: Mapped[list["Outline"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    toc_nodes: Mapped[list["NovelToc"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    chapters: Mapped[list["Chapter"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    state_logs: Mapped[list["StateLog"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    temperatures: Mapped[list["EntityTemperature"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    foreshadowing_items: Mapped[list["Foreshadowing"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    knowledge_items: Mapped[list["CharacterKnowledge"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class CreationSession(Base):
    """Pre-project story-room state. A book is created only after this reaches PILOT_GENERATED."""

    __tablename__ = "creation_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    state: Mapped[str] = mapped_column(String(40), default="RAW_IDEA", nullable=False)
    input_payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    selected_direction: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    foundation: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    foundation_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (Index("ix_creation_sessions_user_updated", "user_id", "updated_at"),)


class CreationArtifact(Base):
    """Immutable versioned output exchanged by story-room roles."""

    __tablename__ = "creation_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("creation_sessions.id", ondelete="CASCADE"), nullable=False
    )
    artifact_type: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    parent_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("creation_artifacts.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("session_id", "artifact_type", "version", name="uq_creation_artifact_version"),
        Index("ix_creation_artifacts_session_type", "session_id", "artifact_type"),
    )


class CreationDecision(Base):
    """An explicit author choice made before a project exists."""

    __tablename__ = "creation_decisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("creation_sessions.id", ondelete="CASCADE"), nullable=False
    )
    decision_type: Mapped[str] = mapped_column(String(50), nullable=False)
    options: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    chosen_index: Mapped[int | None] = mapped_column(Integer)
    chosen_payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    user_note: Mapped[str | None] = mapped_column(Text)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ViabilityReview(Base):
    """Evidence-backed long-form preflight; no numeric self-score is trusted."""

    __tablename__ = "viability_reviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("creation_sessions.id", ondelete="CASCADE"), nullable=False
    )
    foundation_version: Mapped[int] = mapped_column(Integer, nullable=False)
    verdict: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    blocking_issues: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    warnings: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    author_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("session_id", "foundation_version", name="uq_viability_review_foundation"),
    )


class StoryWiki(Base):
    __tablename__ = "story_wiki"
    __table_args__ = (UniqueConstraint("project_id", "slug", name="uq_story_wiki_slug"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    wikilinks: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    last_updated_chapter: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_chapters: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list, nullable=False)
    visibility: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="generated", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="wiki_pages")


class Outline(Base):
    __tablename__ = "outlines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("outlines.id", ondelete="SET NULL"))
    level: Mapped[str] = mapped_column(String(10), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_sealed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    project: Mapped["Project"] = relationship(back_populates="outlines")


class NovelToc(Base):
    __tablename__ = "novel_toc"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("novel_toc.id", ondelete="SET NULL"))
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    characters: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    key_events: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    chapter_range_start: Mapped[int | None] = mapped_column(Integer)
    chapter_range_end: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="toc_nodes")


class Chapter(Base):
    __tablename__ = "chapters"
    __table_args__ = (UniqueConstraint("project_id", "chapter_sequence", name="uq_project_chapter_sequence"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    volume_sequence: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    chapter_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    quality_scores: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    beat_sheet: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    generation_log: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="chapters")


class StateLog(Base):
    __tablename__ = "state_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    dimension: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_name: Mapped[str] = mapped_column(String(200), nullable=False)
    field: Mapped[str | None] = mapped_column(String(100))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.9, nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="observer", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    project: Mapped["Project"] = relationship(back_populates="state_logs")


class EntityTemperature(Base):
    __tablename__ = "entity_temperature"
    __table_args__ = (UniqueConstraint("project_id", "entity_name", name="uq_project_entity_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    entity_name: Mapped[str] = mapped_column(String(200), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    temperature: Mapped[str] = mapped_column(String(10), default="hot", nullable=False)
    last_referenced_chapter: Mapped[int] = mapped_column(Integer, nullable=False)
    compressed_summary: Mapped[str | None] = mapped_column(Text)

    project: Mapped["Project"] = relationship(back_populates="temperatures")


class Foreshadowing(Base):
    __tablename__ = "foreshadowing"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    planted_chapter: Mapped[int] = mapped_column(Integer, nullable=False)
    target_chapter: Mapped[int | None] = mapped_column(Integer)
    resolved_chapter: Mapped[int | None] = mapped_column(Integer)
    importance: Mapped[str] = mapped_column(String(1), default="B", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    escalation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    related_characters: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    project: Mapped["Project"] = relationship(back_populates="foreshadowing_items")


class CharacterKnowledge(Base):
    __tablename__ = "character_knowledge"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    character_name: Mapped[str] = mapped_column(String(100), nullable=False)
    knowledge: Mapped[str] = mapped_column(Text, nullable=False)
    source_chapter: Mapped[int | None] = mapped_column(Integer)
    knowledge_type: Mapped[str] = mapped_column(String(20), default="knows", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    project: Mapped["Project"] = relationship(back_populates="knowledge_items")


class ChapterChunk(Base):
    __tablename__ = "chapter_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    imported_chapter_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("imported_chapters.id", ondelete="SET NULL", use_alter=True)
    )
    source: Mapped[str] = mapped_column(String(20), default="native", nullable=False)
    chapter_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    entities: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    arc_id: Mapped[str | None] = mapped_column(String(100))
    is_milestone: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class WritingKnowledgeDocument(Base):
    __tablename__ = "writing_knowledge_documents"
    __table_args__ = (
        UniqueConstraint("source_path", "source_sha256", name="uq_writing_knowledge_source_version"),
        Index("ix_writing_knowledge_document_status", "status", "category"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    source_format: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ready", nullable=False)
    outline: Mapped[list[dict]] = mapped_column(JSONB, default=list, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    chunks: Mapped[list["WritingKnowledgeChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class WritingKnowledgeChunk(Base):
    __tablename__ = "writing_knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_writing_knowledge_chunk"),
        Index("ix_writing_knowledge_chunk_tags", "tags", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("writing_knowledge_documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    heading_path: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    start_char: Mapped[int] = mapped_column(Integer, nullable=False)
    end_char: Mapped[int] = mapped_column(Integer, nullable=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    document: Mapped["WritingKnowledgeDocument"] = relationship(back_populates="chunks")


class WritingMethodCard(Base):
    __tablename__ = "writing_method_cards"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_writing_method_card_slug"),
        Index("ix_writing_method_card_tags", "tags", postgresql_using="gin"),
        Index("ix_writing_method_card_genre", "genre"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(240), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    principle: Mapped[str] = mapped_column(Text, nullable=False)
    when_to_use: Mapped[str] = mapped_column(Text, nullable=False)
    procedure: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    checks: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    anti_patterns: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    genre: Mapped[str | None] = mapped_column(String(50))
    wikilinks: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    source_chunk_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class SceneTemplate(Base):
    __tablename__ = "scene_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    scene_type: Mapped[str] = mapped_column(String(50), nullable=False)
    genre: Mapped[str | None] = mapped_column(String(50))
    tension_arc: Mapped[str] = mapped_column(Text, nullable=False)
    beats: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    pov_suggestion: Mapped[str] = mapped_column(Text, default="", nullable=False)
    entry_condition: Mapped[str] = mapped_column(Text, default="", nullable=False)
    exit_condition: Mapped[str] = mapped_column(Text, default="", nullable=False)
    emotional_shift: Mapped[str] = mapped_column(Text, default="", nullable=False)
    anti_patterns: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class PlotDevice(Base):
    __tablename__ = "plot_devices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    device_type: Mapped[str] = mapped_column(String(50), nullable=False)
    genre: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    setup: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    escalation: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    payoff: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    common_mistakes: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class StyleReference(Base):
    __tablename__ = "style_references"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    style_profile: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    sample_passages: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class GenerationRun(Base):
    __tablename__ = "generation_runs"
    __table_args__ = (
        UniqueConstraint("project_id", "client_request_id", name="uq_generation_run_request"),
        Index("ix_generation_run_project_status", "project_id", "status"),
        Index(
            "uq_generation_run_active_semantic",
            "project_id",
            "semantic_key",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running', 'pausing')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    client_request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    semantic_key: Mapped[str] = mapped_column(String(160), nullable=False)
    claim_token: Mapped[str | None] = mapped_column(String(64))
    deerflow_thread_id: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    current_node: Mapped[str | None] = mapped_column(String(50))
    attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    input_revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    result_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "chapter_revisions.id", ondelete="SET NULL", use_alter=True, name="fk_generation_run_result_revision"
        )
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class GenerationNodeRun(Base):
    __tablename__ = "generation_node_runs"
    __table_args__ = (
        UniqueConstraint("run_id", "node_name", "attempt", name="uq_generation_node_attempt"),
        Index("ix_generation_node_run_status", "run_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("generation_runs.id", ondelete="CASCADE"), nullable=False)
    node_name: Mapped[str] = mapped_column(String(50), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False)
    input_payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    output_payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_hash: Mapped[str | None] = mapped_column(String(64))
    model_name: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChapterRevision(Base):
    __tablename__ = "chapter_revisions"
    __table_args__ = (
        UniqueConstraint("project_id", "chapter_sequence", "revision", name="uq_chapter_revision"),
        UniqueConstraint("project_id", "chapter_sequence", "body_sha256", name="uq_chapter_body_revision"),
        Index("ix_chapter_revision_status", "project_id", "chapter_sequence", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    generation_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("generation_runs.id", ondelete="SET NULL"))
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("chapter_revisions.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), default="candidate", nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    beat_sheet: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    changes: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    quality_scores: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    body_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StateEvent(Base):
    __tablename__ = "state_events"
    __table_args__ = (
        UniqueConstraint("project_id", "event_key", name="uq_state_event_key"),
        Index("ix_state_event_entity", "project_id", "entity_type", "entity_key", "field"),
        Index("ix_state_event_revision", "project_id", "chapter_sequence", "chapter_revision"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_revision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chapter_revisions.id", ondelete="CASCADE"), nullable=False
    )
    chapter_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    chapter_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    event_key: Mapped[str] = mapped_column(String(180), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    operation: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_key: Mapped[str] = mapped_column(String(200), nullable=False)
    field: Mapped[str] = mapped_column(String(100), nullable=False)
    old_value: Mapped[dict | None] = mapped_column(JSONB)
    new_value: Mapped[dict | None] = mapped_column(JSONB)
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    correction_of_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("state_events.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class CurrentState(Base):
    __tablename__ = "current_states"
    __table_args__ = (
        UniqueConstraint("project_id", "entity_type", "entity_key", "field", name="uq_current_state_field"),
        Index("ix_current_state_temperature", "project_id", "temperature", "last_chapter_sequence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_key: Mapped[str] = mapped_column(String(200), nullable=False)
    field: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("state_events.id", ondelete="RESTRICT"), nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    temperature: Mapped[str] = mapped_column(String(10), default="hot", nullable=False)
    last_chapter_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class WikiRevision(Base):
    __tablename__ = "wiki_revisions"
    __table_args__ = (
        UniqueConstraint("page_id", "revision", name="uq_wiki_page_revision"),
        Index("ix_wiki_revision_source", "project_id", "chapter_sequence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    page_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("story_wiki.id", ondelete="CASCADE"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    chapter_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chapter_revisions.id", ondelete="SET NULL")
    )
    chapter_sequence: Mapped[int | None] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    wikilinks: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    sources: Mapped[list[dict]] = mapped_column(JSONB, default=list, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class IndexRun(Base):
    __tablename__ = "index_runs"
    __table_args__ = (
        UniqueConstraint("project_id", "index_kind", "target_revision", name="uq_index_target_revision"),
        Index("ix_index_run_status", "project_id", "index_kind", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    index_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    target_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    built_revision: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    claim_token: Mapped[str | None] = mapped_column(String(64))
    attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    artifact: Mapped[bytes | None] = mapped_column(LargeBinary)
    artifact_sha256: Mapped[str | None] = mapped_column(String(64))
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QualityGateResult(Base):
    __tablename__ = "quality_gate_results"
    __table_args__ = (
        UniqueConstraint("chapter_revision_id", "gate_name", "attempt", name="uq_quality_gate_attempt"),
        Index("ix_quality_gate_revision", "chapter_revision_id", "passed"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chapter_revision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chapter_revisions.id", ondelete="CASCADE"), nullable=False
    )
    gate_name: Mapped[str] = mapped_column(String(50), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    blocking: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ProjectEvent(Base):
    __tablename__ = "project_events"
    __table_args__ = (
        UniqueConstraint("project_id", "sequence", name="uq_project_event_sequence"),
        Index("ix_project_event_cursor", "project_id", "sequence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("generation_runs.id", ondelete="SET NULL"))
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        UniqueConstraint("event_key", name="uq_outbox_event_key"),
        Index("ix_outbox_pending", "published_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_key: Mapped[str] = mapped_column(String(200), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(50), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ImportedWork(Base):
    __tablename__ = "imported_works"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    author: Mapped[str | None] = mapped_column(String(200))
    source_platform: Mapped[str | None] = mapped_column(String(100))
    total_chapters: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_words: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    genre: Mapped[str | None] = mapped_column(String(50))
    sub_genre: Mapped[str | None] = mapped_column(String(100))
    analysis_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    analysis_progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    analysis_attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    analysis_claim_token: Mapped[str | None] = mapped_column(String(64))
    analysis_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    analysis_error: Mapped[str | None] = mapped_column(Text)
    breakpoint_analysis: Mapped[dict | None] = mapped_column(JSONB)
    style_profile: Mapped[dict | None] = mapped_column(JSONB)
    extracted_data: Mapped[dict | None] = mapped_column(JSONB)
    rights_status: Mapped[str] = mapped_column(String(20), default="private", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    imported_chapters: Mapped[list["ImportedChapter"]] = relationship(
        back_populates="work", cascade="all, delete-orphan"
    )


class ImportedChapter(Base):
    __tablename__ = "imported_chapters"
    __table_args__ = (UniqueConstraint("work_id", "chapter_sequence", name="uq_imported_chapter_seq"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    work_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("imported_works.id", ondelete="CASCADE"), nullable=False)
    chapter_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    analysis_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)

    work: Mapped["ImportedWork"] = relationship(back_populates="imported_chapters")


class MarketTrack(Base):
    __tablename__ = "market_tracks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    track_name: Mapped[str] = mapped_column(String(200), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    genre: Mapped[str] = mapped_column(String(50), nullable=False)
    sub_genre: Mapped[str | None] = mapped_column(String(100))
    heat: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    heat_trend: Mapped[str] = mapped_column(String(20), default="stable", nullable=False)
    competition: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), default="beginner", nullable=False)
    monetization: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    benchmark_works: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    taste_tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    golden_formula: Mapped[str | None] = mapped_column(Text)
    platform_tips: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class TropeLibrary(Base):
    __tablename__ = "trope_library"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trope_name: Mapped[str] = mapped_column(String(200), nullable=False)
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    hook_template: Mapped[str | None] = mapped_column(Text)
    pacing_formula: Mapped[str | None] = mapped_column(Text)
    source_works: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    channel: Mapped[str | None] = mapped_column(String(20))
    genre: Mapped[str | None] = mapped_column(String(50))
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)


class HotNovel(Base):
    __tablename__ = "hot_novels"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    author: Mapped[str | None] = mapped_column(String(200))
    platform: Mapped[str | None] = mapped_column(String(100))
    genre: Mapped[str | None] = mapped_column(String(50))
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    synopsis: Mapped[str | None] = mapped_column(Text)
    rank_position: Mapped[int | None] = mapped_column(Integer)
    public_stats: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    reviews_summary: Mapped[str | None] = mapped_column(Text)
    sample_hook: Mapped[str | None] = mapped_column(Text)
    track_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("market_tracks.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class ReaderFeedback(Base):
    __tablename__ = "reader_feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="ai", nullable=False)
    chase_score: Mapped[int | None] = mapped_column(Integer)
    summary: Mapped[str | None] = mapped_column(Text)
    readers: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    thrill_analysis: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    risk_points: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ImmersiveSession(Base):
    __tablename__ = "immersive_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    work_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("imported_works.id", ondelete="CASCADE"), nullable=False)
    character_name: Mapped[str] = mapped_column(String(200), nullable=False)
    experience_style: Mapped[str | None] = mapped_column(String(20))
    segments: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    character_state: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class OutlineNode(Base):
    """六层大纲树（L0 点子 / L1 立意 / L2 设定 / L3 主线 / L4 事件段 / L5 章纲）。"""

    __tablename__ = "outline_nodes"
    __table_args__ = (Index("ix_outline_node_project_layer_seq", "project_id", "layer", "seq"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    layer: Mapped[str] = mapped_column(String(10), nullable=False)  # L0-L5
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("outline_nodes.id", ondelete="SET NULL"))
    seq: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    title: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)  # draft/confirmed/locked
    meta: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class BeatCard(Base):
    """章内情节构思卡（L6 Beat 卡），每章唯一一张。"""

    __tablename__ = "beat_cards"
    __table_args__ = (UniqueConstraint("chapter_id", name="uq_beat_card_chapter"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chapter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False)
    fields: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)  # 13 个字段
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)  # draft/confirmed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class PlotLedger(Base):
    """伏笔登记表（一等公民）：埋设/提及/回收/载体/状态。"""

    __tablename__ = "plot_ledger"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # person/item/dialog
    description: Mapped[str] = mapped_column(Text, nullable=False)
    planted_chapter: Mapped[int] = mapped_column(Integer, nullable=False)
    mentioned_chapters: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list, nullable=False)
    due_chapter: Mapped[int | None] = mapped_column(Integer)
    resolved_chapter: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)  # open/reminded/closed/expired
    is_yy: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    origin_foreshadowing_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("foreshadowing.id", ondelete="SET NULL", use_alter=True, name="fk_plot_ledger_origin_fs"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class PacingConfig(Base):
    """节奏引擎参数：每本书可调。"""

    __tablename__ = "pacing_configs"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    minor_climax_cycle: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    major_climax_cycle: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    sweet_density: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    mode: Mapped[str] = mapped_column(String(20), default="ladder", nullable=False)  # ladder/ecg
    opening_mode: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class CraftRule(Base):
    """负面清单三级规则（A 阻塞 / B 警告 / C 风格提示）。"""

    __tablename__ = "craft_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    level: Mapped[str] = mapped_column(String(10), nullable=False)  # A/B/C
    rule_text: Mapped[str] = mapped_column(Text, nullable=False)
    detect_method: Mapped[str] = mapped_column(String(20), default="llm_judge", nullable=False)  # regex/llm_judge
    scope: Mapped[str] = mapped_column(String(20), default="global", nullable=False)  # global/genre/opening
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class BlueprintJob(Base):
    """蓝图域长任务（大纲生成 / Beat 卡生成）的耐久任务记录。"""

    __tablename__ = "blueprint_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)  # outline_generate / beat_card_generate
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="queued", nullable=False
    )  # queued/running/succeeded/failed
    result: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class SummaryChain(Base):
    """滚动摘要链 — 每章发布时写入，供 LLM 上下文查询最近 N 章的情节脉络。

    - chapter_summary: 当前章的 300 字摘要
    - rolling_summary: 最近 5-10 章的 800 字滚动摘要（每次重新生成）
    - volume_summary: 当前卷的 1200 字卷摘要（每卷完成时写入，之后不再变化）
    """

    __tablename__ = "summary_chains"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    chapter_summary: Mapped[str] = mapped_column(Text, nullable=False)
    rolling_summary: Mapped[str] = mapped_column(Text, nullable=False)
    volume_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("project_id", "chapter_sequence", name="uq_summary_chain_chapter"),)


class WritingCharter(Base):
    """创作宪章 — 作者在项目启动时确立的约束性规则。"""

    __tablename__ = "writing_charters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    narrative_focus: Mapped[str] = mapped_column(Text, default="", nullable=False)
    red_lines: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    mandates: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    target_readers: Mapped[str] = mapped_column(Text, default="", nullable=False)
    tone_reference: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (UniqueConstraint("project_id", name="uq_writing_charter_project"),)


class TasteProfile(Base):
    """品味档案 — 记录用户偏好，反馈飞轮蒸馏输出。"""

    __tablename__ = "taste_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    preferred_genres: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    preferred_pacing: Mapped[str] = mapped_column(String(20), default="mixed", nullable=False)
    preferred_tension: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    dialogue_preference: Mapped[str] = mapped_column(String(20), default="natural", nullable=False)
    description_density: Mapped[str] = mapped_column(String(20), default="moderate", nullable=False)
    avoid_patterns: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    favorite_patterns: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    distilled_from: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (UniqueConstraint("user_id", name="uq_taste_profile_user"),)


class StyleExemplar(Base):
    """范例库 — 用户认可的优质片段，供风格蒸馏注入。"""

    __tablename__ = "style_exemplars"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="user_selection", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class FeedbackEvent(Base):
    """反馈事件 — 用户改稿/选标题/评分等行为记录。"""

    __tablename__ = "feedback_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_sequence: Mapped[int | None] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    distilled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (Index("ix_feedback_events_pending", "project_id", "distilled"),)


class DecisionPoint(Base):
    """决策记忆 — AI 出选项、用户做选择，记录选择偏好。"""

    __tablename__ = "decision_points"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_sequence: Mapped[int | None] = mapped_column(Integer)
    decision_type: Mapped[str] = mapped_column(String(50), nullable=False)
    options: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    chosen_index: Mapped[int | None] = mapped_column(Integer)
    user_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class CharacterVoiceCard(Base):
    """人物语感卡 — 记录每个角色的说话习惯和辨识度特征。"""

    __tablename__ = "character_voice_cards"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    character_name: Mapped[str] = mapped_column(String(200), nullable=False)
    catch_phrases: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    sentence_patterns: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    avoid_topics: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    subtext_patterns: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    emotional_range: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    last_updated_chapter: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (UniqueConstraint("project_id", "character_name", name="uq_voice_card_character"),)


class ControlSetting(Base):
    """三挡控制 — 自动/副驾/手动，粒度到章。"""

    __tablename__ = "control_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), default="copilot", nullable=False)
    gate_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    brief_duration_seconds: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    auto_publish: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    chapter_overrides: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (UniqueConstraint("project_id", name="uq_control_setting_project"),)


class IntentAnchor(Base):
    """作者明确确认的少量硬约束；AI 可扩写但不得静默改写。"""

    __tablename__ = "intent_anchors"
    __table_args__ = (Index("ix_intent_anchor_project_kind", "project_id", "kind"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(30), default="interview", nullable=False)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    locked: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class ProjectSeed(Base):
    """建项时四包资产的可追溯快照；修改时追加版本而不是覆盖历史。"""

    __tablename__ = "project_seeds"
    __table_args__ = (UniqueConstraint("project_id", "version", name="uq_project_seed_version"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    source_work_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("imported_works.id", ondelete="SET NULL")
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="confirmed", nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class WorkCodexEntry(Base):
    """导入作品的事实、叙事、风格和技法四层知识条目。"""

    __tablename__ = "work_codex_entries"
    __table_args__ = (
        Index("ix_work_codex_layer_kind", "imported_work_id", "layer", "kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    imported_work_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("imported_works.id", ondelete="CASCADE"), nullable=False
    )
    layer: Mapped[str] = mapped_column(String(20), nullable=False)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.8, nullable=False)
    user_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_chapter_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class NarrativeDna(Base):
    """可用于续写或仿写的统计化叙事方法，不包含原作事实。"""

    __tablename__ = "narrative_dna"
    __table_args__ = (UniqueConstraint("imported_work_id", name="uq_narrative_dna_work"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    imported_work_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("imported_works.id", ondelete="CASCADE"), nullable=False
    )
    hook_patterns: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    pacing_stats: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    pov_habits: Mapped[str] = mapped_column(Text, default="", nullable=False)
    escalation_curve: Mapped[str] = mapped_column(Text, default="", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class IntentBrief(Base):
    """意图简报 — 每章开写前的用户可读摘要和裁决点。"""

    __tablename__ = "intent_briefs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    why_this_chapter: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    scene_entities: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    character_states: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    due_foreshadowing: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    writing_contract: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    user_verdict: Mapped[str | None] = mapped_column(String(20))
    user_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("project_id", "chapter_sequence", name="uq_intent_brief_chapter"),)
