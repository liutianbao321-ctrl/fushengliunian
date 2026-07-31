"""种子数据：为所有主流类型注入初始写作方法卡、场景模板和桥段。

用法:
    python scripts/seed_genre_knowledge.py
"""

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models import PlotDevice, SceneTemplate, WritingMethodCard

GENRES = ["玄幻", "仙侠", "都市", "言情", "悬疑", "科幻", "历史", "游戏"]

METHOD_CARDS = {
    "玄幻": [
        {
            "slug": "xianxia-leveling-arc",
            "title": "升级弧的节奏控制",
            "principle": "每 3-5 章一个小突破，10-15 章一个境界跨越；突破前必须有代价或风险铺垫。",
            "when_to_use": "写修炼/升级段落时",
            "procedure": ["铺垫瓶颈或契机", "写修炼/战斗过程", "展示突破后的变化与新代价"],
            "checks": ["突破前是否有至少一章的阻力描写", "突破后是否至少引入一个新冲突"],
            "anti_patterns": ["机械升级无代价", "每章都突破"],
        },
        {
            "slug": "xianxia-power-display",
            "title": "战力展示的黄金法则",
            "principle": "新能力首次展示要有仪式感：对手先强→主角被压制→找到破绽→反杀。不要在练功房展示新技能。",
            "when_to_use": "主角获得新能力/新法宝的第一场战斗",
            "procedure": ["先写对手的强大与自信", "主角陷入被动", "找到对方能力的边界", "用新能力逆转"],
            "checks": ["读者是否能清晰感知新能力有多强", "对手是否被尊重（不是小丑）"],
            "anti_patterns": ["秒杀式首秀", "新能力当场失效制造尴尬"],
        },
    ],
    "仙侠": [
        {
            "slug": "immortal-cultivation-frustration",
            "title": "修炼路上的挫败设计",
            "principle": "仙侠的魅力在于'求道之难'。每三次成功搭配一次重大挫败，让读者为主角的坚持共情。",
            "when_to_use": "主角连续获得机缘后",
            "procedure": ["布置一个无法靠蛮力突破的关卡", "写主角的执着与试错", "在看似绝望时发现另一条路"],
            "checks": ["挫败是否让读者心疼而非烦躁", "另一条路是否早有伏笔"],
            "anti_patterns": ["挫败只是为了打脸反派", "每条路都走不通"],
        },
    ],
    "都市": [
        {
            "slug": "urban-slice-status",
            "title": "都市文的社会地位阶梯",
            "principle": "都市爽感来自社会地位的可见提升。每 10 章左右在社交场合展示一次主角的阶层跃迁信号。",
            "when_to_use": "规划中期情节时",
            "procedure": ["设定当前社会圈层的上限", "设计一个跨圈层的社交场合", "让主角在场合中展示超出预期的能力或资源"],
            "checks": ["社会地位展示是否自然（不是刻意炫耀）", "跃迁后是否带来新冲突"],
            "anti_patterns": ["每章都在打脸装逼", "主角的社会地位与实力不匹配"],
        },
    ],
    "言情": [
        {
            "slug": "romance-tension-tango",
            "title": "情感的推拉节奏",
            "principle": "言情核心是'推拉'：靠近→误解/阻碍→更近一步→新阻碍。每 5-8 章完成一次推拉循环。",
            "when_to_use": "男女主感情发展的每个阶段",
            "procedure": ["制造一个让两人必须靠近的场景", "写双方的心理活动（单视角）", "插入外部阻碍", "在解决阻碍中感情升温"],
            "checks": ["每次推是否让读者有真实失落感", "每次拉是否让读者感到值得等待"],
            "anti_patterns": ["为虐而虐", "一甜到底无波澜"],
        },
    ],
    "悬疑": [
        {
            "slug": "mystery-clue-layering",
            "title": "线索的分层投放",
            "principle": "每 3 章给一条新线索，每 5 章回收一条旧线索同时引出更深谜团。不要让读者连续 10 章只有新线索没有答案。",
            "when_to_use": "设计长篇谜案时",
            "procedure": ["规划 3-4 层谜团", "每层投放 2-3 条线索", "在层间安排一个'小答案'作为奖励"],
            "checks": ["读者是否能在第 3 章时已经能猜到第 1 层答案", "每条线索是否有至少两种解读可能"],
            "anti_patterns": ["所有线索同一章给出", "答案全靠主角灵光一闪"],
        },
    ],
    "科幻": [
        {
            "slug": "scifi-tech-cost",
            "title": "科技设定必须附带代价",
            "principle": "有趣的科幻设定都有显著代价或限制。没有代价的超能力/黑科技会让故事失去张力。",
            "when_to_use": "引入新技术/黑科技时",
            "procedure": ["展示技术的强大", "揭示代价或限制", "让主角必须做权衡"],
            "checks": ["代价是否影响情节走向", "限制是否在关键时刻起作用"],
            "anti_patterns": ["技术无副作用", "代价在下一章就被无视"],
        },
    ],
    "历史": [
        {
            "slug": "historical-restraint",
            "title": "历史文的真实感约束",
            "principle": "主角可以改变小事件，但大历史趋势需尊重。让读者感觉'这确实可能发生在那个时代'。",
            "when_to_use": "主角准备改变历史事件时",
            "procedure": ["先完整写出历史上该事件的原貌", "让主角了解背后的因果关系", "在小细节上做改变，而非推翻大趋势"],
            "checks": ["时代细节是否准确（衣食住行）", "改变是否在合理范围内"],
            "anti_patterns": ["主角颠覆整个王朝", "现代价值观硬套古代"],
        },
    ],
    "游戏": [
        {
            "slug": "game-like-reward-cycle",
            "title": "游戏文的奖励周期",
            "principle": "每 2 章一个小奖励（装备/技能点），每 5 章一个中奖励（新副本/新地图），每 15 章一个大奖励（转职/神器）。",
            "when_to_use": "规划整本书的节奏时",
            "procedure": ["设定主角当前等级的目标", "安排获得奖励的挑战", "展示奖励的实际效果"],
            "checks": ["奖励是否对应付出", "奖励后是否引入新挑战"],
            "anti_patterns": ["挂机式升级", "奖励只有数值变化无实质影响"],
        },
    ],
}

