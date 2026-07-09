# 任务：优化「入戏」导演 Agent / 演员 Agent 的 Prompt 文案

用法：将本文全文复制给优化 AI，并在文末粘贴待优化的 Prompt 原文。

**硬约束：JSON 输出契约、`{{占位符}}`、system/user 职责均不可变。** 只允许优化自然语言指令。

相关路径：
- `prompts/director/system.txt`、`prompts/director/user.txt`
- `prompts/roleplay/system.txt`、`prompts/roleplay/user.txt`

---

## 一、产品与玩法背景（先读懂再改）

「入戏」：玩家与 AI 角色对话，用语言推动隐藏数值，达成胜负。

每轮流程：
1. 玩家发言
2. **导演 Agent**（裁判+调度）：读剧本背景、人设、待命中 key_points/pitfalls、当前数值与历史 → 输出结构化 JSON（命中、stat_changes、reaction、是否结束）
3. 引擎按命中区间合并数值、clamp、判定胜负/超时
4. **演员 Agent**：只负责扮演角色，消费导演的 reaction（tone/intensity/focus）生成 `emotion_tag` + `reply`

导演**绝不**说角色台词；演员**绝不**做数值裁判。

剧本侧已配置：background、objective、ai persona、emotion_vocabulary、stats、key_points、pitfalls、win/lose 等。Prompt 里通过 `{{占位符}}` 注入，运行时字符串替换。

---

## 二、当前 Prompt 文件与占位符（结构不可变）

你会收到若干 `.txt` 文件内容。常见四件套：

### 导演 system（无占位符或极少）
职责：判定命中、给增量、写 reaction、判结束；只返回 JSON。

导演输出 JSON 契约（字段名与语义必须保持）：

```json
{
  "hit_key_points": [1, 2],
  "hit_pitfalls": [1],
  "stat_changes": {"数值名": 增量整数},
  "reaction": {
    "tone": "来自情绪词表",
    "intensity": "弱/中/强",
    "focus": "≤15字聚焦点，不是台词"
  },
  "game_over": false,
  "outcome": null,
  "ending_text": null
}
```

### 导演 user（占位符必须原样保留）
`{{background}}` `{{objective}}` `{{ai_character_name}}` `{{ai_character_persona}}` `{{emotion_vocabulary}}` `{{player_character_name}}` `{{current_stats}}` `{{conversation_history}}` `{{player_message}}` `{{pending_key_points}}` `{{pending_pitfalls}}` `{{win_condition}}` `{{lose_condition}}` `{{current_turn}}` `{{max_turns}}`

### 演员 system
占位符：`{{ai_character_name}}` `{{ai_character_persona}}` `{{background}}`  
输出：`{"emotion_tag":"...","reply":"..."}`

### 演员 user
占位符：`{{conversation_history}}` `{{player_character_name}}` `{{player_message}}` `{{reaction_tone}}` `{{reaction_intensity}}` `{{reaction_focus}}` `{{emotion_vocabulary}}` `{{ai_character_name}}`

---

## 三、输出格式（最高优先级约束）

1. **按文件分别输出完整替换文本**；每个文件一个代码块，标题标明文件名（如 `director/system.txt`）。
2. **禁止改变结构契约：**
   - 不得增删/改名 JSON 输出字段（`hit_key_points`、`hit_pitfalls`、`stat_changes`、`reaction.tone|intensity|focus`、`game_over`、`outcome`、`ending_text`；演员侧 `emotion_tag`、`reply`）
   - 不得增删/改名任何 `{{占位符}}`；不得改占位符拼写
   - 不得把 system/user 职责对调；不得让导演生成台词、让演员改数值
   - 不得引入新的必须由引擎注入的变量
3. 只优化**自然语言指令的清晰度、判定严格度、语气与长度控制**；不要输出长篇原理说明（代码块外最多一句索引）。

---

## 四、调优方向（写入 prompt 的规则，而不是改 schema）

### 1）服务角色立体度（与剧本 persona 协同）

- 导演：判定时要结合人设的**核心诉求与情绪矛盾**，不要把“说了抱歉”当成命中；应要求语义真正触及 key_point description。
- 导演 `reaction`：tone 必须来自词表；focus 指向本轮情绪焦点（追问、刺痛点、戒备点），体现拉扯，而非“表示原谅”。
- 演员：用人设里的拧巴、自尊、刀子嘴等说话，避免油腻安慰腔和工具人复读。

### 2）难度与节奏（反“两句哄好”）

在导演 system 中强化（保持现有字段）：
- **严格语义命中**：擦边、空泛道歉、正确废话 → 不命中 key_points；可给很小态度分或触发 pitfalls
- 命中区间取值：敷衍取对玩家不利端；具体真诚取有利端
- 未命中时的自由 `stat_changes` 保持小幅（约 -5~+5），避免靠态度分速通
- 不要因为玩家“态度好”就提前 `game_over: win`；结束条件仍应与数值/规则一致（文案上强调：未达胜负态势时 game_over 必须为 false）

### 3）输出控制（演员侧重点）

在演员 system/user 中明确：
- **像真人即时回复**：短句为主，口语，可打断、可留白、可反问
- **长度**：通常 1–3 句，总字数宜短（建议明确上限，如中文约 40–80 字，激动时可略增但禁止小作文/条列说教）
- 禁止：旁白小说腔、心理小作文、一次倾倒全部人设、复述导演标签词（戒备/软化等）
- `emotion_tag` 只能选自词表；可以与导演 tone 不同，但必须贴合本句实际语气

### 4）整体精简

- Prompt 本身去掉重复段落；规则用短条目
- 保留判定与格式硬约束，删除空泛“请认真思考”类套话

---

## 五、自检清单

- [ ] 所有原 `{{...}}` 仍在且拼写不变
- [ ] 导演/演员 JSON 字段集合不变
- [ ] 导演仍禁止输出角色台词；演员仍禁止裁判数值
- [ ] 含“严格命中 / 反速通 / 短回复”类可执行规则
- [ ] 每个文件可直接整文件替换

---

## 六、待优化 Prompt 原文

请优化以下文件（结构与占位符锁定，只改文案质量）：

### director/system.txt

```
{{粘贴}}
```

### director/user.txt

```
{{粘贴}}
```

### roleplay/system.txt

```
{{粘贴}}
```

### roleplay/user.txt

```
{{粘贴}}
```
