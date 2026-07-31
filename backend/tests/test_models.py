from pathlib import Path

from app.models import Base

CONTROL_DOMAIN_TABLES = {
    "taste_profiles",
    "style_exemplars",
    "feedback_events",
    "decision_points",
    "character_voice_cards",
    "control_settings",
    "intent_briefs",
}

CREATION_STUDIO_TABLES = {
    "creation_sessions",
    "creation_artifacts",
    "creation_decisions",
    "viability_reviews",
}


def test_production_tables_are_registered() -> None:
    required = {
        "generation_runs",
        "generation_node_runs",
        "chapter_revisions",
        "state_events",
        "current_states",
        "wiki_revisions",
        "index_runs",
        "quality_gate_results",
        "project_events",
        "outbox_events",
        "intent_anchors",
        "project_seeds",
        "work_codex_entries",
        "narrative_dna",
        *CONTROL_DOMAIN_TABLES,
        *CREATION_STUDIO_TABLES,
    }
    assert required.issubset(Base.metadata.tables)


def test_generation_and_revision_uniqueness_contracts_exist() -> None:
    run_constraints = {constraint.name for constraint in Base.metadata.tables["generation_runs"].constraints}
    revision_constraints = {constraint.name for constraint in Base.metadata.tables["chapter_revisions"].constraints}
    assert "uq_generation_run_request" in run_constraints
    assert "uq_chapter_revision" in revision_constraints
    assert "uq_chapter_body_revision" in revision_constraints


def test_durable_worker_lease_columns_exist() -> None:
    generation_columns = Base.metadata.tables["generation_runs"].columns
    index_columns = Base.metadata.tables["index_runs"].columns
    import_columns = Base.metadata.tables["imported_works"].columns
    assert {"claim_token", "heartbeat_at", "attempt"}.issubset(generation_columns.keys())
    assert {"claim_token", "heartbeat_at", "attempt", "started_at"}.issubset(index_columns.keys())
    assert {"analysis_claim_token", "analysis_heartbeat_at", "analysis_attempt", "analysis_error"}.issubset(
        import_columns.keys()
    )


def test_imported_narrative_chunks_are_traceable() -> None:
    columns = Base.metadata.tables["chapter_chunks"].columns
    assert {"source", "imported_chapter_id"}.issubset(columns.keys())


def test_control_domain_tables_are_backed_by_latest_migration() -> None:
    migration = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "20260729_0011_complete_control_domain.py"
    ).read_text(encoding="utf-8")
    assert 'revision: str = "0011"' in migration
    assert 'down_revision: str | None = "0010"' in migration
    for table_name in CONTROL_DOMAIN_TABLES:
        assert f'op.create_table(\n            "{table_name}"' in migration


def test_content_censorship_rule_is_removed_by_latest_migration() -> None:
    migration = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "20260729_0012_remove_content_censorship.py"
    ).read_text(encoding="utf-8")
    assert 'revision: str = "0012"' in migration
    assert 'down_revision: str | None = "0011"' in migration
    assert "DELETE FROM craft_rules" in migration


def test_creation_studio_tables_are_backed_by_latest_migration() -> None:
    migration = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "20260731_0013_creation_studio.py"
    ).read_text(encoding="utf-8")
    assert 'revision: str = "0013"' in migration
    assert 'down_revision: str | None = "0012"' in migration
    for table_name in CREATION_STUDIO_TABLES:
        assert f'"{table_name}"' in migration
