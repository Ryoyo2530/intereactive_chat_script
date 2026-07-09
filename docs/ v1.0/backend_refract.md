# 入戏 —— 后端目录结构基础重构

## 现状问题（基于develop分支实际代码）

- `main.py` 470行，堆了30个路由（玩家端+dev模式全部混在一起），职责不清晰，改一个功能要在一个大文件里定位
- `game/` 目录平铺14个文件，核心引擎（`engine.py` `director.py` `roleplay.py` `session.py` `condition_parser.py`）、内容管理（`script_repository.py` `validator.py`）、LLM基础设施（`llm_client.py` `llm_config.py`）、dev模式专属逻辑（`dev_auth.py` `dev_drafts.py` `prompt_preview.py` `path_calculator.py`）全部并列在同一层，看目录完全看不出模块边界
- `game/engine.py` 500行，是全仓库最大的文件，大概率承担了过多职责（编排+其他逻辑混在一起）

本次重构目标：**只调整目录结构和import路径，不改变任何业务逻辑**。这是一次纯粹的"搬家"，做完后行为应与重构前完全一致。

---

## 一、`game/` 拆分为四个子包

按职责分组，文件内容不变，仅移动位置并调整import：

```
game/
├── core/                      # 核心游戏引擎：agent编排、会话、条件解析
│   ├── __init__.py
│   ├── engine.py               # 原 game/engine.py
│   ├── director.py             # 原 game/director.py
│   ├── roleplay.py             # 原 game/roleplay.py
│   ├── session.py              # 原 game/session.py
│   └── condition_parser.py     # 原 game/condition_parser.py
│
├── content/                    # 剧本内容管理：加载、保存、校验
│   ├── __init__.py
│   ├── script_repository.py    # 原 game/script_repository.py
│   └── validator.py            # 原 game/validator.py
│
├── llm/                        # LLM调用基础设施
│   ├── __init__.py
│   ├── client.py                # 原 game/llm_client.py
│   └── config.py                # 原 game/llm_config.py
│
├── prompts/                     # prompt模板加载与渲染
│   ├── __init__.py
│   └── manager.py                # 原 game/prompt_manager.py
│
└── dev/                         # dev模式专属业务逻辑（不属于核心玩法）
    ├── __init__.py
    ├── auth.py                   # 原 game/dev_auth.py
    ├── drafts.py                  # 原 game/dev_drafts.py
    ├── prompt_preview.py          # 原 game/prompt_preview.py
    └── path_calculator.py         # 原 game/path_calculator.py
```

**划分逻辑**：
- `core/`：不管是玩家端正式对局还是dev模式的试玩验证，都会调用这一层——这是游戏真正跑起来的引擎部分
- `content/`：剧本作为"数据"如何被读取、写入、校验，玩家端（只读）和dev模式（读写）共用
- `llm/`：纯粹的LLM调用封装，不含任何游戏业务逻辑，理论上换个项目也能直接复用
- `prompts/`：prompt模板管理独立成一个子包，虽然当前只有一个文件，但预留未来模板增多（比如v1.3以后可能要新增更多agent类型）时的扩展空间
- `dev/`：只有dev模式会用到的东西——鉴权、草稿管理、prompt预览、路径计算器，全部和"玩家实际怎么玩"无关，独立分组能让你清楚哪些代码是给自己用的工具，哪些是产品本体

**注意**：`game/llm/client.py` 和 `game/llm/config.py` 改名去掉了原来的 `llm_` 前缀（因为已经在 `llm/` 目录下，前缀是冗余信息），其余文件保持原名不变，减少不必要的改动量。

---

## 二、`main.py` 拆分为路由模块

新建 `routers/` 包，按面向对象拆分：

```
routers/
├── __init__.py
├── player.py       # 玩家端接口
├── dev_scripts.py  # dev模式：剧本CRUD、校验、导入导出
├── dev_drafts.py   # dev模式：草稿管理、对比
├── dev_prompts.py  # dev模式：prompt草稿/发布/预览
└── dev_simulate.py # dev模式：试玩验证的start/message
```

### 各文件承接的现有路由（对照当前main.py的路由清单）

**`routers/player.py`**：
```
GET  /favicon.ico
GET  /api/config/llm
POST /api/config/llm/test
GET  /api/scripts
GET  /api/scripts/{script_id}/detail
POST /api/session/start
POST /api/session/message
POST /api/session/message/stream
GET  /
```

