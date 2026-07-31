from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.worldbuilder import build_project_bootstrap, build_volume_anchors, estimate_volume_count
from app.models import (
    BeatCard,
    Chapter,
    ControlSetting,
    IntentAnchor,
    NovelToc,
    Outline,
    OutlineNode,
    Project,
    ProjectSeed,
    StoryWiki,
    WritingCharter,
)
from app.schemas import ProjectCreate


def scene_contract_to_chapter_plan(
    scene_contract: dict,
    *,
    title: str,
    protagonist: str,
) -> dict:
    """Translate an accepted opening scene contract into the canonical beat-sheet shape."""
    scenes = scene_contract.get("scenes") if isinstance(scene_contract, dict) else []
    beats: list[dict] = []
    characters = [protagonist]
    for index, scene in enumerate(scenes if isinstance(scenes, list) else []):
        if not isinstance(scene, dict):
            continue
        present = scene.get("present_characters") or scene.get("characters") or []
        if isinstance(present, str):
            present = [item.strip() for item in present.replace("，", "、").split("、") if item.strip()]
        elif not isinstance(present, list):
            present = []
        characters.extend(str(item).strip() for item in present if str(item).strip())
        action = str(scene.get("action_and_response") or scene.get("action") or "").strip()
        consequence = str(scene.get("consequence") or scene.get("outcome") or "").strip()
        perception = str(scene.get("perception") or "").strip()
        event_parts = [item for item in (perception, action, consequence) if item]
        if not event_parts:
            continue
        beats.append(
            {
                "segment": str(scene.get("segment") or f"场景 {index + 1}"),
                "location": str(scene.get("place") or scene.get("location") or "开篇地点"),
                "characters": list(dict.fromkeys([str(item) for item in present])),
                "event": "；".join(event_parts),
                "obstacle": str(scene.get("obstacle") or scene_contract.get("resistance") or "眼前阻力仍在"),
                "outcome": consequence or action,
            }
        )
    return {
        "title_candidates": [title],
        "pov_character": str(scene_contract.get("viewpoint") or protagonist),
        "reader_experience": str(scene_contract.get("reader_orientation") or scene_contract.get("starting_state") or "跟随主角进入眼前处境"),
        "goal": str(scene_contract.get("immediate_goal") or "完成眼前目标"),
        "conflict": str(scene_contract.get("resistance") or "眼前目标受到阻碍"),
        "characters": list(dict.fromkeys(item for item in characters if item)),
        "opening": {
            "situation": str(scene_contract.get("starting_state") or "故事开始"),
            "pressure": str(scene_contract.get("resistance") or "异常打断正常状态"),
            "first_action": str(scene_contract.get("action") or scene_contract.get("decision") or "主角开始应对"),
        },
        "beats": beats[:5],
        "hook": str(scene_contract.get("next_promise") or scene_contract.get("immediate_consequence") or "眼前后果仍待处理"),
        "ending_image": str(scene_contract.get("changed_state") or scene_contract.get("immediate_consequence") or "局面发生变化"),
        "must_avoid": ["提前完成后续章节任务", "脱离当前视角解释世界设定"],
        "scene_contract": scene_contract,
    }


