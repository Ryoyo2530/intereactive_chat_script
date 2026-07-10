# 入戏 v1.3 —— Echoes 阅读流 UI 与后端重构

> 玩家端 UI 以本版本为准；开发者模式规格仍以 [design_doc_v1.2.md](./design_doc_v1.2.md) 为准。

## 一、版本目标

v1.3 将玩家端对局页从「聊天气泡」升级为 **Echoes 阅读流**（纸感排版、角色名前缀、Echo 卡片、独立输入区），并完成后端目录重构（`game/` 分包 + `routers/` 拆路由）。

**本版本不做**：难度分级、开发者模式视觉对齐（可选）、移动端专项回归（待测）。

---

## 二、Echoes 阅读流 UI

### 2.1 页面结构

| 区域 | 说明 |
|------|------|
| 章节头 | 剧本标题 + 轮次；可展开/收起背景与角色卡 |
| 世界状态 | 数值名 + 轨道圆点 + 数字 |
| 阅读流 | `角色名：` 前缀对白；情绪标签在台词上方；玩家行左侧竖线区分 |
| Echo 卡片 | 数值 \|Δ\| ≥ 5 或命中关键点时出现 |
| 输入区 | 底部独立面板，与正文阅读流视觉分离 |
| 请帮帮我 | 输入区上方，触发隐晦提示（LLM，每局限次） |

静态 Concept Demo：`/concept/echoes_demo.html`（假数据，不接后端）

### 2.2 前端模块

```
static/echoes/
├── echoes.css      # 设计 token + 组件样式
├── echoes-core.js  # Echo 触发、文案池、调性变量
└── echoes-app.js   # Alpine 对局逻辑 + SSE 流式
```

- Alpine.js 本地托管：`static/vendor/alpine.min.js`
- 选本 / briefing / 结局：`static/app.js` 通过 `CustomEvent` 与 Alpine 通信

### 2.3 调性参数 `tone_preset`

| 值 | 行高 | 字距 | 回复动效 | Echo 动效 |
|----|------|------|----------|-----------|
| `从容`（默认） | 1.9 | 0.03em | 450ms | 300ms |
| `明快` | 1.6 | normal | 175ms | 150ms |

由 `echoes-core.js` 的 `applyTonePreset()` 写入 CSS 变量。测试剧本：`original_bright_001`（`tone_preset: "明快"`）。

---

## 三、Echo 卡片（模板文案，非 LLM）

### 3.1 触发条件（前端）

- 任一数值变化 \|Δ\| ≥ `ECHO_THRESHOLD`（默认 5）
- 或本轮命中关键点 / 减分点

### 3.2 文案来源

1. 剧本 JSON 可选字段 `echo_phrases`（按数值名 + 方向 + 幅度）
2. 未配置则用 `echoes-core.js` 内 `DEFAULT_ECHO_PHRASES._default` 兜底

键名格式：`up_small` / `up_medium` / `up_large` / `down_small` / `down_medium` / `down_large`

示例：

```json
"echo_phrases": {
  "愤怒值": {
    "down_medium": ["空气松弛了一瞬。", "紧绷的气氛稍稍缓和。"],
    "down_large": ["重压忽然卸去一角。"]
  }
}
```

### 3.3 API 透传

- `GET /api/scripts/{id}/detail` → `echo_phrases`, `tone_preset`, `chapter_title`
- `POST /api/session/start` → `script.echo_phrases`, `script.tone_preset`, `script.max_hints`

---

## 四、请帮帮我（剧情提示）

- 按钮位置：输入区上方（`echoes-help`）
- 接口：`POST /api/session/hint`，body `{ "session_id": "..." }`
- 每局默认 3 次，剧本可配置 `max_hints`
- 单独 LLM 调用，根据当前对话、数值、未命中关键点生成 **隐晦方向提示**，不剧透具体台词
- 提示以 `echoes-hint-card` 插入阅读流

---

## 五、后端目录重构

详见 [backend_refract.md](./backend_refract.md)。

