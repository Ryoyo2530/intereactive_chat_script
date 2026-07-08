# 入戏 v1.0-chat_script_prompt_optimization —— 导演Prompt结构化 + 剧本关键点系统

## 本次改动目标

1. 将导演 Agent 的 `reaction_instruction`（自由文本大段描述）改为**结构化字段**（tone / intensity / focus），减少解析歧义，也让演员 Agent 消费起来更稳定。
2. 引入**剧本关键点系统**（key_points / pitfalls），让"玩家需要说到什么内容"由剧本作者（你）显式配置，而不是完全依赖导演LLM临场自由判断，从而让剧情走向和胜负判定更可控、更可复现。

本次改动**不涉及**难度分级、提示机制、开发者面板——这些仍按原路线图排在 v1.1/v1.2。

---

## 一、为什么要做关键点系统

当前导演完全靠自由判断数值变化，存在两个问题：
- 同样的玩家发言，不同轮次/不同上下文下导演给出的数值增量可能不一致，胜负条件的"可复现性"差
- 你作为剧本作者，无法精确控制"必须让玩家说到什么才能推进剧情"，只能通过调整prompt间接影响，效果不直接

关键点系统把"剧情应该如何被推动"显式写进剧本配置，导演的职责从"自由裁量"收窄为"识别玩家发言是否命中了预设的内容点，命中了就按预设规则给分"。这样：
- 剧本作者可以精确设计"过关路径"（比如必须依次或不分先后地让玩家提到三个关键内容点）
- 也可以设计"减分陷阱"（比如玩家说了推卸责任的话，直接扣大量好感度）
- 导演LLM的判断空间从"给多少分"收窄为"判断是否语义命中"，更稳定

---

## 二、剧本 JSON Schema 扩展

在 `scripts/example_script.json` 中新增 `key_points` 和 `pitfalls` 字段，并新增角色情绪词表 `emotion_vocabulary`：

```json
{
  "id": "example_script",
  "title": "我的前半生 - 唐晶篇",
  "background": "...",
  "ai_character": {
    "name": "唐晶",
    "persona": "...",
    "emotion_vocabulary": ["戒备", "软化", "追问", "爆发", "冷静", "释然"]
  },
  "player_character": { "name": "罗子君" },
  "objective": "解释清楚罗子君和贺涵的关系，让唐晶原谅自己",
  "stats": {
    "怀疑值": { "initial": 60, "min": 0, "max": 100 },
    "愤怒值": { "initial": 70, "min": 0, "max": 100 }
  },
  "key_points": [
    {
      "id": "explain_boundary",
      "description": "玩家明确说明自己和贺涵之间保持了界限，没有越界行为",
      "hit_stat_changes": { "怀疑值": -20, "愤怒值": -10 }
    },
    {
      "id": "acknowledge_friendship",
      "description": "玩家主动承认唐晶和贺涵之间的关系值得被尊重，表达对这段友情的重视",
      "hit_stat_changes": { "愤怒值": -20 }
    },
    {
      "id": "mention_career_respect",
      "description": "玩家提到理解并尊重唐晶的事业和独立性，而非把她当作威胁",
      "hit_stat_changes": { "怀疑值": -15 }
    }
  ],
  "pitfalls": [
    {
      "id": "blame_deflect",
      "description": "玩家试图把责任推给唐晶或第三方，而非正面回应质疑",
      "hit_stat_changes": { "愤怒值": 20 }
    },
    {
      "id": "vague_excuse",
      "description": "玩家用含糊其辞的借口搪塞，没有实质回应问题",
      "hit_stat_changes": { "怀疑值": 10 }
    }
  ],
  "win_condition": "怀疑值 <= 20 且 愤怒值 <= 20",
  "lose_condition": "愤怒值 >= 100",
  "max_turns": 15,
  "opening_line": "..."
}
```

**设计说明**：
- `key_points` / `pitfalls` 的 `hit_stat_changes` 是命中后**直接生效**的预设增量，不再依赖导演随意发挥
- `emotion_vocabulary` 提供给导演一个受限的情绪词表，避免 `reaction.tone` 输出五花八门难以在前端/演员prompt中统一处理
- 关键点数量、内容、命中后的分值完全由你控制，这是本次改动让你获得的核心可配置能力
- 胜利条件依然可以保留纯数值判断（`win_condition`），关键点系统是**驱动数值变化的手段**，不是替代胜负判断本身；如果你后续想要"必须命中全部关键点才能赢"这种玩法，可以在 v1.1 再加 `win_requires_key_points` 字段，本次先把关键点驱动数值这一层做稳

