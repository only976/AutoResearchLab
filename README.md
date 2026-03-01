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

**配置**：编辑 `backend/db/config.json` 或访问 Config 页面，设置 LLM API Key 及前端端口。

**启动**：一行命令同时启动后端和前端。

```bash
node start.js
```

后端固定端口 8888，前端端口从 config.json 读取（默认 3030）。按 `Ctrl+C` 可同时停止两者。

单独启动：`node start.js backend` 或 `node start.js frontend`

访问 `http://localhost:<frontend_port>`（默认 3030，见 config.json）

## Docker（仅后端）

```bash
docker build -t autoresearchlab .
docker run -p 8000:8000 -e GOOGLE_API_KEY=xxx autoresearchlab
```

前端本地运行，默认连接后端 `http://localhost:8888`（可通过 `API_BASE_URL` 环境变量覆盖）。

## 项目结构

```
├── backend/       # FastAPI 后端
│   ├── db/       # config.json、SQLite、MAARS 数据
│   └── maars/    # MAARS 实验规划与执行
└── frontend/     # Next.js
    └── src/maars/ # MAARS React 组件与 API
```

## 功能

- **Ideas**：输入领域，生成并细化选题
- **Experiments**：MAARS 分解任务、并行执行
- **Paper**：基于实验产出撰写草稿
