# 入戏 v2.0.detail-1 —— 存储迁移 + 数据模型落地

> 本文档是 v2.0 总纲（`overall.md`）下的第一份可执行指令文档，对应总纲中 v2.0.1+v2.0.2 合并阶段。执行完本文档后，应达到：内容资产持久化到数据库、重启/重新部署不再丢失数据、v1.x已有剧本迁移为新的work数据模型且行为不变。**本阶段不做长篇玩法本身的游玩逻辑**（章节推进/分支判定留给 detail-2），只做数据层。

---

## 一、本阶段目标

1. 引入 Supabase（Postgres）作为内容资产的持久化层，替代当前"本地文件系统 + 手动导出"方案
2. 落地统一的 `work`/`chapter`/存档 数据模型（详见第三节），短局与长篇共用同一套结构
3. 将 `scripts/*.json` 中现有的所有剧本，迁移为 `type: "short_form"` 的 work（单章节封装），**内容不变，只改数据结构位置**
4. dev模式的保存/发布操作，从"写文件"改为"写数据库"，改动立即生效且跨部署持久
5. 保证迁移完成后，玩家端现有的完整对局体验（选剧本→对话→触发结局）与迁移前**完全一致**

## 二、本阶段明确不做

- 不做多章节游玩逻辑、flag驱动的分支判定、`ai_choice` 机制的实际调用（这些是detail-2的范围，本阶段只把承载这些概念的表结构建好）
- 不做产品层UI改动（模式切换入口、长篇卡片等留给detail-3）
- 不接入多模态资源存储（Supabase Storage先不用）
- 不做flag的删改能力（v2.0范围内flag只增，本阶段甚至不会有实际的flag写入场景，因为短局迁移出来的work不涉及flag）

---

## 三、数据模型（Postgres 表结构）

以下为建表规范，字段类型和约束请按实际Supabase Postgres语法实现，命名统一用snake_case。

### 3.1 `works` 表（作品级）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | text, primary key | 作品唯一id，沿用原剧本id即可（迁移时保持不变） |
| `type` | text | `short_form` / `long_form`，本阶段迁移出的数据全部为 `short_form` |
| `title` | text | |
| `origin_tag` | text | 沿用v1.1定义 |
| `theme_tags` | jsonb | 字符串数组 |
| `teaser` | text | |
| `player_role_hint` | text | |
| `estimated_turns_hint` | text | |
| `stats_schema` | jsonb | 作品级数值维度定义，结构：`{ "维度名": {"initial":.., "min":.., "max":.., "label":..} }` |
| `chapter_ids` | jsonb | 该作品包含的章节id清单，短局固定为长度1的数组 |
| `entry_chapter_id` | text | 入口章节id |
| `status` | text | `draft` / `published`，对应dev模式的草稿/发布状态 |
| `created_at` / `updated_at` | timestamptz | |

### 3.2 `chapters` 表（章节级）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | text, primary key | 章节唯一id |
| `work_id` | text, foreign key → works.id | |
| `title` | text | |
| `background` | text | |
| `ai_character` | jsonb | `{name, persona, emotion_vocabulary}` |
| `player_character` | jsonb | `{name}` |
| `opening_line` | text | |
| `max_turns` | int | |
| `key_points` | jsonb | 数组，结构沿用v1.0原有 `key_points` |
| `pitfalls` | jsonb | 数组，结构沿用v1.0原有 `pitfalls` |
| `flags_read` | jsonb | 字符串数组，本阶段迁移的短局数据全部为空数组 |
| `flags_write` | jsonb | 数组，本阶段迁移的短局数据全部为空数组 |
| `exits` | jsonb | 出口定义数组。短局的exits固定为单条，直接对应原有的 `win_condition`/`lose_condition` 逻辑（见3.3处理方式） |
| `created_at` / `updated_at` | timestamptz | |

**短局迁移时 `exits` 的处理方式**：不强行套用detail-2才会用到的 `hard_condition`/`ai_choice` 结构，短局章节的 `exits` 字段本阶段写成一个占位标记即可，例如：
```json
{ "type": "terminal", "win_condition": "...", "lose_condition": "..." }
```
即原样保留v1.0的胜负条件字符串，只是换了存放位置，不引入分支树逻辑。真正的 `hard_condition`/`ai_choice` 出口类型解析在detail-2实现。

### 3.3 `saves` 表（存档，短局场景下等价于v1.0的session）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | text/uuid, primary key | |
| `work_id` | text | |
| `current_chapter_id` | text | |
| `current_turn` | int | |
| `stats` | jsonb | 当前数值状态 |
| `flags` | jsonb | 本阶段短局场景下恒为空对象 `{}` |
| `chapter_summaries` | jsonb | 本阶段短局场景下恒为空数组 `[]` |
| `hit_key_point_ids` | jsonb | 字符串数组 |
| `hit_pitfall_ids` | jsonb | 字符串数组 |
| `conversation_history` | jsonb | 当前章节对话历史 |
| `game_over` | boolean | |
| `outcome` | text | `win`/`lose`/null |
| `created_at` / `updated_at` | timestamptz | |

