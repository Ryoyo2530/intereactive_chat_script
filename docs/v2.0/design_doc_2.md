# 入戏 v2.0.detail-2 —— 长篇玩法引擎 MVP

> 本文档是 v2.0 总纲（`ruxi-v2.0-overall.md`）下的第二份可执行指令文档，承接 detail-1 已落地的数据模型（`works`/`chapters`/`saves` 表）。本阶段目标是让**多章节长篇作品的核心玩法机制**完整跑通：章节推进、flag读写、章节收尾判定出口、存档/读档。**本阶段不做产品层UI**（选择页模式切换、长篇卡片、阅读流呈现留给 detail-3），只需要能通过接口/最小化前端（沿用现有对局界面即可，不打磨）跑通一个完整的多章节长篇demo作品。

---

## 一、本阶段目标

1. `engine.py`（或拆分后的 `core/engine.py`）支持"章节收尾"这一新增编排环节，衔接章节与章节之间的推进
2. 实现 `exits` 的两种类型解析：`hard_condition`（代码判定）与 `ai_choice`（LLM在候选池内选择，含兜底）
3. 实现 flag 的读取（拼入导演prompt）与写入（章节收尾时判定触发并落库）
4. 实现章节收尾摘要的生成与存储
5. 实现长篇存档的读档恢复（从任意存档点继续游玩）
6. 产出一个最小的长篇demo作品（2-3章即可，含至少一处硬性分支和一处ai_choice分支），用于端到端验证

## 二、本阶段明确不做

- 不做选择页/卡片/模式切换等产品层UI（detail-3范围）
- 不做重度AI自由（AI创造新分支/新章节）——本阶段 `ai_choice` 的候选池必须是剧本作者预先写定的现有章节id列表
- 不做flag删改（v2.0范围内flag只增，本阶段的flag写入逻辑不需要考虑覆盖/删除已有flag的场景）
- 不做多模态

---

## 三、导演Agent输出扩展（章节收尾时）

导演agent在**每一轮**的输出结构不变（`stat_changes`/`hit_key_points`/`hit_pitfalls`/`reaction`/`game_over` 等，沿用已有结构）。新增的是：当本轮判定触发 `game_over=true`（即本章节结束，无论是胜利、失败还是正常推进到下一章），导演agent的输出**额外**包含一个 `chapter_wrap_up` 字段：

```json
{
  "stat_changes": {...},
  "hit_key_points": [...],
  "hit_pitfalls": [...],
  "reaction": {...},
  "game_over": true,
  "chapter_wrap_up": {
    "summary": "玩家选择独自承担误会，未向任何人求助。",
    "triggered_flags": ["chose_confront_mother"]
  }
}
```

- `summary`：30-50字量级的章节摘要，用于后续章节prompt引用
- `triggered_flags`：本章 `flags_write` 声明列表中，实际满足触发条件的flag id列表（导演agent只需要判断"哪些flag的trigger条件在本章游玩过程中被满足了"，具体flag如何写入存档由engine层处理，不由LLM直接决定flag的value内容——除非该flag定义本身就需要一个非布尔值，此时trigger条件里应明确说明取值规则）

**解析容错**：`chapter_wrap_up` 解析失败或缺失时的兜底策略——`summary` 兜底为一句通用文案（如"这一章的故事告一段落。"），`triggered_flags` 兜底为空列表（即本章不触发任何flag写入，宁可少记一次flag，也不要因为解析异常写入错误的flag）。此兜底逻辑需要打印日志，便于后续观察哪类章节容易导致该字段解析失败。

`chapter_wrap_up` 只应该由导演agent在**最后一轮**（`game_over=true`时）产出，其余轮次不需要要求LLM输出这个字段，避免增加不必要的token消耗。

---

## 四、章节收尾编排逻辑（engine.py 新增流程）

在原有"判定 `game_over=true` 后返回结局"的基础上，长篇场景下需要追加以下步骤：

1. 从导演agent本轮输出中取出 `chapter_wrap_up`
2. **写入flag**：遍历当前章节 `flags_write` 声明列表，检查每条的 `trigger` 是否出现在 `chapter_wrap_up.triggered_flags` 中，命中则将该flag写入存档的 `flags` 字典（只增，若该flag已存在则跳过，不覆盖——本阶段flag只增的约束在此落地）
3. **写入章节摘要**：将 `chapter_wrap_up.summary` 追加到存档的 `chapter_summaries` 列表
4. **判定出口（exits）**：按 `exit_evaluation_order: hard_condition_first` 规则（见detail-1中chapter表的exits字段设计），依次尝试：
   - 遍历所有 `type: hard_condition` 的出口，用当前存档的 `stats` + `flags` 求值其 `condition` 表达式（复用 `condition_parser.py`），第一个满足条件的即为下一章
   - 若所有 `hard_condition` 均不满足，且存在 `type: ai_choice` 的出口：调用导演agent（或复用本轮已有的LLM调用，视实现效率决定是否合并成一次调用），传入 `candidates` 候选章节id列表 + 该出口的 `selection_guidance` + 本章游玩摘要，要求LLM从候选池中选择一个章节id
   - LLM选择结果解析失败，或返回值不在candidates列表内：使用该出口的 `fallback_next_chapter` 作为兜底，**必须**保证此处不会出现"无法确定下一章"的卡死情况
   - 若某作品的最后一章没有任何exits（即该章节就是终点章节），直接判定为作品结局，不再尝试推进