async def seed_new_project(db: AsyncSession, project: Project, payload: ProjectCreate) -> Project:
    bootstrap = build_project_bootstrap(payload)
    project.total_chapters = bootstrap.generation_state["estimated_total_chapters"]
    project.style_profile = bootstrap.style_profile
    project.generation_state = bootstrap.generation_state

    for page in bootstrap.wiki_pages:
        db.add(
            StoryWiki(
                project_id=project.id,
                slug=page["slug"],
                category=page["category"],
                title=page["title"],
                content=page["content"],
                aliases=page["aliases"],
                wikilinks=page["wikilinks"],
                visibility=page["visibility"],
            )
        )
    book_outline_data = next(item for item in bootstrap.outlines if item["level"] == "book")
    book_outline = Outline(project_id=project.id, **book_outline_data)
    db.add(book_outline)
    await db.flush()
    volume_outlines: list[Outline] = []
    for item in [value for value in bootstrap.outlines if value["level"] == "volume"]:
        volume = Outline(project_id=project.id, parent_id=book_outline.id, **item)
        db.add(volume)
        volume_outlines.append(volume)
    await db.flush()
    for item in [value for value in bootstrap.outlines if value["level"] == "chapter"]:
        parent = next(
            volume
            for volume in volume_outlines
            if volume.content["chapter_range"][0] <= item["sequence"] <= volume.content["chapter_range"][1]
        )
        db.add(Outline(project_id=project.id, parent_id=parent.id, **item))

    # 新蓝图域是写作上下文的主读取模型。建项时同步建立 L3-L5，避免新书只有旧大纲可看。
    book_node = OutlineNode(
        project_id=project.id,
        layer="L3",
        seq=1,
        title=book_outline.title,
        body=str(book_outline.content.get("goal") or project.one_sentence),
        status="confirmed",
        meta=book_outline.content,
    )
    db.add(book_node)
    await db.flush()
    volume_nodes: dict[int, OutlineNode] = {}
    for volume in volume_outlines:
        node = OutlineNode(
            project_id=project.id,
            parent_id=book_node.id,
            layer="L4",
            seq=volume.sequence,
            title=volume.title,
            body=str(volume.content.get("goal") or ""),
            status="confirmed" if volume.sequence == 1 else "draft",
            meta=volume.content,
        )
        db.add(node)
        volume_nodes[volume.sequence] = node
    await db.flush()
    for item in [value for value in bootstrap.outlines if value["level"] == "chapter"]:
        parent_sequence = next(
            volume.sequence
            for volume in volume_outlines
            if volume.content["chapter_range"][0] <= item["sequence"] <= volume.content["chapter_range"][1]
        )
        db.add(
            OutlineNode(
                project_id=project.id,
                parent_id=volume_nodes[parent_sequence].id,
                layer="L5",
                seq=item["sequence"],
                title=item["title"],
                body=str(item["content"].get("goal") or ""),
                status="confirmed" if item["sequence"] == 1 else "draft",
                meta=item["content"],
            )
        )

    book_toc_data = next(item for item in bootstrap.toc_nodes if item["level"] == "book")
    book_toc = NovelToc(project_id=project.id, **book_toc_data)
    db.add(book_toc)
    await db.flush()
    volume_tocs: list[NovelToc] = []
    for item in [value for value in bootstrap.toc_nodes if value["level"] == "volume"]:
        volume = NovelToc(project_id=project.id, parent_id=book_toc.id, **item)
        db.add(volume)
        volume_tocs.append(volume)
    await db.flush()
    for item in [value for value in bootstrap.toc_nodes if value["level"] == "chapter"]:
        parent = next(
            volume
            for volume in volume_tocs
            if volume.chapter_range_start <= item["sequence"] <= volume.chapter_range_end
        )
        db.add(NovelToc(project_id=project.id, parent_id=parent.id, **item))
    seeded_chapters: dict[int, Chapter] = {}
    for chapter_data in bootstrap.chapters:
        chapter = Chapter(
            project_id=project.id,
            volume_sequence=chapter_data["volume_sequence"],
            chapter_sequence=chapter_data["chapter_sequence"],
            title=chapter_data["title"],
            summary=chapter_data["summary"],
            status=chapter_data["status"],
        )
        db.add(chapter)
        seeded_chapters[chapter.chapter_sequence] = chapter

    pilot = payload.opening_pilot
    first_chapter = seeded_chapters.get(1)
    if pilot is not None and first_chapter is not None:
        chapter_plan = scene_contract_to_chapter_plan(
            pilot.scene_contract,
            title=pilot.title.strip(),
            protagonist=payload.protagonist_name,
        )
        first_chapter.title = pilot.title.strip()
        first_chapter.content = pilot.content.strip()
        first_chapter.summary = pilot.summary.strip()
        first_chapter.word_count = len("".join(first_chapter.content.split()))
        first_chapter.beat_sheet = chapter_plan
        first_chapter.generation_log = {"source": "creation_v2_pilot", "accepted_by_author": True}
        first_chapter.status = "draft"
        await db.flush()
        db.add(BeatCard(chapter_id=first_chapter.id, fields=chapter_plan, status="confirmed"))

        first_volume_outline = next((item for item in volume_outlines if item.sequence == 1), None)
        db.add(
            Outline(
                project_id=project.id,
                parent_id=first_volume_outline.id if first_volume_outline else None,
                level="chapter",
                sequence=1,
                title=first_chapter.title,
                content=chapter_plan,
                is_sealed=False,
            )
        )
        first_volume_toc = next((item for item in volume_tocs if item.sequence == 1), None)
        db.add(
            NovelToc(
                project_id=project.id,
                parent_id=first_volume_toc.id if first_volume_toc else None,
                level="chapter",
                sequence=1,
                title=first_chapter.title,
                summary=first_chapter.summary,
                characters=[payload.protagonist_name],
                key_events=[pilot.scene_contract.get("changed_state", "")],
                chapter_range_start=1,
                chapter_range_end=1,
            )
        )

    profile = payload.planning_profile if isinstance(payload.planning_profile, dict) else {}
    constitution = profile.get("author_constitution") if isinstance(profile.get("author_constitution"), dict) else {}
    core = profile.get("creation_v2", {}).get("core", {}) if isinstance(profile.get("creation_v2"), dict) else {}
    red_lines = [str(constitution.get("non_negotiables") or "").strip()]
    red_lines = [item for item in red_lines if item]
    mandates = [
        str(constitution.get("reader_promise") or core.get("reader_promise") or "").strip(),
        str(core.get("ending_direction") or "").strip(),
    ]
    mandates = [item for item in mandates if item]
    db.add(
        WritingCharter(
            project_id=project.id,
            narrative_focus=str(core.get("emotional_core") or project.one_sentence),
            red_lines=red_lines,
            mandates=mandates,
            target_readers=str(constitution.get("reader_promise") or ""),
            tone_reference=str(profile.get("writing_style", {}).get("description_effective") or ""),
        )
    )
    anchor_values = {
        "motivation": constitution.get("why_write") or (payload.intent_brief or {}).get("idea"),
        "emotion": core.get("emotional_core"),
        "ending": core.get("ending_direction"),
        "reader_promise": constitution.get("reader_promise") or core.get("reader_promise"),
        "red_line": constitution.get("non_negotiables"),
    }
    for kind, content in anchor_values.items():
        if str(content or "").strip():
            db.add(
                IntentAnchor(
                    project_id=project.id,
                    kind=kind,
                    content=str(content).strip(),
                    source="interview" if payload.creation_mode in {"inspired", "guided", "lazy"} else "import",
                    confirmed=True,
                    locked=True,
                )
            )
    db.add(ControlSetting(project_id=project.id, mode="copilot", gate_enabled=True, auto_publish=False))
    db.add(
        ProjectSeed(
            project_id=project.id,
            source=payload.creation_mode,
            source_work_id=payload.source_work_id,
            snapshot={
                "heart": {"constitution": constitution, "intent_anchors": anchor_values},
                "facts": {"world": profile.get("world_engine", {}), "characters": profile.get("characters", [])},
                "blueprint": profile.get("book_blueprint", {}),
                "narrative_assets": {"opening_pilot": pilot.model_dump() if pilot else None},
            },
        )
    )

    await db.flush()
    return project