SCENE_TEMPLATES = {
    "战斗": {
        "tension_arc": "低→渐高→峰值→回落",
        "beats": ["对峙（双方亮牌）", "试探（低强度交手）", "压制（一方劣势）", "逆转（底牌/援军）", "结局（胜/负/逃）"],
        "pov_suggestion": "全程锁定主角视角",
        "entry_condition": "双方目标不可调和且愿意正面冲突",
        "exit_condition": "一方目标达成/放弃/失去战斗能力",
        "emotional_shift": "自信→紧张→绝境→振奋/释然",
        "anti_patterns": ["一招秒杀", "全程碾压", "战斗中插回忆杀"],
    },
    "谈判": {
        "tension_arc": "中→渐高→高峰→下降",
        "beats": ["开场条件（双方要价）", "拉锯（互相试探底线）", "僵局（谁都不让步）", "转折（新信息/第三方）", "成交或破裂"],
        "pov_suggestion": "主视角为主，必要时切对方微表情",
        "entry_condition": "双方有交易需求但利益不一致",
        "exit_condition": "达成协议或彻底决裂",
        "emotional_shift": "冷静→不耐→焦躁→算计→满意/愤怒",
        "anti_patterns": ["主角永远占上风", "对方智商下线"],
    },
    "情感": {
        "tension_arc": "低→渐高→峰值→温和",
        "beats": ["日常相处（铺垫）", "触发事件（意外/冲突）", "情绪爆发（争吵/表白）", "深层沟通（理解/原谅）"],
        "pov_suggestion": "优先选情绪波动更大的一方",
        "entry_condition": "两人之间存在未解决的张力",
        "exit_condition": "关系进入新阶段（更近或更远）",
        "emotional_shift": "平静→波动→激烈→温暖/伤感",
        "anti_patterns": ["为煽情而煽情", "和解太快无过渡"],
    },
    "悬疑": {
        "tension_arc": "低→持续上升→高峰→部分解答",
        "beats": ["发现异常", "收集线索", "误入歧途", "接近真相", "反转（新谜团）"],
        "pov_suggestion": "主角视角，保留信息给读者",
        "entry_condition": "主角接触到超出理解范围的异常",
        "exit_condition": "当前谜团有阶段性答案或出现更大谜团",
        "emotional_shift": "好奇→困惑→焦虑→专注→震惊",
        "anti_patterns": ["线索全由配角告知", "答案是主角直觉"],
    },
    "修炼": {
        "tension_arc": "低→缓慢上升→突破→回落",
        "beats": ["闭关准备", "修炼过程（阻力/瓶颈）", "突破契机", "晋升", "新境界的代价或副作用"],
        "pov_suggestion": "内视角为主，感知体内变化",
        "entry_condition": "主角达到当前境界圆满",
        "exit_condition": "成功突破或卡瓶颈另寻出路",
        "emotional_shift": "平静→焦躁→专注→畅快→沉重",
        "anti_patterns": ["跳过过程直接突破", "突破后无新内容"],
    },
}

