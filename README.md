# 入戏

> 用对话改写剧情走向的 AI 文字游戏

选剧本 → 读入场须知 → 开口说话 → 数值涨跌 → 触发结局

**公网体验：** https://ruxi.onrender.com

---

## 界面预览（v1.3 · Echoes 阅读流）

v1.3 起，对局页从「聊天气泡」改为 **Echoes 阅读流**：纸感排版、无气泡、角色名前缀、玩家竖线区分、数值变化时浮现 Echo 卡片。

![Echoes 对局页示意](docs/%20v1.0/ui_screenshots/echoes_gameplay_v1.3.png)

| 区域 | 说明 |
|------|------|
| 章节头 | 剧本标题 + 轮次；可展开/收起背景与角色卡 |
| 世界状态 | 数值名 + 轨道圆点 + 数字（如「怀疑值 60」） |
| 阅读流 | `唐晶：` / `罗子君：` 前缀对白；情绪标签（如「戒备」）在台词上方 |
| Echo 卡片 | 数值 \|Δ\| ≥ 5 或命中关键点时出现；文案来自模板池（非 LLM） |
| 输入区 | 底部独立面板，与正文阅读流视觉分离 |

静态 Concept Demo（假数据、不接后端）：http://localhost:8000/concept/echoes_demo.html

---

## 玩法简介

1. **选剧本** — 从「影视热梗」或「你也一定遇到过」两大分类中挑一个场景
2. **读须知** — 了解你的目标和胜负条件
3. **认识对手** — 查看 AI 角色介绍；生活剧本可自定义对手的名字和性格
4. **开始对话** — 用文字说服、安抚或博弈，每句话都会影响隐藏数值
5. **等待结局** — 数值达到胜利/失败阈值时触发对应结局

### 剧本分类

| 分类 | 副标题 | 内容 |
|------|--------|------|
| 影视热梗 | 这一世由你夺回一切 | 代入影视角色，重演经典名场面 |
| 你也一定遇到过 | 如何炼就一张好嘴 | 职场、恋爱、社交，练习真实沟通场景 |

---

