"""Add the source-grounded writing knowledge base.

Revision ID: 20260723_0003
Revises: 20260721_0002
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260723_0003"
down_revision = "20260721_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # See 0002: a fresh install may already have tables created by the dynamic baseline.
    if "writing_knowledge_documents" in sa.inspect(op.get_bind()).get_table_names():
        _create_search_indexes()
        return
    op.create_table(
        "writing_knowledge_documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("source_format", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("outline", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_path", "source_sha256", name="uq_writing_knowledge_source_version"),
    )
    op.create_index(
        "ix_writing_knowledge_document_status",
        "writing_knowledge_documents",
        ["status", "category"],
    )
    op.create_table(
        "writing_knowledge_chunks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("heading_path", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("start_char", sa.Integer(), nullable=False),
        sa.Column("end_char", sa.Integer(), nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["writing_knowledge_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_writing_knowledge_chunk"),
    )
    op.create_table(
        "writing_method_cards",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.String(length=240), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("principle", sa.Text(), nullable=False),
        sa.Column("when_to_use", sa.Text(), nullable=False),
        sa.Column("procedure", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("checks", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("anti_patterns", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("wikilinks", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("source_chunk_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_writing_method_card_slug"),
    )
    op.create_index("ix_writing_knowledge_chunk_tags", "writing_knowledge_chunks", ["tags"], postgresql_using="gin")
    op.create_index("ix_writing_method_card_tags", "writing_method_cards", ["tags"], postgresql_using="gin")
    _create_search_indexes()


def _create_search_indexes() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_writing_knowledge_chunks_fts ON writing_knowledge_chunks "
        "USING gin (to_tsvector('simple', content))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_writing_knowledge_chunks_embedding ON writing_knowledge_chunks "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_writing_method_cards_fts ON writing_method_cards "
        "USING gin (to_tsvector('simple', principle || ' ' || when_to_use))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_writing_method_cards_embedding ON writing_method_cards "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.drop_table("writing_method_cards")
    op.drop_table("writing_knowledge_chunks")
    op.drop_index("ix_writing_knowledge_document_status", table_name="writing_knowledge_documents")
    op.drop_table("writing_knowledge_documents")
