# AutoResearchLab

多 Agent 协作的自动化科研系统：**灵感构思** → **实验规划** → **论文草稿**。实验由 MAARS 负责规划与执行。

## 技术栈

| 组件 | 技术 |
|------|------|
| 前端 | Next.js |
| 后端 | FastAPI + Socket.IO |
| 实验 | MAARS（Plan Agent + Task Agent） |
| LLM | Gemini / DeepSeek |

## 快速开始

**环境**：Python 3.10+、Node.js 18+

```bash
git clone <repository_url>
cd AutoResearchLab

pip install -r requirements.txt
cd frontend && npm install && cd ..
```

**配置**：编辑 `data/db/config.json` 或访问 Config 页面，设置 LLM API Key 及端口。

**启动**：两个终端分别运行，端口从 `data/db/config.json` 读取。

```bash
# 终端 1 - 后端
node scripts/start.js backend

# 终端 2 - 前端
node scripts/start.js frontend
```

访问 `http://localhost:<frontend_port>`（端口见 config.json）

## Docker（仅后端）

```bash
docker build -t autoresearchlab .
docker run -p 8000:8000 -e GOOGLE_API_KEY=xxx autoresearchlab
```

前端本地运行，在 config.json 中将 `backend_port` 设为 `8000`。

## 项目结构

```
├── backend/       # FastAPI 后端
├── frontend/      # Next.js
├── maars/         # 实验规划与执行
└── data/db/       # config.json、SQLite
```

## 功能

- **Ideas**：输入领域，生成并细化选题
- **Experiments**：MAARS 分解任务、并行执行
- **Paper**：基于实验产出撰写草稿
