# 入戏

AI 互动文字游戏demo。选剧本 → 对话 → 数值变化 → 触发结局。

## 本地运行

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 填入 LLM 配置
uvicorn main:app --reload
```

浏览器打开 http://localhost:8000

## LLM 配置

两种方式（二选一）：

1. **环境变量**（推荐用于部署）：复制 `.env.example` 为 `.env`，填写：
   - `LLM_PROVIDER` — doubao / openai / custom
   - `LLM_API_BASE` — API 地址
   - `LLM_API_KEY` — API Key
   - `LLM_MODEL` — 模型 ID

2. **网页配置**（推荐用于公网分享）：首页「LLM 配置」填写并保存，每人使用自己的 API Key（存于浏览器 localStorage）

## 分支与部署流程

| 分支 | 用途 |
|------|------|
| `develop` | 日常开发，所有功能更新在此进行 |
| `main` | 稳定版本，合并后 Render **自动部署** |

```bash
# 日常开发（已在 develop 上）
git checkout develop
# ... 开发、commit ...
git push origin develop

# 确认无误后发布到公网
git checkout main
git merge develop
git push origin main   # → Render 自动触发部署
git checkout develop   # 回到开发分支
```

Render 监听 `main` 分支（见 `render.yaml` 中 `branch: main`），**只有 merge 到 main 才会更新公网**。

## 部署到 Render

1. 代码 merge 到 `main` 并 push
2. [Render Dashboard](https://dashboard.render.com) 查看 Events 等待部署完成
3. 公网地址：https://ruxi.onrender.com

> 无需在 Render 配置 `LLM_API_KEY`——访客通过网页自行填写 Key 即可。

Build: `pip install -r requirements.txt`
Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
