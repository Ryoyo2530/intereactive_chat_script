# 入戏 - 基础框架搭建指导

## 目标
搭建一个**可运行、可部署、可访问**的最小框架版本。此阶段**不追求玩法完整**，只追求：
1. 项目结构清晰，便于后续迭代剧本/数值系统
2. 本地可运行
3. 能部署到公网，分享链接即可访问
4. LLM API Key 安全存放在后端，不暴露给浏览器

---

## 技术选型

- **后端**：Python + FastAPI（处理剧本逻辑、LLM 调用、数值系统、对话状态）
- **前端**：纯 HTML + JS + **Tailwind CSS（CDN 引入，零构建）**——不用 React/Vue，不需要 npm/webpack，但视觉效果可以做到精致（详见下方"前端美化方案"）
- **托管**：FastAPI 直接用 `StaticFiles` 托管前端页面，**前后端合并为一个服务**，只需部署一次
- **部署平台**：Render.com（免费层，Git 推送自动部署，比 Streamlit Cloud 同样简单；免费层有冷启动但对分享给朋友玩的 demo 完全够用）
- **LLM 调用**：通过 Anthropic/Openai API（或其他 LLM API），Key 存放在环境变量，只在后端调用

初始配置示例见 `.env.example`（请勿将真实 Key 提交到 Git）。
### 前端美化方案：为什么选 Tailwind CDN

对话式文字游戏最需要的视觉打磨点是：**对话气泡的呈现、数值条的直观变化、轮次/进度的提示感**。这些用 Tailwind 的原子类可以快速写出效果，且不需要任何构建工具：

```html
<script src="https://cdn.tailwindcss.com"></script>
```

引入这一行之后，直接在 HTML 里写 `class="rounded-2xl bg-rose-50 px-4 py-3 shadow-sm"` 这类原子类即可，不需要写 CSS 文件、不需要编译。比手写 CSS 快，又比引入 React 轻量得多——对"能跑起来 + 有基本美感"的 demo 阶段是最优性价比选择。

如果后续想要更极致的动效（比如打字机效果、数值条平滑过渡动画），可以在 `app.js` 里用原生 JS 或极小的过渡库（如 CSS `transition` 属性）实现，仍然不需要引入完整前端框架。

---

## 项目结构

```
ai-fiction-game/
├── main.py                 # FastAPI 入口
├── requirements.txt
├── .env.example            # 环境变量示例（ANTHROPIC_API_KEY等）
├── .gitignore               # 忽略 .env, __pycache__ 等
├── scripts/                 # 剧本配置目录（未来核心迭代区）
│   └── example_script.json  # 示例剧本（先写死一个，验证链路）
├── game/
│   ├── __init__.py
│   ├── session.py          # 游戏会话状态管理（内存字典即可，demo阶段不用数据库）
│   ├── llm_client.py       # 封装 LLM API 调用
│   └── engine.py           # 核心游戏逻辑：读取剧本、调用LLM、更新数值、判断胜负
└── static/
    ├── index.html          # 单页前端：剧本选择 + 对话界面，<head>中通过CDN引入Tailwind
    ├── app.js              # 前端逻辑：发送消息、渲染对话、渲染数值条、简单过渡动效
    └── style.css           # 少量Tailwind覆盖不了的自定义样式（如打字机效果的keyframes）
```

---

## 核心接口设计（先实现这几个即可跑通）

### 1. `GET /api/scripts`
返回可用剧本列表（从 `scripts/` 目录读取），前端用于渲染剧本选择页。

### 2. `POST /api/session/start`
请求体：`{ "script_id": "example_script" }`
- 创建一个新的游戏会话（生成 session_id，存于内存字典）
- 初始化该剧本的数值系统（如 "怀疑值": 50, "愤怒值": 30）
- 返回：`session_id`、剧本开场白、初始数值状态

### 3. `POST /api/session/message`
请求体：`{ "session_id": "...", "message": "玩家发的话" }`
- 读取该 session 的历史对话 + 数值状态
- 调用 LLM：将【剧本设定 + 角色设定 + 数值系统当前状态 + 历史对话 + 玩家新消息】拼接为 prompt，要求 LLM 返回：
  - 角色的回复文本
  - 数值变化（结构化 JSON，例如 `{"怀疑值": -5, "愤怒值": +10}`）
  - 是否达成目标 / 游戏结束判定
- 更新 session 状态
- 返回：AI回复文本、最新数值状态、游戏是否结束及结局描述

> **Demo阶段简化建议**：LLM 返回格式用 JSON 强约束（prompt 里要求"只返回JSON，包含 reply/stat_changes/game_over/ending_text 字段"），后端解析失败时做兜底（数值不变、游戏继续），避免因格式问题崩溃。

### 4. 剧本 JSON 结构示例（`scripts/example_script.json`）
```json
{
  "id": "example_script",
  "title": "我的前半生 - 唐晶篇",
  "background": "电视剧《我的前半生》背景：罗子君和唐晶因为贺涵的事情发生矛盾...",
  "ai_character": {
    "name": "唐晶",
    "persona": "唐晶的性格设定、说话风格..."
  },
  "player_character": {
    "name": "罗子君"
  },
  "objective": "解释清楚罗子君和贺涵的关系，让唐晶原谅自己",
  "stats": {
    "怀疑值": {"initial": 50, "min": 0, "max": 100},
    "愤怒值": {"initial": 60, "min": 0, "max": 100}
  },
  "win_condition": "怀疑值 <= 20 且 愤怒值 <= 20",
  "lose_condition": "愤怒值 >= 100",
  "max_turns": 15,
  "opening_line": "（唐晶的开场白，由AI结合background生成或预先写死）"
}
```