**`routers/dev_scripts.py`**（含登录，因为登录和剧本管理耦合较紧，也可以单独拆一个 `dev_auth.py` 路由文件，如果你觉得职责更清晰的话）：
```
GET    /dev
POST   /api/dev/login
GET    /api/dev/scripts
GET    /api/dev/scripts/{script_id}
POST   /api/dev/scripts
POST   /api/dev/scripts/{script_id}/validate
PUT    /api/dev/scripts/{script_id}
DELETE /api/dev/scripts/{script_id}
GET    /api/dev/scripts/{script_id}/export
GET    /api/dev/export
POST   /api/dev/scripts/import
POST   /api/dev/scripts/import/overwrite
```

**`routers/dev_drafts.py`**：
```
GET    /api/dev/drafts/scripts/{script_id}
PUT    /api/dev/drafts/scripts/{script_id}
DELETE /api/dev/drafts/scripts/{script_id}
GET    /api/dev/drafts/scripts/{script_id}/compare
```

**`routers/dev_prompts.py`**：
```
GET    /api/dev/prompts
PUT    /api/dev/prompts/draft
POST   /api/dev/prompts/publish
DELETE /api/dev/prompts/draft
POST   /api/dev/prompts/preview
```

**`routers/dev_simulate.py`**：
```
POST /api/dev/scripts/{script_id}/simulate/start
POST /api/dev/scripts/{script_id}/simulate/message
```

### 重构后的 `main.py`

只保留应用初始化、中间件、路由挂载：

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from routers import player, dev_scripts, dev_drafts, dev_prompts, dev_simulate

app = FastAPI()

app.include_router(player.router)
app.include_router(dev_scripts.router, prefix="/api/dev", tags=["dev-scripts"])
app.include_router(dev_drafts.router, prefix="/api/dev/drafts", tags=["dev-drafts"])
app.include_router(dev_prompts.router, prefix="/api/dev/prompts", tags=["dev-prompts"])
app.include_router(dev_simulate.router, prefix="/api/dev", tags=["dev-simulate"])

app.mount("/", StaticFiles(directory="static"), name="static")
```

（以上路由前缀分配仅供参考，实际以各router内部路径拼接后与原有路由完全一致为准——重构后用现有的 `scripts/verify_deploy.sh` 或手动过一遍所有接口，确认URL没有变化。）

`require_dev_auth` 这个依赖项（原来在 `main.py` 里定义或从 `game/dev_auth.py` 引入）应放在 `game/dev/auth.py` 里作为纯函数/依赖项导出，所有dev相关router统一从这里导入，不要在每个router文件里各自重复定义。

---

## 三、`game/engine.py`（500行）的处理建议

这个文件明显是当前仓库里职责最重的一个。本次重构**不强制拆分它的内部逻辑**（避免和"只搬家不改逻辑"的重构目标冲突，拆分内部逻辑风险更高，应该作为独立的下一步任务，而不是和目录搬家混在一起做）。

但建议你在完成本次目录重构后，另起一次改动专门看一下 `engine.py` 内部：如果它同时包含"编排导演/演员调用顺序"+"session状态更新"+"数值计算/clamp逻辑"+"接口层数据组装"这几类不同职责，可以考虑再拆成 `core/engine.py`（编排主流程）+ `core/stats.py`（数值计算相关的纯函数）这样的粒度，但这是本次重构之后的后续优化项，不在这次一起做。

---

## 四、实施步骤

1. 用 `git mv` 逐个文件搬家（保留git历史，不要用删除+新建的方式），而不是手动复制粘贴
2. 每个子包加 `__init__.py`（可以为空，或者在 `__init__.py` 里做一些常用符号的重新导出，方便外部import路径更短，视你喜好决定）
3. 全局搜索所有 `from game import xxx` / `from game.xxx import` 引用，改成新路径（比如 `from game import llm_client` 改为 `from game.llm import client as llm_client`，或者直接改调用点用新的模块名）
4. 拆分 `main.py` 到 `routers/` 时，逐个路由搬，每搬完一批就跑一次现有的 `scripts/verify_deploy.sh`（如果这个脚本覆盖了主要接口的话）或手动过一遍关键流程（选剧本→对局→dev模式登录→剧本编辑），确保行为没变
5. 全部搬完后，本地完整跑一遍README里提到的核心使用路径，再部署到Render验证

---

## 五、验证要求

1. 重构后本地启动服务，玩家端完整走一局（选剧本→对话→触发结局）与重构前行为一致
2. dev模式登录、剧本编辑保存、试玩验证、prompt预览/发布等功能逐项跑一遍，确认路由路径和行为都没有变化
3. 检查是否有遗漏的旧import路径导致启动报错（比如某个文件里还在用 `from game import engine` 这种旧路径）
4. 部署到Render，确认线上行为与本地一致