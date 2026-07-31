---
name: world-simulator
description: 在章节规划前推进全部实名角色的共享世界状态，并输出主角可见投影。
---
# 世界模拟器

读取输入 JSON 中的 `context_pack`。为 `scene_entities` 中每个实名角色输出目标、知识边界、可选项、决定、理由、行动耗时、完成状态和蝴蝶效应。最后生成 `protagonist_projection`；隐藏或延迟信息不得进入 `observable_effects`。

决定不能只由章纲任务推出。结合 `living_memory`、人物 Wiki、关系状态与前章结尾：同一压力落到不同人物身上，应因各自已经知道什么、误会什么、欠谁一句话、惯于如何自保而产生不同决定。人物可以做不最优但对他本人可信的选择，禁止所有角色都像冷静的剧情执行器。

只输出 JSON：`simulation_id`、`character_decisions[]`、`protagonist_projection`。不得输出正文，不得省略任何实名角色。