---

## 实施步骤（要求 coding agent 按顺序做）

1. 初始化项目结构（如上），写好 `requirements.txt`（fastapi, uvicorn, python-dotenv, anthropic 或对应 LLM SDK）
2. 实现 `game/llm_client.py`：封装对 LLM API 的调用（读取环境变量里的 API Key）
3. 写死一个最简单的 `scripts/example_script.json`
4. 实现 `game/engine.py`：加载剧本、维护 session 状态（内存字典即可，形如 `{session_id: {history: [], stats: {}, turn: 0}}`）
5. 实现 `main.py` 中的三个接口（`/api/scripts`, `/api/session/start`, `/api/session/message`），并用 `app.mount("/", StaticFiles(directory="static", html=True))` 挂载前端
6. 写 `static/index.html` + `app.js` + `style.css`：能选剧本、发消息、展示AI回复和数值条。这一步**需要基本的视觉打磨**，具体要求见下方"前端UI设计要求"
7. **本地验证**：`uvicorn main:app --reload`，用浏览器访问 `localhost:8000`，走通"选剧本 → 对话 → 数值变化 → 触发结局"完整链路
8. 写 `.env.example` 说明需要哪些环境变量，`.gitignore` 排除 `.env`
9. 推送到 GitHub，在 Render.com（或 Railway.app）新建 Web Service：
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - 在平台的环境变量设置里填入 `ANTHROPIC_API_KEY`
10. 部署成功后访问分配的公网 URL，确认流程和本地一致，即完成"可运行+可部署验证"的框架目标

---

## 前端UI设计要求（demo阶段需要做到的美化程度）

不需要精美插画或复杂交互，但需要体现"这是一个精心设计的剧情游戏"而非"能跑的表单"。具体要求：

**整体氛围**：根据剧本的情绪基调选择配色（例如都市情感剧适合暖色调、柔和阴影；悬疑剧本适合冷色调、高对比）。不要用默认的纯白背景+黑色文字，要有一个统一的背景色/渐变和一套克制的强调色。

**对话区域**：
- 玩家消息和AI角色消息要有明显区分（气泡方向、颜色区分，类似聊天软件的左右布局）
- AI角色的消息旁应显示角色名（甚至可以预留头像位置，demo阶段用文字/emoji代替头像图片即可）
- 新消息出现时有简单的淡入或滑入过渡（用 CSS transition 即可，不需要复杂动画库）

**数值系统可视化**（这是本游戏的核心体验点，需要重点打磨）：
- 每个数值用一个横向进度条展示，而不是纯数字，让玩家能直觉感受"愤怒值在上升"
- 数值变化时进度条要有平滑过渡动画（CSS `transition: width 0.4s ease`），并且可以在数值变化时短暂高亮/闪烁提示玩家"这里有变化"
- 用颜色语义化数值：例如愤怒值高时进度条偏红，友好值高时偏绿

**顶部/侧边信息栏**：显示当前剧本标题、目标提示、当前轮次/剩余轮次（如"第 3/15 轮"），让玩家清楚游戏进度和目标

**结局呈现**：游戏结束（胜利/失败）时不要只是弹一个 alert，用一个居中的结算卡片覆盖对话区，展示结局文案，并给出"重新开始"按钮

**响应式**：保证手机浏览器打开时布局不错乱（Tailwind 的响应式类如 `sm:` `md:` 前缀可以低成本解决），因为分享链接给朋友很可能是在手机上点开的

---

## 后续迭代预留点（框架搭建时应保持扩展性，但不需要现在实现）

- 多剧本：`scripts/` 下加更多 JSON 文件即可，无需改动核心引擎
- 多角色：`ai_character` 可扩展为数组，`engine.py` 里增加"当前发言角色"字段
- 数值→剧情分支：`win_condition`/`lose_condition` 目前用简单表达式字符串，未来可扩展为更复杂的规则引擎
- 会话持久化：demo阶段用内存字典足够；如果要跨设备/防止服务重启丢失，后续可换 Redis 或 SQLite
- "导演/监测模型"角色：可以在 `engine.py` 的 message 处理流程里，在角色回复之外**额外调用一次 LLM** 专门做数值判定和裁判，与角色扮演的 LLM 调用分离，便于分别调优 prompt

---

## 给 coding agent 的执行提示

> 请按照以上结构和步骤，先实现一个能本地运行、能部署到 Render.com 的最小可用版本。核心验证目标是：用户能打开网页 → 选择剧本 → 和AI角色对话若干轮 → 看到数值变化（带平滑动画的进度条）→ 触发胜利或失败结局（带结算卡片）。前端使用 Tailwind CDN 达到"前端UI设计要求"章节列出的基本美化程度，但不需要数据库、不需要用户登录、不需要多剧本内容，核心目标是打通完整链路、具备基本美感、并验证公网可访问。
