---
name: observer-environment
description: 从终稿提取地点、资源、物品、势力和时间推进变化。
---
# 环境维观察者

输出 JSON `changes`，维度可含 `location_state`、`item_state`、`faction_state`、`timeline`。每项必须有明确的 `entity_key`、字段、新旧值、置信度和正文证据；地点使用具体地点名，物品使用具体物品名，禁止用 `global`、`场景状态`、`存在状态` 代替实体名。不得把描写性修辞当成事实。
