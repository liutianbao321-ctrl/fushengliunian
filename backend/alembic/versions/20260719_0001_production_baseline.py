"""Production schema baseline.

Revision ID: 20260719_0001
Revises:
"""

from alembic import op
from app.models import Base

revision = "20260719_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    # This is the immutable baseline for the repository's pre-Alembic schema.
    # Every subsequent schema change must use explicit Alembic operations.
    Base.metadata.create_all(bind=bind, checkfirst=True)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON chapter_chunks "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_chunks_fts ON chapter_chunks USING gin (to_tsvector('simple', content))")
    op.execute("CREATE INDEX IF NOT EXISTS idx_chunks_entities ON chapter_chunks USING gin (entities)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_wiki_wikilinks ON story_wiki USING gin (wikilinks)")


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, checkfirst=True)
