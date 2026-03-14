# MAARS

Multi-Agent Automated Research System — 多智能体自动研究系统。从模糊 idea 到论文草稿的一站式研究流水线。

---

## 快速开始

**前置**：Python 3.10+

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:asgi_app --host 0.0.0.0 --port 3001 --loop asyncio --http h11
```

或使用项目根目录的 `./start.sh`（macOS/Linux）或 `start.bat`（Windows）。

访问 <http://localhost:3001> 进入首页。

---

## 使用流程

**Research** 是产品级工作单元。每个 Research 对应一个研究主题，贯穿 refine → plan → execute → paper 四阶段。

```text
首页输入 prompt → Create Research → 进入详情页 → Run 全流程 或 分阶段执行
```

| 页面 | 说明 |
| --- | --- |
| **首页** (`/` 或 `index.html`) | 输入研究主题，点击 Create 创建 Research |
| **Research 列表** (`research.html`) | 查看所有 Research，点击进入详情 |
| **Research 详情** (`research_detail.html?researchId=xxx`) | 执行 refine / plan / execute / paper 四阶段 |

| 阶段 | 作用 |
| --- | --- |
| Refine | 提取关键词、arXiv 检索、生成 refined idea |
| Plan | 将 idea 分解为可执行任务树 |
| Execute | 执行原子任务、验证产出 |
| Paper | 根据 Plan 与 Task 产出生成论文草稿（Markdown/LaTeX） |

每个阶段支持 **Run**（从头执行）、**Resume**（从 stopped/failed 恢复）、**Retry**（清空后重试）、**Stop**（中止）。

Thinking 区域展示推理过程，Output 区域展示最终产出（文献、任务 artifact、论文）。

---

## 四 Agent

| Agent | 职责 |
| --- | --- |
| Idea | 关键词提取、arXiv 检索、Refined Idea |
| Plan | 任务分解（atomicity → decompose → format → quality） |
| Task | 原子任务执行与验证 |
| Paper | 论文草稿生成（Markdown/LaTeX） |

每个 Agent 支持 **Mock**（模拟）、**LLM**（单轮）、**Agent**（工具循环）三种模式。
Settings → AI Config 中切换。Paper Agent 的 Agent 模式当前为 MVP：outline → sections → assembly。

---

## 配置

**Alt+Shift+S** (Win/Linux) 或 **Cmd+Shift+S** (Mac) 打开 Settings：

- **Theme** — 主题
- **AI Config** — Agent 模式、Idea RAG、Self-Reflection、API Preset
- **Data** — Restore recent plan、Clear all data

---

## 项目结构

```text
maars/
├── backend/           # FastAPI + 实时事件桥接（前端使用 SSE）
│   ├── api/           # 路由（idea、plan、execution、paper、research、plans、session、settings 等）
│   ├── idea_agent/    # Idea Agent
│   ├── plan_agent/    # Plan Agent
│   ├── task_agent/    # Task Agent
│   ├── paper_agent/   # Paper Agent
│   ├── shared/        # llm_client、skill_utils、reflection 等
│   ├── visualization/ # 执行图布局
│   └── db/            # SQLite 持久化封装（含 Research 元数据）+ sandbox 辅助
├── frontend/          # 静态页面、SSE/EventSource
│   ├── index.html     # 首页（创建 Research）
│   ├── research.html  # Research 列表
│   └── research_detail.html  # Research 详情（四阶段执行）
└── start.sh / start.bat  # 启动脚本
```

---

## 文档

| 文档 | 说明 |
| --- | --- |
| [docs/README.md](docs/README.md) | 文档索引 |
| [docs/DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md) | 开发指南（架构、Research API、Skill 扩充与维护） |
| [docs/workflow/](docs/workflow/) | 工作流说明（用户流程、Research 流程、四 Agent、实时事件） |
| [docs/FRONTEND_SCRIPTS.md](docs/FRONTEND_SCRIPTS.md) | 前端脚本与模块依赖 |
| [docs/RELEASE_NOTE_STANDARD.md](docs/RELEASE_NOTE_STANDARD.md) | Release Note 撰写标准 |