## 本地运行

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 填入 LLM 与开发者密码（见下文）
uvicorn main:app --reload
```

| 地址 | 说明 |
|------|------|
| http://localhost:8000 | 玩家端（配置了邀请码池时需先输入邀请码） |
| http://localhost:8000/dev | 开发者模式（需 `DEV_MODE_PASSWORD`） |

---

## 模型配置

### 玩家端

两种方式二选一：

**环境变量**（推荐用于部署）— 在 `.env` 中填写：

```env
LLM_PROVIDER=doubao        # doubao / openai / custom
LLM_API_BASE=https://...
LLM_API_KEY=your-key
LLM_MODEL=model-id
LLM_TIMEOUT_SECONDS=40
DEV_MODE_PASSWORD=...      # 开发者模式
INVITE_CODE=...            # 玩家端单一邀请码（留空关闭；换码即作废全部旧 cookie）
SESSION_TTL_MINUTES=30
SESSION_MAX_CONCURRENT=200
SESSION_HARD_MAX_TURNS=50
```

邀请码：Render / `.env` 配置一个 `INVITE_CODE` 即可。全体朋友共用；想作废时改掉该变量重新部署。

**网页配置**（适合访客自带 Key）— 玩家端「模型配置」Tab 填写并保存，Key 存于浏览器 localStorage。

### 开发者模式

在 **LLM 调试** 工作区可单独配置导演 / 演员模型（Provider、API Base、Key、Model），支持「同一模型」或分模型调试，配置保存在浏览器 localStorage（`ruxi_dev_llm_config`）。试玩验证时会使用此处的配置。

---

## 开发者模式（/dev）

面向内容迭代：在线编辑剧本与 Prompt，在发布前验证效果，无需每次改 JSON 都走 git push + 重新部署。

> 需在 `.env` 设置 `DEV_MODE_PASSWORD`。保存并发布后的剧本会**立即对线上玩家生效**；Render 免费层重启后文件系统会重置，重要改动请用「导出全部」备份并提交到 Git。

### 两个工作区

顶部切换 **剧本编辑** / **LLM 调试**，职责分离：

| 工作区 | 功能 |
|--------|------|
| **剧本编辑** | 剧本列表、JSON 编辑器、假设路径计算器、试玩验证 |
| **LLM 调试** | LLM 模型配置、导演/演员 Prompt 模板编辑与渲染预览 |

### 草稿与发布

剧本与 Prompt 均支持三层版本：

1. **编辑区** — 当前正在改的内容  
2. **Save Draft** — 写入服务端缓冲区（`dev_drafts/`，不进入 git）  
3. **保存并发布** — 覆盖生产版本（`scripts/*.json` 或 `prompts/`），并清除对应草稿  

试玩验证默认优先使用 **已 Save Draft 的缓冲区**（剧本草稿 + Prompt 草稿），可对比生产版 diff（红删绿增）。

### 剧本编辑

- 左侧按分类展示剧本列表（未保存草稿有琥珀色圆点）
- **编辑器** — JSON 文本编辑 + 字段说明侧栏；Save Draft / 对比生产版 / 保存并发布
- **假设路径** — 勾选关键点/减分点，静态估算数值走向与胜负（不调用 LLM）
- **试玩验证** — 对当前选中剧本跑完整对局；每轮可展开调试信息（导演/演员 JSON、原始 Prompt、TTFT/耗时、Token、模型名）；右侧数值节奏看板；可导出本局调试记录 JSON

### LLM 调试

- **模型配置** — 导演与演员 Agent 模型
- **Prompt 模板** — 编辑 `director/system.txt`、`director/user.txt`、`roleplay/system.txt`、`roleplay/user.txt`；选择剧本 + 示例玩家发言 → **渲染预览**（查看变量填充后的完整 Prompt）

### 其他

- 上传 / 下载单个剧本或导出全部 zip
- 新建剧本（内置 JSON 模板）
- Schema 校验在**保存并发布**时执行；错误阻止发布，警告允许发布

详细规格见 [`docs/ v1.0/design_doc_v1.2.md`](docs/%20v1.0/design_doc_v1.2.md) 与 [文档结构](#文档结构docs) 一节。

---

## 技术架构

- **后端** — FastAPI + Python；路由拆分至 `routers/`；玩家消息支持 SSE 流式输出
- **前端** — 原生 HTML / CSS / JS + **Alpine.js**（本地托管）；对局页采用 Echoes 阅读流（`static/echoes/`）
- **双 LLM Agent**
  - **Director** — 判定关键点/减分点、数值变化、结构化 reaction、胜负
  - **Roleplay** — 生成角色台词与 `emotion_tag`（受剧本情绪词表约束）
- **Echo 卡片文案** — 前端模板池（`echo_phrases` 可选字段 + 通用兜底），不由 LLM 生成
- **剧本** — `scripts/fanfic/`、`scripts/original/` 下的 JSON；运行时经 `game/content/script_repository` 加载，dev 保存后即时生效
- **Prompt** — `prompts/director/`、`prompts/roleplay/` 模板，由 `game/prompts/manager` 渲染

---

## 项目结构

```
intereactive_chat_script/
├── main.py                      # FastAPI 入口：挂载 routers + 静态资源
├── requirements.txt
├── render.yaml                  # Render 部署配置
├── .env.example                 # 环境变量模板（LLM_*、DEV_MODE_PASSWORD、INVITE_CODE）
│
├── routers/                     # API 路由（由 main.py 挂载）
│   ├── player.py                # 玩家端：剧本、对局、首页
│   ├── access.py                # 玩家端：邀请码校验
│   ├── dev_scripts.py           # dev：登录、剧本 CRUD、导入导出
│   ├── dev_drafts.py            # dev：草稿管理、对比
│   ├── dev_prompts.py           # dev：Prompt 草稿/发布/预览
│   ├── dev_simulate.py          # dev：试玩 start/message
│   └── dev_stats.py             # dev：轻量运行指标
│
├── game/                        # 后端核心逻辑
│   ├── access.py                # 单一共享邀请码 + 内存运行指标
│   ├── core/                    # 对局引擎、导演、演员、会话、条件解析
│   │   ├── engine.py
│   │   ├── director.py
│   │   ├── roleplay.py
│   │   ├── session.py           # TTL 惰性清理 / 并发上限 / 轮次硬顶
│   │   └── condition_parser.py
│   ├── content/                 # 剧本仓库与 schema 校验
│   │   ├── script_repository.py # 原子写保护
│   │   └── validator.py
│   ├── llm/                     # LLM 客户端与配置
│   │   ├── client.py            # 超时 + 一次轻量重试
│   │   └── config.py
│   ├── prompts/                 # Prompt 模板管理
│   │   └── manager.py
│   └── dev/                     # 开发者模式专属逻辑
│       ├── auth.py
│       ├── drafts.py
│       ├── path_calculator.py
│       └── prompt_preview.py
│
├── static/
│   ├── robots.txt               # Disallow: /
│   ├── share/share-capture.js   # 分享图片 / 纯文本导出
│   └── echoes/                  # Echoes 阅读流 UI
│
├── scripts/                     # 生产剧本（JSON，dev 保存并发布写入此处）
│   ├── fanfic/                  # 影视同人 · origin_tag: 影视同人
│   ├── original/                # 原创剧情 · origin_tag: 你也一定遇到过
│   └── verify_deploy.sh         # 部署前本地校验脚本（可选）
│
├── prompts/                     # 生产 Prompt 模板（dev 发布 Prompt 写入此处）
│   ├── director/
│   │   ├── system.txt           # 导演 system：职责、JSON 格式、关键点规则
│   │   └── user.txt             # 导演 user：背景、数值、历史、待命中关键点等
│   ├── roleplay/
│   │   ├── system.txt           # 演员 system：角色人设与输出规则
│   │   └── user.txt             # 演员 user：历史、reaction 指导、情绪词表
│   └── script_gen_prompt.md     # 用 AI 批量生成新剧本 JSON 的提示词模板
│
├── static/                      # 玩家端前端
│   ├── index.html               # 选本 + briefing + Echoes 对局页 + 结局
│   ├── app.js                   # 选剧本、briefing、与 Alpine 对局页事件通信
│   ├── style.css
│   ├── echoes/                  # v1.3 Echoes 阅读流模块
│   │   ├── echoes.css           # 设计 token + 组件样式
│   │   ├── echoes-core.js       # Echo 触发、文案池、调性变量
│   │   └── echoes-app.js        # Alpine 对局逻辑 + SSE 流式
│   ├── concept/
│   │   └── echoes_demo.html     # 静态 Concept Demo（假数据）
│   ├── vendor/
│   │   └── alpine.min.js        # Alpine.js（本地托管）
│   └── dev/                     # 开发者模式前端
│       ├── index.html
│       └── dev.js               # 剧本编辑 / LLM 调试 / 试玩 / diff / 导出
│
├── dev_drafts/                  # 本地草稿目录（.gitignore，运行时生成）
│   ├── scripts/                 # Save Draft 的剧本 JSON
│   └── prompts/                 # Save Draft 的 Prompt 模板
│
└── docs/                        # 设计与参考文档（见下节）
    └──  v1.0/
        └── ui_screenshots/      # README 用界面截图
            └── echoes_gameplay_v1.3.png
```

### 主要 API 路由

| 前缀 | 用途 |
|------|------|
| `GET /` | 玩家端页面 |
| `GET /dev` | 开发者模式页面 |
| `GET/POST /api/scripts/*` | 剧本列表与详情（玩家） |
| `POST /api/session/*` | 开始对局、发消息（含 SSE 流式） |
| `GET/POST /api/config/llm*` | 模型配置状态与连接测试 |
| `POST /api/dev/login` | 开发者登录 |
| `GET/PUT/POST/DELETE /api/dev/scripts/*` | 剧本 CRUD、校验、导入导出 |
| `GET/PUT/DELETE /api/dev/drafts/scripts/*` | 剧本草稿读写、对比 |
| `GET/PUT/POST/DELETE /api/dev/prompts*` | Prompt 读写、草稿、发布、预览 |
| `POST /api/dev/scripts/{id}/simulate/*` | dev 试玩（含调试字段） |

---

## 文档结构（`docs/`）

设计文档按版本迭代组织；**玩家端 UI 以 v1.3（Echoes 阅读流）为准**，开发者模式规格以 v1.2 为准。

```
docs/
├── design_document.md           # 项目最初框架搭建指导（技术选型、最小可部署版本）
│
├── doubao_cache_instruction.md  # 火山引擎 Doubao Prompt 缓存接入参考（非核心玩法）
│
└──  v1.0/                       # v1.x 里程碑文档（注意目录名含前导空格）
    ├── design_doc_v1.0.md       # v1.0：双 Agent 架构、Prompt 模板机制、工程拆分
    ├── design_doc_v1.1.md       # v1.1：剧本分类标签、选择页、briefing 等 UX
    ├── design_doc_v1.2.md       # v1.2：/dev 编辑器、草稿、试玩调试、假设路径
    ├── design_docv1.3.md        # v1.3（当前 UI）：Echoes 阅读流、Alpine.js、后端目录重构 ★
    ├── backend_refract.md       # v1.3 后端目录重构方案与验证清单
    ├── chat_script_optimization.md
    │                            # 关键点/减分点系统、结构化 reaction、emotion_vocabulary
    ├── ui_screenshots/          # 界面截图（供 README 引用）
    │   └── echoes_gameplay_v1.3.png
    └── ui_mockup_v1.0/          # v1.0 时期 UI 静态 mockup（HTML，仅供参考）
        ├── script_selection_preview.html
        ├── ruxi_gameplay_screen_mockup.html
        ├── ruxi_ending_card_mockup.html
        └── ruxi_dev_mode_simulate_panel_mockup.html
```

### 文档阅读顺序建议

| 顺序 | 文件 | 说明 |
|------|------|------|
| 1 | [`docs/ v1.0/design_doc_v1.0.md`](docs/%20v1.0/design_doc_v1.0.md) | 理解导演/演员双 Agent 分工与 Prompt 管理 |
| 2 | [`docs/ v1.0/chat_script_optimization.md`](docs/%20v1.0/chat_script_optimization.md) | 理解 `key_points` / `pitfalls` / `reaction` / 剧本 JSON 扩展 |
| 3 | [`docs/ v1.0/design_doc_v1.1.md`](docs/%20v1.0/design_doc_v1.1.md) | 理解 `origin_tag`、`theme_tags`、玩家端选本与入场须知 |
| 4 | [`docs/ v1.0/design_doc_v1.2.md`](docs/%20v1.0/design_doc_v1.2.md) | **开发者模式完整规格**：校验、草稿、试玩调试、Prompt 编辑 |
| 5 | [`docs/ v1.0/design_docv1.3.md`](docs/%20v1.0/design_docv1.3.md) | **Echoes 阅读流 UI**、Echo 卡片、调性参数、待办项 |
| — | [`docs/design_document.md`](docs/design_document.md) | 最早期的脚手架与部署思路，部分细节已被 v1.x 覆盖 |

### 剧本 JSON 核心字段（速查）

完整 schema 与校验规则见 `game/content/validator.py` 与 design_doc_v1.2 §四。

| 字段 | 说明 |
|------|------|
| `id`, `title`, `origin_tag`, `theme_tags` | 标识与分类 |
| `teaser`, `briefing`, `objective`, `background` | 展示与 LLM 背景 |
| `ai_character`, `player_character` | 角色名、人设；`ai_character.emotion_vocabulary` 为情绪词表 |
| `stats` | 数值维度：`initial` / `min` / `max` / `direction` |
| `key_points`, `pitfalls` | 关键点与减分点：`id`、`description`、`hit_stat_changes`（范围） |
| `win_condition`, `lose_condition` | 条件表达式，如 `好感度 >= 70 且 愤怒值 <= 20` |
| `max_turns`, `opening_line` | 回合上限与 AI 开场白 |
| `ending_titles` | 结局卡片标题（`win` / `lose`）；可选 `ending_lines` 作规则兜底文案 |
| `echo_phrases` | （v1.3 可选）Echo 卡片文学化文案池，按数值名 + 变化方向/幅度分类；未配置则用前端通用兜底 |
| `tone_preset` | （v1.3 可选）阅读流调性：`从容`（默认）/ `明快`，影响行高与动效时长 |

开发者模式功能说明亦见上文 [开发者模式（/dev）](#开发者模式dev) 一节。

---

## 分支与部署

| 分支 | 用途 |
|------|------|
| `develop` | 日常开发 |
| `main` | 稳定版，push 后 Render 自动部署 |

```bash
git checkout main
git merge develop
git push origin main
git checkout develop
```

Render 监听 `main`（见 `render.yaml`）。

- **Build:** `pip install -r requirements.txt`
- **Start:** `uvicorn main:app --host 0.0.0.0 --port $PORT`

部署环境需配置 `LLM_*`；建议配置 `INVITE_CODE`（玩家端邀请码）与（可选）`DEV_MODE_PASSWORD`。

### Render 免费实例：性能与限制

当前公网部署使用 Render **Free Web Service**（见 `render.yaml` 的 `plan: free`）。适合 demo / 小范围分享，**不适合**高并发或 SLA 要求高的生产场景。

#### 平台资源（Free 档典型值）

| 项 | 大约水平 |
|----|----------|
| 内存 | 512 MB |
| CPU | 共享、偏低（约 0.1 CPU 量级） |
| 实例数 | 1（无水平扩展） |
| 文件系统 | **易失** — 重启 / 重新部署后，`/dev` 在线保存的剧本与草稿会丢失（git 里的 `scripts/`、`prompts/` 会随部署恢复） |
| 空闲行为 | 约 **15 分钟**无请求后休眠；下次访问需 **冷启动**（常见 30–60 秒，视依赖安装与唤醒情况而定） |

#### 对本项目的实际体验

| 场景 | 预期 |
|------|------|
| 打开首页 / 静态资源 | 实例**唤醒后**较快；`echoes/`、`vendor/` 等有 24h 浏览器缓存 |
| 选剧本、读 briefing | 毫秒级（读 JSON，不调 LLM） |
| **每轮对话** | 主要耗时在 **LLM**（导演 + 演员各 1 次调用，流式输出）。通常 **数秒～十余秒/轮**，与模型、Prompt 长度、火山引擎 API 延迟有关，与 Render 关系不大 |
| 「请帮帮我」 | 额外 **1 次** LLM 调用，再叠加数秒 |
| 同时进行中的对局 | 免费单实例 + 内存 Session，**同时 1～3 局**较稳；再多容易变慢或触发 OOM / 排队感 |
| API 限流 | 每 IP **120 次/分钟**（`RATE_LIMIT_PER_MINUTE`），超限返回 **429** |

#### 架构上的边界（v1.3 当前实现）

- **Session 在进程内存** — 服务重启后所有进行中的对局丢失；不支持多实例共享状态。
- **限流在进程内存** — 仅对当前实例有效；若将来升级到多实例需换 Redis 等方案。
- **瓶颈通常在 LLM API**，而非 Render 本身；升级 Render 套餐对「每句话等多久」帮助有限，换更快模型 / 优化 Prompt 更直接。

#### 部署后自检

```bash
# 常规冒烟（首页、API、静态缓存等）
./scripts/verify_deploy.sh https://ruxi.onrender.com

# 含限流压测（会对线上连发约 125 次 /api/scripts，建议低峰期执行）
VERIFY_RATE_LIMIT=1 ./scripts/verify_deploy.sh https://ruxi.onrender.com
```

#### 若访问量上来

1. 内容改动走 **git → main → 自动部署**，不要只依赖 `/dev` 线上保存。  
2. 考虑 Render **Starter** 或以上（不休眠、更多 CPU/内存）。  
3. 长期需要：持久化 Session、多实例、队列削峰 — 属于 v2 架构，当前 demo 未做。