async def ensure_blank_chapter(db: AsyncSession, project: Project, sequence: int) -> Chapter:
    chapter = await db.scalar(
        select(Chapter).where(Chapter.project_id == project.id, Chapter.chapter_sequence == sequence)
    )
    if chapter:
        return chapter
    volumes = list(
        (
            await db.scalars(
                select(Outline).where(Outline.project_id == project.id, Outline.level == "volume")
            )
        ).all()
    )
    volume_outline = next(
        (
            item
            for item in volumes
            if (item.content.get("chapter_range") or [0, -1])[0]
            <= sequence
            <= (item.content.get("chapter_range") or [0, -1])[1]
        ),
        None,
    )
    chapter = Chapter(
        project_id=project.id,
        volume_sequence=volume_outline.sequence if volume_outline else 1,
        chapter_sequence=sequence,
        title=f"第{sequence}章",
        summary="",
        status="unplanned",
    )
    db.add(chapter)
    await db.flush()
    return chapter


async def upgrade_project_to_volume_tree(db: AsyncSession, project: Project) -> list[Outline]:
    """把旧的单卷项目原地升级为多卷锚点；不改正文、不删用户大纲。"""
    outlines = list(
        (
            await db.scalars(
                select(Outline).where(Outline.project_id == project.id).order_by(Outline.sequence.asc())
            )
        ).all()
    )
    volumes = [item for item in outlines if item.level == "volume"]
    if len(volumes) > 1:
        return volumes
    book = next((item for item in outlines if item.level == "book"), None)
    if book is None:
        raise ValueError("项目缺少全书大纲")
    volume_count = estimate_volume_count(project.total_chapters)
    blueprint = (
        project.style_profile.get("creation_blueprint", {})
        if isinstance(project.style_profile, dict)
        else {}
    )
    anchors = build_volume_anchors(project.total_chapters, volume_count, blueprint)
    first = volumes[0] if volumes else None
    for anchor in anchors:
        if anchor["sequence"] == 1 and first:
            first.content = {
                **first.content,
                "chapter_range": anchor["chapter_range"],
                "status": "detailed",
                "stage_title": anchor["stage_title"],
            }
            continue
        db.add(
            Outline(
                project_id=project.id,
                parent_id=book.id,
                level="volume",
                sequence=anchor["sequence"],
                title=anchor["title"],
                content={
                    "goal": f"待第{anchor['sequence']}卷开始前滚动规划",
                    "stage_title": anchor["stage_title"],
                    "chapter_range": anchor["chapter_range"],
                    "status": "anchor",
                },
                is_sealed=False,
            )
        )
    await db.flush()
    all_volumes = list(
        (
            await db.scalars(
                select(Outline)
                .where(Outline.project_id == project.id, Outline.level == "volume")
                .order_by(Outline.sequence.asc())
            )
        ).all()
    )
    # 同步已有章节的卷序号。
    chapters = list((await db.scalars(select(Chapter).where(Chapter.project_id == project.id))).all())
    for chapter in chapters:
        anchor = next(
            item
            for item in anchors
            if item["chapter_range"][0] <= chapter.chapter_sequence <= item["chapter_range"][1]
        )
        chapter.volume_sequence = anchor["sequence"]
    # 同步已有章纲的父卷。
    for chapter_outline in [item for item in outlines if item.level == "chapter"]:
        owner = next(
            item
            for item in all_volumes
            if item.content["chapter_range"][0]
            <= chapter_outline.sequence
            <= item.content["chapter_range"][1]
        )
        chapter_outline.parent_id = owner.id

    # 同步 PageIndex 卷树及已有章节父节点。
    book_toc = await db.scalar(
        select(NovelToc).where(NovelToc.project_id == project.id, NovelToc.level == "book")
    )
    toc_volumes = list(
        (
            await db.scalars(
                select(NovelToc)
                .where(NovelToc.project_id == project.id, NovelToc.level == "volume")
                .order_by(NovelToc.sequence.asc())
            )
        ).all()
    )
    first_toc = toc_volumes[0] if toc_volumes else None
    for anchor in anchors:
        if anchor["sequence"] == 1 and first_toc:
            first_toc.chapter_range_start, first_toc.chapter_range_end = anchor["chapter_range"]
            continue
        db.add(
            NovelToc(
                project_id=project.id,
                parent_id=book_toc.id if book_toc else None,
                level="volume",
                sequence=anchor["sequence"],
                title=anchor["title"],
                summary=f"待第{anchor['sequence']}卷开始前滚动规划",
                characters=[project.protagonist_name],
                key_events=[],
                chapter_range_start=anchor["chapter_range"][0],
                chapter_range_end=anchor["chapter_range"][1],
            )
        )
    await db.flush()
    all_volume_tocs = list(
        (
            await db.scalars(
                select(NovelToc)
                .where(NovelToc.project_id == project.id, NovelToc.level == "volume")
                .order_by(NovelToc.sequence.asc())
            )
        ).all()
    )
    chapter_tocs = list(
        (
            await db.scalars(
                select(NovelToc).where(NovelToc.project_id == project.id, NovelToc.level == "chapter")
            )
        ).all()
    )
    for chapter_toc in chapter_tocs:
        owner = next(
            (
                item
                for item in all_volume_tocs
                if item.chapter_range_start is not None
                and item.chapter_range_end is not None
                and item.chapter_range_start <= chapter_toc.sequence <= item.chapter_range_end
            ),
            None,
        )
        if owner:
            chapter_toc.parent_id = owner.id
    book.content = {**book.content, "volume_count": volume_count}
    await db.flush()
    return all_volumes
