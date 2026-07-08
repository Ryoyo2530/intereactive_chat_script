# 入戏

> 用对话改写剧情走向的 AI 文字游戏

选剧本 → 读入场须知 → 开口说话 → 数值涨跌 → 触发结局

**公网体验：** https://ruxi.onrender.com

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
| http://localhost:8000 | 玩家端 |
| http://localhost:8000/dev | 开发者模式（需 `DEV_MODE_PASSWORD`） |

---

## LLM 配置

### 玩家端

两种方式二选一：

**环境变量**（推荐用于部署）— 在 `.env` 中填写：

```env
LLM_PROVIDER=doubao        # doubao / openai / custom
LLM_API_BASE=https://...
LLM_API_KEY=your-key
LLM_MODEL=model-id
```

**网页配置**（适合访客自带 Key）— 玩家端「LLM 配置」Tab 填写并保存，Key 存于浏览器 localStorage。

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

- **LLM 配置** — 导演与演员 Agent 模型
- **Prompt 模板** — 编辑 `director/system.txt`、`director/user.txt`、`roleplay/system.txt`、`roleplay/user.txt`；选择剧本 + 示例玩家发言 → **渲染预览**（查看变量填充后的完整 Prompt）

### 其他

- 上传 / 下载单个剧本或导出全部 zip
- 新建剧本（内置 JSON 模板）
- Schema 校验在**保存并发布**时执行；错误阻止发布，警告允许发布

设计说明见 [`docs/ v1.0/design_doc_v1.2.md`](docs/%20v1.0/design_doc_v1.2.md)。

---

## 技术架构

- **后端** — FastAPI + Python；玩家消息支持 SSE 流式输出
- **前端** — 原生 HTML / CSS / JS，无框架依赖
- **双 LLM Agent**
  - **Director** — 判定关键点/减分点、数值变化、结构化 reaction、胜负
  - **Roleplay** — 生成角色台词与 `emotion_tag`（受剧本情绪词表约束）
- **剧本** — `scripts/fanfic/`、`scripts/original/` 下的 JSON；运行时经 `script_repository` 加载，dev 保存后即时生效
- **Prompt** — `prompts/director/`、`prompts/roleplay/` 模板，由 `prompt_manager` 渲染

### 目录结构

```
├── main.py                 # FastAPI 入口（玩家 + dev API）
├── game/
│   ├── engine.py           # 对局主流程
│   ├── director.py         # 导演 Agent
│   ├── roleplay.py         # 演员 Agent
│   ├── script_repository.py
│   ├── validator.py        # 剧本 schema 校验
│   ├── dev_drafts.py       # 剧本/Prompt 草稿缓冲区
│   ├── path_calculator.py  # 假设路径静态计算
│   └── ...
├── scripts/                # 生产剧本（按分类分子目录）
├── prompts/                # 生产 Prompt 模板
├── dev_drafts/             # 本地草稿（gitignore，不提交）
├── static/                 # 玩家端
│   └── dev/                # 开发者模式前端
└── docs/                   # 设计文档
```

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

部署环境需配置 `LLM_*` 与（可选）`DEV_MODE_PASSWORD`。
