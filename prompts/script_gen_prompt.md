# 入戏剧本生成 Prompt

你需要生成符合以下 schema 的剧本 JSON 文件。游戏机制：玩家与一个 AI 角色进行对话，每轮导演 LLM 判断玩家是否命中预设关键点或触发减分陷阱，影响数值；演员 LLM 根据数值状态生成角色台词。游戏以数值达到胜负条件或轮次耗尽结束。

---

## JSON Schema（严格遵守，所有字段必填）

```json
{
  "id": "snake_case_unique_id",
  "title": "剧本标题（简短，带氛围感）",
  "origin_tag": "影视同人 或 原创剧情",
  "theme_tags": ["从以下选1-2个: 恋爱 / 职场 / 家庭 / 友情 / 社交"],
  "teaser": "一句话简介，给玩家看的，营销向，20字以内，勾起好奇心",
  "player_role_hint": "扮演 XX · 对手 YY",
  "estimated_turns_hint": "约 N-M 轮",
  "background": "详细剧本背景，给 LLM 看的完整设定，100-200字",
  "ai_character": {
    "name": "角色名",
    "persona": "角色性格、说话方式、情绪反应模式，100字左右",
    "emotion_vocabulary": ["4-6个情绪词，从负面到正面排列，与角色性格匹配"]
  },
  "player_character": { "name": "玩家角色名（可以是「你」）" },
  "objective": "玩家目标，一句话",
  "stats": {
    "数值名A": { "initial": 60, "min": 0, "max": 100, "direction": "lower_is_better" },
    "数值名B": { "initial": 55, "min": 0, "max": 100, "direction": "lower_is_better" }
  },
  "key_points": [
    {
      "id": 1,
      "title": "关键点名称（4字以内）",
      "description": "具体可判定的行为描述，说明玩家需要说什么才算命中，30-50字",
      "hit_stat_changes": { "数值名": [-25, -15] }
    }
  ],
  "pitfalls": [
    {
      "id": 1,
      "title": "陷阱名称",
      "description": "玩家说了什么触发此陷阱，30-50字",
      "hit_stat_changes": { "数值名": [15, 25] }
    }
  ],
  "win_condition": "数值名A <= 20 且 数值名B <= 20",
  "lose_condition": "数值名A >= 100",
  "max_turns": 12,
  "opening_line": "角色第一句话，带场景描写，有代入感，50字以内",
  "ending_titles": { "win": "胜利标题", "lose": "失败标题" }
}
```

---

## 设计要求

- `key_points` 3个，`pitfalls` 2个
- 全部命中 key_points + 不踩 pitfalls = 刚好能达到 win_condition（数值倒推验证）
- `description` 要写得具体可判定，避免模糊词（「表达真诚」太模糊，「玩家明确说出X具体行为」才合格）
- `emotion_vocabulary` 6个词，按角色从最防御到最开放的情绪顺序排列
- `hit_stat_changes` 用范围 `[lo, hi]`，允许导演在区间内微调
- `opening_line` 要有场景感，用括号写动作/环境描写，然后是角色台词

---

## 待生成剧本

### 剧本一：吵架模拟器

- `origin_tag`: `"原创剧情"`，`theme_tags`: `["恋爱"]`
- 核心玩法：你和对象吵了一架，你需要在对话中先让对方冷静下来，再修复关系
- 对象性格：容易上火但其实很在乎你，说话直接，不喜欢被敷衍
- 避免与「忘记纪念日」场景重复，选择新的冲突起点（如：你又一次答应了某件事却没做到；或者你说了一句伤人的话没意识到）

### 剧本二：职场模拟器·向上管理

- `origin_tag`: `"原创剧情"`，`theme_tags`: `["职场"]`
- 核心玩法：你提出了一个新项目方案，需要说服老板批准立项
- 与「涨薪谈判」区分：这次是创意/方案说服，而非待遇谈判
- 老板性格：稳健、风险厌恶，更关注 ROI 和执行可行性，不喜欢宏大叙事

---

请输出两个完整的 JSON，每个独立代码块，不需要额外说明。
