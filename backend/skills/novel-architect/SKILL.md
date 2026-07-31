---
name: novel-architect
description: 根据作者确认的章纲、人物状态和文风合同整理可写的因果场景。
---
# 章节建筑师

输出 JSON：`chapter_sequence`、`pov_character`、`characters[]`、`beats[]`、`consciousness_thread`，并保留章纲中的 `reader_experience`、`protagonist_change`、`opening`、`style_direction`、`hook`、`ending_image`、`must_avoid`。

`beats` 是 1 至 8 个连续情节段，不是固定场景数量，也不套固定四段式。一个情节段可以是一场完整互动，也可以是在同一地点里的等待、试探、误判、谈判、失败余波或局部兑现。每段包含角色即时目标、阻力、策略、结果与感官锚点；前一段结果必须触发后一段需求。禁止为了结构完整强行反转，禁止“制造冲突”“留下悬念”等元叙事占位语。

读取章纲中的 `progression_budget`。整章只允许 `single_local_change` 指定的一种局部变化，`event_span` 说明当前事件是否需要跨章延续，`must_remain_open` 必须保持未解决。能力、关系、真相、身份、地图/势力五类进展不能在同章跨越两类；多个 beats 应展开同一件事的尝试、反应和余波，不能各自完成一个任务。若本章只有一个情节段，也要把它整理成可写的完整现场，而不是强行拆分。

先读取 `style_profile.author_constitution`。章纲必须说明本章用哪一个人物选择兑现作者想留下的感受，并尊重不可妥协项；`writing_guidance.method_cards` 只提供可选方法，不能凌驾于作者宪章、Canon 或人物自身逻辑。

情节因果之外，必须设计一条“人物意识接力”。它不是让正文逐项扩写的新清单，而是防止每场、每段都把人物大脑重置：

- `consciousness_thread.carry_in`：从 `living_memory` 和前章结尾中选择本 POV 真正带进现场的身体余感、未完成意图、当前误解、没说出口的话或关系记忆。首章则从人物既有习惯与眼前处境建立起点。不要复述前情。
- `consciousness_thread.scene_threads[]` 必须与 `beats[]` 一一对应。每项至少含 `attention_shift`、`action_cause`、`residue`，并可含 `private_association`、`self_justification`、`spoken_subtext`。前一段的 `residue` 必须成为后一段注意、判断或措辞发生偏移的原因；若只有一个情节段，则重点写清 carry_in 与 chapter_aftertaste。
- `consciousness_thread.chapter_aftertaste`：记录人物内部发生了什么细微偏移、什么仍未说出口、哪个动作或感官印象会跟进下一章。它不能是“危机仍在继续”之类策划话术。

意识线必须属于这个具体人物。若换成同题材的任意主角仍然成立，就重做。细节不是装饰：人物注意到它，是因为欲望、旧经验、偏见或关系史让它此刻变得刺眼。

意识线只能重新组织输入中已有的人物经历、动作、物品和现场事实。不得为了让联想显得巧妙而新增伤痕来源、物品归属、旧事或巧合；输入未确认的联系只能写成人物当下的猜测，并保留可能猜错的空间。

`consciousness_thread` 不得省略，结构必须如下（值写成具体内容，不要复制占位文字）：
`{"carry_in": {...}, "scene_threads": [{"attention_shift": "...", "action_cause": "...", "residue": "..."}], "chapter_aftertaste": {...}}`。

除首章外，`living_memory.previous_ending` 是本章开场的硬边界：上一章最后已经在进行的动作、对白、威胁、人物位置、手中物和可判断的时段必须从下一瞬间接续。除非 `chapter_outline` 明确写出经过多久以及期间发生什么，不得切换昼夜、让人物回到先前位置、重做上一章已发生的动作，或把同一声响、来客、发现和冲突再次当作第一次发生。若旧章纲的 `opening` 与已发布前章结尾冲突，以已发布前章结尾为准，并只保留章纲尚未发生的核心事件。
