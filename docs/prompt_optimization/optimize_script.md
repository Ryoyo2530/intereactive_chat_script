# 任务：优化「入戏」互动文字游戏的剧本 JSON

用法：将本文全文复制给优化 AI，并在文末粘贴待优化的剧本 JSON。

**硬约束：字段名、嵌套结构、类型均不可变。** 只允许改写自然语言内容与数值设计质量。

相关路径：示例剧本 `scripts/fanfic/fanfic_friendship_001.json`；校验 `game/content/validator.py`。

---

## 一、产品与玩法背景（先读懂再改）

「入戏」是一款 AI 互动文字游戏：玩家选剧本 → 读入场须知 → 与 AI 对手对话 → 每句话影响隐藏数值 → 数值触达胜/负条件或轮次耗尽后出结局。

双 Agent 架构：
- **导演 Agent**：不扮演角色；判断玩家是否命中 `key_points` / `pitfalls`，给出数值增量与结构化 `reaction`（tone/intensity/focus）。
- **演员 Agent**：按导演的 reaction + 角色人设生成台词与 `emotion_tag`。

剧本分两类（`origin_tag`）：
- `"影视同人"`：影视热梗，代入经典名场面（如《我的前半生》唐晶篇）
- `"你也一定遇到过"`：生活向沟通场景（恋爱/职场/社交等）

核心循环：玩家发言 → 导演判定命中与数值变化 → 演员出台词 → 数值 clamp → 检查 win/lose/超时。

**关键点机制要点：**
- `key_points` / `pitfalls` 各 id **每局只能命中一次**
- 命中时数值变化取自 `hit_stat_changes` 的区间 `[lo, hi]`（导演在区间内微调）
- 未命中时允许小幅态度反馈（约 -5~+5）
- 胜利看 `win_condition` 数值表达式，**不是**“必须点满所有关键点”（但设计上应让合理通关路径与数值倒推一致）
- `win_condition` / `lose_condition` 只支持用 `且` 连接的比较式，**不支持「或」**

---

## 二、字段说明（必须理解每个字段的用途）

| 字段 | 用途 |
|------|------|
| `id` | 唯一 snake_case id，通常与文件名一致 |
| `title` | 展示标题 |
| `origin_tag` | 仅允许 `"影视同人"` 或 `"你也一定遇到过"` |
| `theme_tags` | 从：恋爱 / 职场 / 家庭 / 友情 / 社交 选 1–2 个 |
| `teaser` | 选剧本卡片上一句话钩子（偏营销、短） |
| `player_role_hint` | 如「扮演 罗子君 · 对手 唐晶」 |
| `estimated_turns_hint` | 如「约 10-15 轮」 |
| `briefing` | 玩家可见的入场须知（不要剧透通关话术） |
| `background` | 给 LLM 的完整设定（比 briefing 更全，但仍要精炼） |
| `ai_character.name` | 对手名 |
| `ai_character.persona` | 性格、说话方式、情绪模式——导演与演员都会读 |
| `ai_character.emotion_vocabulary` | 4–6 个情绪词，供导演 tone / 演员 emotion_tag |
| `ai_character.intro` | briefing 页短介绍 |
| `player_character.name` | 玩家角色名 |
| `objective` | 玩家目标（会注入导演 prompt） |
| `stats` | 2–3 个数值；每项含 initial/min/max/direction |
| `key_points[]` | id, title, description, hit_stat_changes |
| `pitfalls[]` | 同上结构，负面触发 |
| `win_condition` / `lose_condition` | 如 `怀疑值 <= 20 且 愤怒值 <= 20` |
| `max_turns` | 超时判负 |
| `opening_line` | AI 开场白（可用括号写动作） |
| `ending_titles` | `{ "win", "lose" }` |
| `echo_phrases` | 可选；按数值名配置 up/down × small/medium/large 文案池 |

`hit_stat_changes`：值为整数，或区间 `[lo, hi]`（推荐区间）。区间语义：越真诚具体 → 取对玩家更有利的一端。

---

## 三、输出格式（最高优先级约束）