**说明**：本阶段 `saves` 表实际承担的就是原来 `game/session.py` 里内存态session的持久化版本。是否每局都落库、还是仅在需要"断线续玩"时才落库，由实现时视性能取舍决定，但表结构按此设计，为detail-2的长篇存档/读档做好准备。

---

## 四、后端改动范围

### 4.1 新增数据访问层

在 `game/content/` 下新增（或改造原有 `script_repository.py`）：
- `work_repository.py`：负责 works/chapters 表的读写，替代原先直接读 `scripts/*.json` 文件的逻辑
- `save_repository.py`：负责 saves 表的读写

`script_repository.py` 原有的对外接口签名尽量保持不变（如 `get_script(id)`、`list_scripts()`），内部实现从"读文件"改为"读数据库并组装成原有返回结构"，这样上层 `engine.py`/`validator.py`/路由层的调用代码改动可以降到最低。

### 4.2 dev模式改动

- 所有 `/api/dev/scripts/*` 的保存/发布接口，内部改为写 `works`/`chapters` 表，不再写文件系统
- 校验逻辑（`validator.py`）不变，只是校验完成后的持久化目标从文件改为数据库
- 原有的"导出全部剧本"/"下载单个剧本"功能保留，但导出内容从"打包scripts目录的json文件"改为"从数据库查询后动态组装成json"，供下载

### 4.3 环境配置

新增环境变量（Render部署时配置）：
- `SUPABASE_URL`
- `SUPABASE_KEY`（建议用service role key，仅后端持有，不暴露给前端）

---

## 五、数据迁移步骤

1. 编写一次性迁移脚本（可临时放在 `scripts/migrate_to_supabase.py`，迁移完成验证无误后可删除或归档，不进入正式代码路径）
2. 脚本逻辑：
   - 遍历现有 `scripts/*.json`
   - 每个剧本文件拆分为一条 `works` 记录（`type: "short_form"`）+ 一条 `chapters` 记录（该作品唯一的章节，`id` 可与作品id保持一致或加后缀如 `{script_id}_main`）
   - 原剧本的 `background`/`ai_character`/`key_points`/`pitfalls`/`win_condition`/`lose_condition`/`max_turns`/`opening_line` 等字段按第三节表结构对应写入 `chapters` 表
   - 原剧本的 `origin_tag`/`theme_tags`/`teaser`/`player_role_hint`/`estimated_turns_hint`/`stats`（数值定义）等字段写入 `works` 表（数值定义对应 `stats_schema`）
3. 迁移脚本执行后，**不删除原有 `scripts/*.json` 文件**，作为迁移失败时的回滚依据保留一段时间，待验证稳定后再决定是否清理
4. prompt模板（`prompts/*.txt`）本阶段**不迁移进数据库**，仍保留文件形式——prompt模板改动频率低、且属于"调优时改文字"的场景，文件+git版本管理本身就是合适的持久化方式；本阶段迁移范围只针对"剧本内容"这一类高频运行时更新的资产（如未来确有需要迁移prompt，作为独立事项另行评估，不在本阶段范围内）

---

## 六、验证要求

1. **持久化验证（核心）**：在Render上完成部署后，通过dev模式编辑并保存一个剧本字段（如改一句teaser），刷新玩家端确认改动立即生效；随后**主动触发一次重新部署**（如推送一次无关代码改动），部署完成后再次检查该剧本，确认改动**未丢失**——这是本阶段最核心的验收标准，直接对应总纲中"存储止血"的目标
2. **迁移正确性验证**：迁移完成后，逐一核对迁移前后的剧本内容（至少覆盖当前所有已有剧本），确认字段无丢失、无错位
3. **行为一致性验证**：玩家端完整走一局（选剧本→对话→触发结局），确认与迁移前行为完全一致；dev模式的登录、剧本编辑保存、试玩验证、prompt预览/发布等功能逐项跑一遍，确认无回归
4. **回滚可行性验证**：确认原始 `scripts/*.json` 文件仍完整保留，且理论上可以在数据库出现问题时手动回退到文件读取逻辑（不要求实际实现自动回退开关，只需确认数据未被破坏性删除）
5. 检查环境变量缺失/数据库连接失败时的报错是否清晰可读，避免线上故障时难以排查

---

## 七、给下一阶段（detail-2）的接口留白说明

本阶段完成后，`chapters` 表已包含 `flags_read`/`flags_write`/`exits` 字段，但这些字段在短局场景下均为空值或占位结构。detail-2 开始时，需要：
- 实现真正的多章节 `work`（`type: "long_form"`）创建与编辑
- 实现 `exits` 中 `hard_condition`/`ai_choice` 两种类型的解析与判定逻辑
- 实现 `saves` 表中 `flags`/`chapter_summaries` 的实际写入与跨章节引用

本阶段不需要为此额外做任何提前实现，只需确保表结构字段已经预留到位（第三节已覆盖），detail-2可以直接在此结构上扩展，无需改表结构本身。