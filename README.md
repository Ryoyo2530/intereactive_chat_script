# 入戏

AI 互动文字游戏框架。选剧本 → 对话 → 数值变化 → 触发结局。

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

2. **网页配置**：首页「LLM 配置」标签页填写并保存（存于浏览器 localStorage）

## 部署到 Render

1. 推送代码到 GitHub
2. [Render Dashboard](https://dashboard.render.com) → New → Blueprint，连接仓库（或使用 `render.yaml`）
3. 在环境变量中设置 `LLM_API_KEY`
4. 部署完成后访问分配的 URL

Build: `pip install -r requirements.txt`  
Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