1. **只输出一份完整、可直接替换的 JSON**（可包在 `json` 代码块里）。不要输出解释、diff、字段清单。
2. **字段名、嵌套结构、类型必须与输入剧本兼容**——可改写字段**内容**，但：
   - 不得改名、不得改层级、不得新增引擎不认识的顶层字段
   - 不得删除输入里已有的顶层字段（若输入有 `echo_phrases`/`briefing`/`intro` 等，必须保留）
   - `origin_tag` 枚举值不得写错（禁止 `"原创剧情"`）
   - `stats` 的 key、`key_points`/`pitfalls` 的 id 类型风格与输入保持一致（生产剧本 id 多为数字）
   - `win_condition`/`lose_condition` 语法：`数值名 运算符 整数`，多条件只用 `且`
3. 数值名若调整，必须在 stats / key_points / pitfalls / win/lose / echo_phrases 中**全局一致**。

---

## 四、内容调优方向（按此改写）

### 1）角色立体度（影视同人尤其重要）

- 在 `background` 中补充**必要上下文**（人物关系、冲突起因、本场戏的情绪起点），但避免百科式冗长。
- 强化 `ai_character.persona` / `intro`：写清**核心诉求、性格矛盾、情感拧巴点**，而不是“理性、冷静、会软化”这种扁平标签。
- 参考标准（以《我的前半生》唐晶为例，优化同类角色时对齐这个深度）：
  - 事业心重、自尊高、独立自强
  - 刀子嘴豆腐心；安全感缺失
  - 对贺涵感情拧巴；本场戏交织失望、震惊、被背叛的痛苦、克制的怒、对友情的珍视等复杂情绪
- `emotion_vocabulary` 要能覆盖这场戏的情绪弧线（防御 → 拉扯 → 可能软化/爆发），词要贴角色，不要通用鸡汤词。

### 2）玩法难度与节奏（制造拉扯感）

- **禁止**“道歉两句就哄好”：key_points 必须要求玩家触及**具体、可判定**的内容（界限、尊重、承认伤害、理解诉求等），description 写清“说什么才算命中”，避免「表达真诚」这类模糊词。
- 按角色立体度设计得分/扣分：
  - 表面道歉、甩锅、轻描淡写、把对方当情绪工具 → 应进 `pitfalls` 或几乎不得分
  - 真正命中角色痛点/诉求 → 才给有效降压
- **数值系统控制在 2–3 个**，名称要精准映射复杂心情（如怀疑/愤怒/委屈/隔阂），不要堆无关维度。
- 数值倒推：全部合理命中 key_points 且不踩大坑 ≈ 刚好能赢；踩坑或敷衍应明显拉长对局或推向失败。
- initial 不要过低；单次命中降幅不要过大导致 2–3 轮通关；保留多轮拉扯空间。
- pitfalls 要“像真人会踩的雷”，与角色自尊/安全感/信任相关。

### 3）输出控制（影响演员表现的字段）

- `persona`、`opening_line` 要暗示**短句、口语、克制**，像真人对话，避免长篇独白气质。
- `opening_line` 有场景感即可，控制长度；不要写成小作文。

### 4）整体精简

- 删冗余形容词与重复信息；`briefing`（给玩家）与 `background`（给 LLM）分工清晰、互不灌水。
- key_points 建议 3 个左右，pitfalls 2 个左右；title 短、description 具体。
- 保留戏剧张力，去掉不影响判定与人设的废话。

---

## 五、自检清单（输出前默默过一遍）

- [ ] JSON 可解析；结构与输入兼容
- [ ] origin_tag / 条件语法合法
- [ ] 2–3 个 stats，名称与全局引用一致
- [ ] key_points description 可被导演语义判定；非“道歉即可”
- [ ] 数值区间与 win/lose/max_turns 倒推合理，有拉扯
- [ ] persona 有核心诉求与情绪复杂度（同人戏有上下文）
- [ ] 文案整体精炼，opening_line 不像长独白

---

## 六、待优化剧本

请优化下面这份剧本 JSON（保持结构兼容，按第四节方向提升质量）：

```json
{{在此粘贴待优化的 script JSON}}
```