```
game/
├── core/       # engine, director, roleplay, session, condition_parser
├── content/    # script_repository, validator
├── llm/        # client, config
├── prompts/    # manager
└── dev/        # auth, drafts, path_calculator, prompt_preview

routers/
├── player.py
├── dev_scripts.py
├── dev_drafts.py
├── dev_prompts.py
└── dev_simulate.py
```

### 5.1 后端加固（v1.3）

| 项 | 实现 |
|----|------|
| 配置 | `game/settings.py`（pydantic-settings）；`llm/config`、`dev/auth`、`main` 统一读取 |
| 日志 | `game/logging_config.py` → `%(asctime)s %(levelname)s %(name)s %(message)s` |
| 限流 | `game/middleware.py` 按 IP 限制 `/api/*`（`RATE_LIMIT_PER_MINUTE`，默认 120/min，429） |
| 压缩 | `GZipMiddleware`（`minimum_size=500`） |
| 静态缓存 | `/echoes/`、`/vendor/` 等 `Cache-Control: public, max-age=86400` |

环境变量见 `.env.example`：`LLM_*`、`DEV_MODE_PASSWORD`、`RATE_LIMIT_PER_MINUTE`、`LOG_LEVEL`。

### 5.2 开发者鉴权

- 环境变量 `DEV_MODE_PASSWORD`
- 登录：`POST /api/dev/login` → 设置 `dev_token` cookie（`path=/`，HMAC 签名，7 天有效）
- **v1.3 修复**：由内存 token 改为无状态签名，避免 uvicorn `--reload` 或进程重启后 cookie 仍有效但服务端 token 丢失导致 401

---

## 六、剧本 JSON 新增可选字段（v1.3）

| 字段 | 说明 |
|------|------|
| `echo_phrases` | Echo 卡片文学化文案池 |
| `tone_preset` | `从容` / `明快` |
| `chapter_title` | 章节头副标题（默认同 `title`） |
| `max_hints` | 每局提示次数（默认 3） |

---

## 七、验证清单

### 已完成（c39927e + 后续）

- [x] 后端目录重构与路由拆分
- [x] Echoes 阅读流 UI + SSE 流式
- [x] Echo 卡片触发与兜底文案池
- [x] 全量产剧本 `echo_phrases`
- [x] `original_bright_001` 明快调性测试剧本
- [x] 开发者鉴权 401 修复（签名 token）
- [x] 后端加固：settings 全链路 / 限流 / GZip / 静态缓存 / 结构化日志
- [x] 「请帮帮我」提示 API + 前端
- [x] 部署验证脚本扩展（缓存、GZip、限流可选压测）

### 待办

- [ ] 移动端回归（iOS Safari / 微信内置浏览器）
- [ ] 线上执行 `VERIFY_RATE_LIMIT=1 ./scripts/verify_deploy.sh <url>` 压测确认
- [ ] Dev 模式视觉与 Echoes 风格对齐（可选）
- [ ] 验证 script 级 `echo_phrases` 覆盖默认池且重复触发文案有变化

---

## 八、本地验证路径

```bash
uvicorn main:app --reload
```

1. 玩家端：选本 → briefing → 对局 → 触发 Echo → 点「请帮帮我」
2. 选 `明快调性 · 电梯偶遇`，确认行高/动效更快
3. 开发者模式：`/dev` 登录 → 剧本列表加载（无 401）→ 试玩验证

### 后端加固验证

```bash
# 静态缓存 + GZip + API 冒烟（本地或线上）
./scripts/verify_deploy.sh http://127.0.0.1:8000

# 限流压测（建议低阈值启动服务后执行）
RATE_LIMIT_PER_MINUTE=10 uvicorn main:app --port 8000
./scripts/verify_rate_limit.sh http://127.0.0.1:8000 10

# 线上部署含限流压测
VERIFY_RATE_LIMIT=1 ./scripts/verify_deploy.sh https://ruxi.onrender.com
```
