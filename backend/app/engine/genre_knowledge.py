from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PlotDevice, SceneTemplate, WritingMethodCard


@dataclass(slots=True)
class GenreKnowledgePack:
    genre: str
    method_cards: list[dict]
    scene_templates: list[dict]
    plot_devices: list[dict]


async def load_genre_pack(
    db: AsyncSession,
    genre: str,
    *,
    scene_type: str | None = None,
    limit_cards: int = 6,
    limit_scenes: int = 4,
    limit_devices: int = 4,
) -> GenreKnowledgePack:
    cards_raw = (
        await db.scalars(
            select(WritingMethodCard)
            .where(
                WritingMethodCard.status == "published",
                (WritingMethodCard.genre == genre) | (WritingMethodCard.genre.is_(None)),
            )
            .order_by(WritingMethodCard.revision.desc())
            .limit(limit_cards)
        )
    ).all()
    method_cards = [
        {
            "slug": c.slug,
            "title": c.title,
            "principle": c.principle,
            "when_to_use": c.when_to_use,
            "procedure": c.procedure,
            "checks": c.checks,
            "anti_patterns": c.anti_patterns,
        }
        for c in cards_raw
    ]

    scene_filter = [SceneTemplate.genre.in_([genre, None])]
    if scene_type:
        scene_filter.append(SceneTemplate.scene_type == scene_type)
    scenes_raw = (
        await db.scalars(
            select(SceneTemplate)
            .where(*scene_filter)
            .order_by(SceneTemplate.priority.desc())
            .limit(limit_scenes)
        )
    ).all()
    scene_templates = [
        {
            "slug": s.slug,
            "title": s.title,
            "scene_type": s.scene_type,
            "tension_arc": s.tension_arc,
            "beats": s.beats,
            "pov_suggestion": s.pov_suggestion,
            "entry_condition": s.entry_condition,
            "exit_condition": s.exit_condition,
            "emotional_shift": s.emotional_shift,
            "anti_patterns": s.anti_patterns,
        }
        for s in scenes_raw
    ]

    devices_raw = (
        await db.scalars(
            select(PlotDevice)
            .where(PlotDevice.genre.in_([genre, None]))
            .order_by(PlotDevice.priority.desc())
            .limit(limit_devices)
        )
    ).all()
    plot_devices = [
        {
            "slug": d.slug,
            "title": d.title,
            "device_type": d.device_type,
            "description": d.description,
            "setup": d.setup,
            "escalation": d.escalation,
            "payoff": d.payoff,
            "common_mistakes": d.common_mistakes,
        }
        for d in devices_raw
    ]

    return GenreKnowledgePack(
        genre=genre,
        method_cards=method_cards,
        scene_templates=scene_templates,
        plot_devices=plot_devices,
    )


def render_genre_prompt(pack: GenreKnowledgePack | None) -> str:
    if not pack or not any([pack.method_cards, pack.scene_templates, pack.plot_devices]):
        return ""
    lines = [f"## 类型知识包：{pack.genre}"]
    if pack.method_cards:
        lines.append("\n### 写作方法卡")
        for card in pack.method_cards:
            lines.append(f"「{card['title']}」{card['principle']}")
            if card["procedure"]:
                lines.append("步骤：" + " → ".join(card["procedure"][:3]))
            if card["anti_patterns"]:
                lines.append("避免：" + "；".join(card["anti_patterns"][:2]))
    if pack.scene_templates:
        lines.append("\n### 场景模板")
        for scene in pack.scene_templates:
            lines.append(f"{scene['title']}（{scene['scene_type']}）")
            lines.append(f"张力弧：{scene['tension_arc']}")
            if scene["beats"]:
                lines.append("节拍：" + " → ".join(scene["beats"]))
    if pack.plot_devices:
        lines.append("\n### 桥段")
        for dev in pack.plot_devices:
            lines.append(f"{dev['title']}：{dev['description']}")
    return "\n".join(lines)