PLOT_DEVICES = [
    {
        "slug": "hidden-identity",
        "device_type": "身份",
        "description": "主角或重要角色隐藏真实身份，在关键时刻揭露引发剧情转折。",
        "setup": ["暗示身份异常（特殊能力/知识/反应）", "安排身份相关的限制或威胁"],
        "escalation": ["身份面临被揭穿的危险", "为保身份做出牺牲或选择"],
        "payoff": ["在最危急的时刻揭露", "揭露后改变力量对比或人际关系"],
        "common_mistakes": ["铺垫不够显得突兀", "揭露后无实质影响"],
    },
    {
        "slug": "race-against-time",
        "device_type": "时限",
        "description": "给主角一个明确的时间限制，在倒计时中推进情节。",
        "setup": ["设定不可更改的截止点", "给出足够重要的成败后果"],
        "escalation": ["途中出现意外延误", "资源/盟友不足"],
        "payoff": ["极限时刻达成或失败", "无论成败都改变局势"],
        "common_mistakes": ["时限过长失去紧迫感", "每次都能极限翻盘"],
    },
    {
        "slug": "mentor-sacrifice",
        "device_type": "成长",
        "description": "导师角色的牺牲（死亡/离开/背叛）成为主角成长的关键转折。",
        "setup": ["建立师徒情感", "暗示导师有秘密或危险"],
        "escalation": ["导师的困境逐步显现", "主角察觉但无力改变"],
        "payoff": ["牺牲发生", "主角继承导师遗志或能力"],
        "common_mistakes": ["导师出场太少读者无感", "牺牲后主角很快恢复"],
    },
    {
        "slug": "tournament-arc",
        "device_type": "事件",
        "description": "通过竞赛/比武/选拔等结构化事件推进情节、展示成长、引入新角色。",
        "setup": ["宣布竞赛及其规则", "主角参赛动机"],
        "escalation": ["逐轮晋级", "遭遇强敌", "场外阴谋"],
        "payoff": ["决赛高潮", "结果改变势力格局"],
        "common_mistakes": ["轮次过多枯燥", "主角永远压轴"],
    },
]


async def seed(db: AsyncSession) -> dict:
    now = datetime.now(UTC)
    stats = {"method_cards": 0, "scene_templates": 0, "plot_devices": 0}

    for genre, cards in METHOD_CARDS.items():
        for card in cards:
            existing = await db.scalar(
                select(WritingMethodCard).where(WritingMethodCard.slug == card["slug"])
            )
            if existing:
                continue
            db.add(WritingMethodCard(
                id=uuid4(),
                slug=card["slug"],
                title=card["title"],
                principle=card["principle"],
                when_to_use=card.get("when_to_use", ""),
                procedure=card.get("procedure", []),
                checks=card.get("checks", []),
                anti_patterns=card.get("anti_patterns", []),
                genre=genre,
                tags=["写作方法", "网文", genre],
                status="published",
                revision=1,
                created_at=now,
                updated_at=now,
            ))
            stats["method_cards"] += 1

    for scene_type, template in SCENE_TEMPLATES.items():
        slug = f"scene-{scene_type}"
        existing = await db.scalar(
            select(SceneTemplate).where(SceneTemplate.slug == slug)
        )
        if existing:
            continue
        db.add(SceneTemplate(
            id=uuid4(),
            slug=slug,
            title=f"{scene_type}场景模板",
            scene_type=scene_type,
            genre=None,
            tension_arc=template["tension_arc"],
            beats=template["beats"],
            pov_suggestion=template["pov_suggestion"],
            entry_condition=template["entry_condition"],
            exit_condition=template["exit_condition"],
            emotional_shift=template["emotional_shift"],
            anti_patterns=template["anti_patterns"],
            tags=["场景模板", scene_type],
            priority=10,
            created_at=now,
            updated_at=now,
        ))
        stats["scene_templates"] += 1

    for device in PLOT_DEVICES:
        existing = await db.scalar(
            select(PlotDevice).where(PlotDevice.slug == device["slug"])
        )
        if existing:
            continue
        db.add(PlotDevice(
            id=uuid4(),
            slug=device["slug"],
            title={"hidden-identity": "隐藏身份", "race-against-time": "限时任务", "mentor-sacrifice": "导师牺牲", "tournament-arc": "比武大会"}.get(device["slug"], device["slug"]),
            device_type=device["device_type"],
            genre=None,
            description=device["description"],
            setup=device["setup"],
            escalation=device["escalation"],
            payoff=device["payoff"],
            common_mistakes=device["common_mistakes"],
            tags=["桥段", device["device_type"]],
            priority=10,
            created_at=now,
            updated_at=now,
        ))
        stats["plot_devices"] += 1

    await db.commit()
    return stats


async def main():
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        stats = await seed(db)
        print(f"写入: 方法卡 {stats['method_cards']} 张 / 场景 {stats['scene_templates']} 个 / 桥段 {stats['plot_devices']} 个")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
