# MAARS

Multi-Agent Automated Research System（多智能体自动研究系统）

## 快速开始

**前置**：已安装 [Python 3.10+](https://www.python.org/downloads/) 并勾选 “Add Python to PATH”。

```bash
cd backend
python -m pip install -r requirements.txt
python -m uvicorn main:asgi_app --host 0.0.0.0 --port 3001 --loop asyncio --http h11
```

在浏览器中访问 **http://localhost:3001**

刷新页面会自动填充示例 idea。**Refine** 可从模糊 idea 提取关键词并检索 arXiv 文献；**Plan** 将 idea 分解为任务树；**Execute** 执行任务。

## 核心流程

### 0. Refine（可选）

用户输入模糊 idea → **Refine** 按钮 → Idea Agent 提取关键词 → arXiv 检索 → 文献列表展示于 Output，并创建 idea_id。

### 1. Generate Plan（规划）

用户输入 idea → Plan Agent 递归分解为任务树 → 保存 `plan.json`

- **Atomicity**：判断任务是否可直接执行（原子任务）
- **Decompose**：非原子任务分解为 2–6 个子任务，仅同级依赖
- **Format**：为原子任务生成 input/output 规范

### 2. Generate Map（执行图）

从 plan 提取原子任务 → 解析依赖（继承+下沉）→ 拓扑排序分 stage → 保存 `execution.json`

### 3. Execution（执行）

Task Agent 池并行执行就绪任务，每个任务执行后 Validate，实时状态推送。Thinking 区域展示 Refine/Plan/Execute 阶段、轮次、工具调用及参数摘要（如 `ReadFile(path: sandbox/notes.txt)`）。

## 四 Agent 工作流程

统一流程模型：**用户点击 → HTTP POST 触发 → 后端后台任务 → WebSocket 数据回传 → 前端更新 UI**。四个 Agent 均采用相同模式：HTTP 仅用于触发并立即返回 `{success, id}`，所有流式数据（thinking、tree、output）、完成状态与错误均通过 WebSocket 推送；前端不依赖 HTTP 响应，仅用 WebSocket 事件更新 UI。

| Agent | 职责 | 触发 | 事件 |
|-------|------|------|------|
| **Idea Agent** | 关键词提取、arXiv 检索、Refined Idea 生成 | Refine 按钮 | idea-start / idea-thinking / idea-complete |
| **Plan Agent** | 任务分解（atomicity → decompose → format → quality） | Plan 按钮 | plan-start / plan-thinking / plan-tree-update / plan-complete |
| **Task Agent** | 原子任务执行与验证 | Execute 启动 | task-start / task-thinking / task-states-update / task-output / task-complete |
| **Paper Agent** | 根据 Plan 与 Task 产出生成论文草稿 | Write 按钮 | paper-start / paper-thinking / paper-complete |

Idea / Plan / Task 均支持 Stop 中止、流式 thinking、error 时按钮重置、Self-Reflection（自迭代：评估输出质量 → 生成 skill → 重执行）。

## 三模式架构（Mock / LLM / Agent）

每个 Agent（Idea、Plan、Task、Paper）可选 **Mock**、**LLM**、**Agent** 三种模式；Paper Agent 支持 Mock/LLM，Agent 模式待开发。

| 模式 | 说明 | 数据流 |
|------|------|--------|
| **Mock** | 模拟输出，不调用真实 LLM | 与 LLM 共用管道，`*UseMock=True` 时走 mock_chat_completion |
| **LLM** | 固定步骤 + 单轮 chat_completion | Idea: collect_literature；Plan: _atomicity_and_decompose_recursive；Task: execute_task |
| **Agent** | Google ADK 驱动，工具循环 | Idea/Plan/Task: adk_runner.run_*_agent_adk |

Mock 与 LLM 均走 LLM 管道，仅 `*UseMock` 区分；Agent 模式单独走 Google ADK，无 Mock 分支。

| Agent | Mock | LLM | Agent |
|-------|------|-----|-------|
| **Idea Agent** | ✅ collect_literature (mock) | ✅ collect_literature (LLM) | ✅ adk_runner（ExtractKeywords、SearchArxiv、FilterPapers、RefineIdea 等） |
| **Plan Agent** | ✅ 递归分解 (mock) | ✅ 递归分解 (LLM) | ✅ adk_runner（CheckAtomicity、Decompose、FormatTask 等） |
| **Task Agent** | ✅ execute_task (mock) | ✅ execute_task (LLM) | ✅ adk_runner（ReadFile、WebSearch、Finish 等） |
| **Paper Agent** | ✅ mock_chat_completion (paper.json) | ✅ 单轮 LLM 生成论文 | 待开发 |

## Agent 工作流（详细）

### Idea Agent

Refine 按钮触发，从模糊 idea 提取关键词并检索 arXiv 文献。LLM 单轮或 Agent 模式（`ideaAgentMode`）。Agent 模式支持迭代检索、论文筛选、CoT 分析、自检重试。流式 thinking 通过 `idea-thinking` 推送。

### Plan Agent

多轮调用工具完成分解，可 LoadSkill 加载技能（分解模式、研究范围、格式规范等）：

| 工具 | 用途 |
|------|------|
| CheckAtomicity | 判断任务是否原子 |
| Decompose | 分解为非原子子任务 |
| FormatTask | 为原子任务生成 input/output |
| AddTasks / UpdateTask | 增改任务 |
| GetPlan / GetNextTask | 读取当前计划 |
| ListSkills / LoadSkill | 加载 Plan Agent 技能 |

### Task Agent

多轮调用工具完成任务，每个任务在独立沙箱中运行，可 LoadSkill 加载技能（markdown-reporter、json-utils、task-output-validator 等）：

| 工具 | 用途 |
|------|------|
| ReadArtifact | 读取依赖任务输出 |
| ReadFile / WriteFile | 读写沙箱内文件 |
| WebSearch / WebFetch | 网页搜索与 URL 抓取（调研任务可引用真实来源） |
| ReadSkillFile / RunSkillScript | 读取并执行技能脚本 |
| ListSkills / LoadSkill | 加载 Executor 技能 |
| Finish | 提交任务输出 |

**验证**：LLM 模式下由系统调用 `llm/validation` 做 LLM 校验；Agent 模式下由 Agent 在 Finish 前通过 task-output-validator 技能自检。

**引用与来源**：调研/对比类报告需包含 `## References` 小节；Format 阶段会为研究任务自动加入引用校验。可选加载 source-attribution 技能强化引用规范。

### Paper Agent

根据 Plan 与 Task 产出生成论文草稿。当前仅 LLM 管道（单轮生成），支持 Markdown / LaTeX 格式。Agent 模式（工具调用、多轮推理）待开发。

## 项目结构

```
maars/
├── backend/
│   ├── main.py          # FastAPI + Socket.io 入口
│   ├── api/             # 路由、schemas、state
│   ├── idea_agent/      # Idea Agent：关键词提取、arXiv 检索
│   │   ├── llm/         # Idea Agent LLM 实现
│   │   ├── agent.py     # Idea Agent ReAct 模式
│   │   ├── prompts/     # idea-agent-prompt.txt、reflect-prompt.txt
│   │   └── skills/      # Idea Agent skills（含 learned/）
│   ├── plan_agent/      # Plan Agent：atomicity → decompose → format（业务逻辑）
│   │   ├── llm/         # Plan Agent LLM 实现
│   │   ├── agent.py     # Plan Agent ReAct 模式
│   │   ├── prompts/     # plan-agent-prompt.txt、reflect-prompt.txt
│   │   └── skills/      # Plan Agent skills
│   ├── task_agent/      # Task Agent：runner、execution、skills
│   │   ├── llm/         # Task Agent LLM 实现（executor + validation）
│   │   ├── agent.py     # Task Agent ReAct 模式
│   │   ├── prompts/     # reflect-prompt.txt
│   │   └── skills/      # task-output-validator、markdown-reporter 等
│   ├── paper_agent/     # Paper Agent：单轮 LLM 论文生成
│   ├── visualization/   # 分解树、执行图布局
│   ├── shared/          # 共享模块：graph、llm_client、reflection、constants、skill_utils
│   ├── db/              # 文件存储：db/{idea_id}/{plan_id}/、settings.json
│   └── test/            # Mock AI（mock-ai/refine.json、execute.json 等）
└── frontend/            # 静态页面、任务树、WebSocket
```

## 配置

按 **Alt+Shift+S** 打开 **Settings**：**Theme**（主题）、**AI Config**（Agent Mode、Idea RAG、Self-Reflection、Preset）、**Data**（Restore recent plan、Clear all data）。

## 文档

- [文档索引](docs/README.md)（工作流、设计文档、前端脚本等）
- [工作流文档](docs/workflow/README.md)
- [前端脚本与模块依赖](docs/FRONTEND_SCRIPTS.md)
- [Release Note 标准](docs/RELEASE_NOTE_STANDARD.md)
- [执行图布局规则](backend/visualization/EXECUTION_LAYOUT_RULES.md)
