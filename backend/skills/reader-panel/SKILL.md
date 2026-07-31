---
name: reader-panel
description: 模拟多类型读者阅读章节并输出追读评分与反馈。
---
# 读者评审团

输入：章节正文 + 前情摘要 + 赛道信息 + 口味标签。模拟至少三位不同画像的读者独立评审，评分必须基于文本证据，禁止虚高。

固定读者画像：
- **爽文小白**：追求爽感与节奏，关注爽点密度和代入感
- **老书虫**：审视叙事技巧、人物弧线和伏笔回收
- **毒舌评论家**：苛刻挑刺，关注逻辑硬伤和套路化问题

输出 JSON，必含以下字段：

- `chase_score`：追读欲望分（0-100），必须附理由
- `one_line_verdict`：一句话总评
- `readers[]`：每位读者含 `persona`、`reaction`（50 字内感受）、`keep_reading`（bool）、`highlight`（最佳段落引用）、`suggestions[]`
- `thrill_analysis`：`thrill_count`（本章爽点数）、`recommended_count`（建议爽点数）、`missing_types[]`（缺失的爽点类型）
- `abandon_risks[]`：每项含 `location`（章内位置描述）、`reason`（可能劝退的原因）

60 分以下必须给出具体改进建议。不得所有读者意见趋同。
