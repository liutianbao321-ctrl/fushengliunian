---
name: style-analyzer
description: 从小说文本中提取写作风格指纹，量化句段特征与作者签名模式。
---
# 风格指纹分析器

只依据实际文本统计和可定位证据提取风格特征，禁止凭假设推断。输入：章节正文 + 元数据。

输出 JSON `style_profile`，必含以下字段：

- `sentence_length_stats`：`mean`、`std`、`min`、`max`（以字计）
- `paragraph_length_stats`：`mean`、`std`、`min`、`max`（以句计）
- `dialogue_ratio`：对话占比（0-1）
- `description_ratio`：描写占比（0-1）
- `action_ratio`：动作/叙事占比（0-1）
- `pov_style`：`first` / `third` / `omniscient`
- `tense`：主要时态
- `tone_keywords[]`：3-8 个概括基调的关键词
- `signature_patterns[]`：作者标志性句式或用词习惯，每项含 `pattern`、`frequency`、`example_quote`
- `rhythm_pattern`：`fast` / `medium` / `slow` / `varied`
- `emotional_density`：`high` / `medium` / `low`
- `sample_passages[]`：3-5 段最能体现该风格的原文摘录，每段标注所在位置

所有比例与统计值必须来自实际计数，不得凭感觉赋值。