---

## 三、Session 状态扩展

`game/session.py` 中每个session需要新增字段跟踪"已命中的关键点/减分点"，避免同一内容点被重复触发计分：

```python
# session 状态新增字段（描述行为，不要求具体实现）
# - hit_key_point_ids: set[str]   已命中的key_point id集合
# - hit_pitfall_ids: set[str]     已命中的pitfall id集合
```

每轮调用导演前，从剧本的完整 `key_points`/`pitfalls` 列表中**过滤掉已命中的**，只把"待命中列表"传给导演（见下方prompt模板变化）。导演返回的 `hit_key_points`/`hit_pitfalls` 在engine层执行后，需要：
1. 对应的 id 加入 session 的已命中集合
2. 对应的 `hit_stat_changes` 累加到当前数值（而不是使用导演自己在stat_changes里给的数值——两者应保持一致，engine层以关键点预设值为准，见下方"数值计算优先级"）

### 数值计算优先级

引擎层合并本轮数值变化时，遵循：
1. 先应用所有命中的 `key_points`/`pitfalls` 对应的 `hit_stat_changes`（累加，允许导演在其基础上做±30%微调，见system prompt规则）
2. 未命中任何关键点的"基础态度反馈"部分（导演在stat_changes里给出的、不对应任何关键点id的小额增量）也一并应用
3. 最终对每个数值做 min/max clamp

---

## 四、Prompt 模板变化

### `director_system.txt`
替换为本次给出的优化版 system prompt（见对话中已给出的完整文本），核心变化：结构化 `reaction` 字段、关键点判定规则说明。

### `director_user.txt` 新增变量

需要新增以下占位符，均由 `engine.py` 在调用前组装：

```
【本角色情绪词表】
{{emotion_vocabulary}}

【待命中关键点】
{{pending_key_points}}
<!-- 格式示例：
- [explain_boundary] 玩家明确说明自己和贺涵之间保持了界限，没有越界行为
- [acknowledge_friendship] 玩家主动承认唐晶和贺涵之间的关系值得被尊重... -->

【待命中减分点】
{{pending_pitfalls}}
```

已命中的关键点/减分点**不再出现**在这两个列表中，`prompt_manager.py` 组装时需要用 session 里的 `hit_key_point_ids`/`hit_pitfall_ids` 过滤剧本原始列表。

### `roleplay_user.txt` 调整

原来消费一段自由文本的 `reaction_instruction`，改为消费结构化字段：

```
【本轮反应指导】
情绪基调：{{reaction_tone}}
情绪强度：{{reaction_intensity}}
回应聚焦：{{reaction_focus}}
```

演员 Agent 的 system prompt 里应同步说明："请根据以上三个维度的指导生成台词，不要直接复述这些标签词，而是通过语气、用词、句式体现出对应的情绪和聚焦点。"

---

## 五、engine.py 编排逻辑调整

1. 读取 session 当前状态（历史、数值、已命中关键点/减分点集合、轮次）
2. 从剧本中过滤出待命中的 `key_points`/`pitfalls`，组装导演prompt
3. 调用导演，得到 `hit_key_points`、`hit_pitfalls`、`stat_changes`、`reaction`、结束判定
4. 按"数值计算优先级"合并所有数值变化，更新session的数值状态和已命中集合
5. 若 `game_over=false`：将 `reaction` 三个字段传给演员prompt，调用演员得到台词
6. 存储历史，返回前端

---

## 六、验证要求

1. 针对新增的 `example_script.json` 关键点配置，构造几组测试对话，人为发送明确命中某个关键点的话术，确认：
   - 该关键点id出现在导演返回的 `hit_key_points` 中
   - 对应的 `hit_stat_changes` 被正确应用
   - 同一关键点在后续轮次中不会被重复命中（即使玩家又提了一遍类似内容）
2. 构造命中 `pitfalls` 的负面话术，确认扣分逻辑生效
3. 验证 `reaction` 结构化字段被正确传递给演员prompt，且演员输出的台词风格确实随 `tone`/`intensity`/`focus` 变化而有可观察的差异（可以人工用同一句玩家发言，手动构造不同的reaction值传给演员agent做对比测试）
4. 确认所有关键点耗尽后（全部命中或轮次耗尽），游戏仍能正常触发胜负判定，不会因为"待命中列表"为空导致prompt异常
5. 部署到 Render 验证公网行为一致

