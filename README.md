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
cp .env.example .env   # 填入 LLM 配置（可选）
uvicorn main:app --reload
```

浏览器打开 http://localhost:8000

---

## LLM 配置

两种方式二选一：

**环境变量**（推荐用于部署）— 复制 `.env.example` 为 `.env` 并填写：

```
LLM_PROVIDER=doubao        # doubao / openai / custom
LLM_API_BASE=https://...
LLM_API_KEY=your-key
LLM_MODEL=model-id
```

**网页配置**（推荐用于公网分享）— 首页「LLM 配置」Tab 填写并保存，Key 存于浏览器 localStorage，每位访客使用自己的 Key。

---

## 技术架构

- **后端** FastAPI + Python，SSE 流式输出
- **前端** 原生 HTML / CSS / JS，无框架依赖
- **双 LLM 架构**
  - Director agent — 判断玩家回复，更新数值和关键点
  - Roleplay agent — 生成 AI 角色对话，携带情绪标签

---

## 分支与部署

| 分支 | 用途 |
|------|------|
| `develop` | 日常开发 |
| `main` | 稳定版，push 后 Render 自动部署 |

```bash
# 发布到公网
git checkout main
git merge develop
git push origin main
git checkout develop
```

Render 监听 `main` 分支（见 `render.yaml`），merge 后自动触发构建。

Build: `pip install -r requirements.txt`
Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
