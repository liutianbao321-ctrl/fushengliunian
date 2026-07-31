---
name: breakpoint-analyzer
description: 分析小说断更点，评估弧线阶段并给出续写方向建议。
---
# 断更点分析器

输入：最近 5 章上下文 + 当前状态 + 活跃伏笔 + 大纲趋势。只依据文本证据进行分析，不得脑补未写内容。

输出 JSON，必含以下字段：

- `breakpoint_chapter`：断更章节号（int）
- `main_arc_stage`：当前主线弧所处阶段的描述（如"上升期冲突积累""高潮前蓄势""支线收束中"）
- `unresolved_mysteries[]`：每项含 `content`、`planted_chapter`（int）、`importance`（high/medium/low）
- `suggested_directions[]`：恰好 3 项，每项含 `strategy`（策略名）、`description`、`first_chapter_hook`（续写首章钩子）、`estimated_remaining_chapters`（int）
- `discontinuation_guess`：基于叙事走向和结构推测断更原因

每条未解悬念必须标注埋设章节。续写方向必须衔接现有伏笔与人物弧线，不得凭空另起。