---

## 七、给你（剧本作者）的配置建议

- 关键点数量建议控制在 **3-5 个**，太多会导致玩家在有限轮次内难以覆盖全部，太少则关键点系统起不到收紧剧情的作用
- 关键点的 `description` 要写得具体、可判定，避免过于抽象（比如"表达真诚"就很难让导演准确判定命中与否，"明确说明自己和贺涵之间保持了界限"就是可判定的）
- pitfalls 不是必须的，但建议至少设计1-2个，用来防止玩家用敷衍/回避的方式"混过"游戏
- `hit_stat_changes` 的数值设计建议让"全部命中key_points + 不踩pitfalls"刚好能达到win_condition，这样你可以用这套数值直接反推剧本的难度曲线

---

## 八、演员 Agent 情绪标签输出 + 前端展示

### 需求

演员 Agent 在生成台词的同时，需要**额外输出一个情绪标签**，用于前端在对话气泡旁展示角色当前情绪状态（如小图标或文字徽章），让玩家更直观地感知角色反应，而不需要单纯从文字里揣摩。

### 演员 Agent 输出格式变更

```json
{
  "reply": "角色本轮说的话，纯对话内容",
  "emotion_tag": "戒备"
}
```

- `emotion_tag` **必须**从剧本的 `emotion_vocabulary`（已在关键点系统改动中加入剧本schema）中选择一个词，不允许自由创造新词——这样前端才能用有限的映射表做展示，不需要处理任意文本。
- `emotion_tag` 由演员 Agent 自主判断并输出，**不要求**与导演给出的 `reaction.tone` 完全一致：导演的 `tone` 是"指导角色该往哪个方向反应"，而 `emotion_tag` 是"角色这句台词实际读起来是什么情绪"，两者通常接近但允许演员根据台词最终呈现效果做更细致的判断（比如导演指导是"追问"，但演员写出的台词里情绪已经升级到"愤怒"，此时应如实标注"愤怒"）。

### Prompt 模板变化

`roleplay_system.txt` 中需要补充说明：

```
你在生成台词的同时，需要判断这句台词实际传递出的情绪，从剧本提供的情绪词表中选择一个最贴切的词，填入 emotion_tag 字段。只允许从词表中选择，不要创造词表之外的情绪词。
```

`roleplay_user.txt` 中需要新增变量传入词表，供演员参考：

```
【可选情绪标签】
{{emotion_vocabulary}}
```

### 接口层变化

`POST /api/session/message` 的返回体新增 `emotion_tag` 字段：

```json
{
  "reply": "...",
  "emotion_tag": "戒备",
  "stats": {...},
  "turn": 4,
  "game_over": false,
  "outcome": null,
  "ending_text": null
}
```

### 前端展示要求

- 在AI角色消息气泡旁（角色名同一行或紧邻位置）展示当前 `emotion_tag`，用小号文字徽章呈现（背景用剧本情绪词表对应的语义色，如果剧本未提供颜色映射则统一用中性灰底），不需要做成图标，文字徽章即可满足demo阶段需求
- 情绪标签变化时可以有简单的淡入效果，不需要复杂动画
- 是否展示情绪标签应做成可关闭的选项（比如一个小开关或前端配置项），因为持续暴露"角色情绪机制"可能会一定程度影响沉浸感，部分玩家可能更喜欢纯靠文字揣摩——demo阶段可以先默认展示，但预留后续可关闭的扩展点，不需要本次就实现开关UI，只需在前端渲染逻辑上做到"情绪标签的渲染是独立于消息渲染的一个模块"，方便以后拆出开关

### 验证要求

1. 确认演员 Agent 返回的 `emotion_tag` 始终是剧本 `emotion_vocabulary` 词表内的词，构造测试确认解析容错（若LLM返回词表外的词或格式错误，前端应有默认兜底展示，比如显示"..."或不展示标签，而不是报错崩溃）
2. 确认前端气泡渲染中，情绪标签能正确显示在对应消息旁，且和该轮对话是绑定的（不会出现上一轮的标签残留展示在新消息上）
3. 人工检查几轮对局，确认 `emotion_tag` 的变化和台词内容读起来是相符的（比如标注"软化"的台词读起来确实语气缓和），如果发现明显不符，可以回头调整 `roleplay_system.txt` 中关于emotion_tag判断的措辞