5. **更新存档**：`current_chapter_id` 更新为判定出的下一章，`current_turn` 归零，`hit_key_point_ids`/`hit_pitfall_ids`/`conversation_history` 针对新章节清空（这些是章节内状态，不跨章节保留，跨章节保留的只有 `stats`/`flags`/`chapter_summaries`）
6. 返回给前端的响应中，除了原有字段，长篇场景下需要额外包含 `next_chapter_id`（或明确 `work_completed: true` 表示整部作品结束）供前端判断是否需要展示"进入下一章"的过渡

---

## 五、Prompt 模板扩展

`director_user.txt` 新增占位符（长篇场景下才会被填充，短局场景该部分留空即可，不影响短局prompt）：

```
【已知剧情事实】
{{known_flags_summary}}
<!-- 格式示例：玩家此前已对林某坦白过秘密；玩家此前选择了独自承担误会。 -->

【前情概要】
{{chapter_summaries_recent}}
<!-- 拼接最近1-3章的summary，避免无限累积导致prompt过长 -->
```

- `known_flags_summary`：engine层根据当前章节的 `flags_read` 声明，从存档 `flags` 字典中查出对应值，组装成自然语言句子（简单模板拼接即可，不需要额外LLM调用）
- `chapter_summaries_recent`：直接取存档 `chapter_summaries` 列表的最近N条（建议N=3，避免章节数增多后prompt线性膨胀），格式为纯文本列表

`prompt_manager.py` 的 `render()` 接口不需要改变行为，只是长篇场景下调用时会多传入这两个变量。

---

## 六、存档读写接口

### 6.1 开始新游玩 / 继续已有存档

- `POST /api/session/start`：短局场景行为不变。长篇场景下，若请求体带 `save_id` 且该存档存在，则从存档恢复状态（读取 `current_chapter_id`/`stats`/`flags`/`chapter_summaries`/`conversation_history` 等）继续游玩；若不带 `save_id`，则从该work的 `entry_chapter_id` 开始新建一份存档
- 响应体需要包含当前所处章节的基本信息（章节标题、开场白或延续对话所需的历史），供前端渲染

### 6.2 章节切换

- 当 `POST /api/session/message` 的响应中出现 `next_chapter_id`（章节切换发生）时，前端下一次请求应该是对新章节的 `opening_line` 展示 + 后续对话仍走 `/api/session/message`，具体的"进入新章节"接口形态（是复用start接口重新调用，还是新增一个轻量的 `advance_chapter` 接口）由实现时根据前端交互需要决定，但**核心约束**是：无论哪种接口形态，都必须保证章节切换后的存档状态（第四节步骤5）已经落库，不依赖前端额外传参来维持状态一致性

### 6.3 存档管理

本阶段只需要支持**单存档位**（一部长篇作品同一时间只维护一份进行中的存档，不需要多存档槽位管理），够验证机制即可。多存档槽位、存档列表管理等属于产品体验层面的能力，如后续需要可在detail-3或更晚阶段补充。

---

## 七、Demo长篇作品要求

用于本阶段验证，建议创建一个2-3章的最小demo作品，需要覆盖：

- 至少1个章节包含 `hard_condition` 类型的出口（且要设计出至少两条不同条件的分支，确保能分别测试到不同走向）
- 至少1个章节包含 `ai_choice` 类型的出口（候选池至少2个章节，并验证 `fallback_next_chapter` 兜底路径可以被人为触发——例如通过构造一次导演输出解析失败的场景）
- 至少1个 `flags_write`/`flags_read` 的实际跨章节引用（比如第1章某选择产生flag，第3章的prompt里能看到基于该flag的"已知剧情事实"文本，且该flag同时也是某条硬性分支的判定条件之一）
- demo作品内容不需要精雕细琢，能支撑验证即可，正式的长篇内容创作在detail-2验证通过后再进行

---

## 八、验证要求

1. 完整走通demo作品的一条主线路径（从entry_chapter到某个终点章节），确认章节切换、数值贯穿、flag读写、摘要生成全部符合预期
2. 人为构造走向不同 `hard_condition` 分支的对局（至少覆盖两条不同分支），确认分支判定结果符合剧本设计
3. 验证 `ai_choice` 机制：正常情况下LLM能在候选池内做出合理选择；人为构造LLM返回格式错误或候选池外内容的场景，确认走到 `fallback_next_chapter` 兜底且不报错、不卡死
4. 验证flag只增语义：让同一个flag的触发条件在多章节中重复满足，确认flag不会被重复写入或产生冲突覆盖
5. 验证存档读档：在某一章节中途退出（不完成该章节），重新请求 `start` 接口带上对应 `save_id`，确认能正确恢复到中断前的状态（当前章节、数值、已命中关键点、对话历史）
6. 确认短局（`type: short_form`）作品在本阶段改动后行为**完全不受影响**——这是贯穿v2.0的底线要求，需要重新跑一遍v1.x原有的验证清单（选剧本→对话→触发结局）
7. 检查 `chapter_wrap_up` 解析失败时的兜底日志是否清晰，便于后续观察

---

## 九、给下一阶段（detail-3）的接口留白说明

本阶段完成后，长篇玩法在接口层面已经完整可用，但前端仍是v1.x原有的单局对话界面，没有章节感知、没有存档管理UI、没有模式区分。detail-3 需要在此基础上：
- 设计并实现选择页的「特写/长镜」模式切换入口
- 设计长篇作品的章节进度展示、章节切换过渡动效
- 评估是否需要为长篇模式的阅读流呈现（对应v1.3已定的"世界残响"视觉方向）做适配调整

本阶段不需要为此提前做任何前端实现，接口设计已经为前端预留了必要信息（`next_chapter_id`/`work_completed`等），detail-3可以直接在此基础上构建UI。