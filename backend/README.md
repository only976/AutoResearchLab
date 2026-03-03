# MAARS Backend

运行方式见项目根 [README](../README.md#快速开始)。

## 叙事：Multi Agent

- **Idea Agent** (`idea_agent/`)：文献收集（Refine），LLM 单轮或 ADK 驱动
- **Plan Agent** (`plan_agent/`)：规划分解，LLM 单轮或 ADK 驱动
- **Task Agent** (`task_agent/`)：任务执行与验证，LLM 单轮或 ADK 驱动
- **Paper Agent** (`paper_agent/`)：论文草稿生成（Write），LLM 单轮，Mock/LLM 模式

## 四模式架构

| 模式 | 说明 | 实现 |
|------|------|------|
| **Mock** | 模拟输出，不调用真实 LLM | `*UseMock=True`（含 ideaUseMock、planUseMock、taskUseMock、paperUseMock），走 LLM 管道（mock_chat_completion） |
| **LLM** | 固定步骤 + 单轮 chat_completion | `*AgentMode=False`，collect_literature / _atomicity_and_decompose_recursive / execute_task |
| **Agent** | Google ADK 驱动，工具循环 | `*AgentMode=True`，adk_runner.run_*_agent_adk |

Mock 与 LLM 共用同一 LLM 管道；Agent 模式单独走 ADK。

## 结构

| 目录 | 职责 |
|------|------|
| api/ | 路由、schemas、共享状态 |
| idea_agent/ | Idea Agent：LLM 管道（collect_literature）+ ADK 驱动（adk_runner.py） |
| plan_agent/ | Plan Agent：LLM 管道（llm/）+ ADK 驱动（adk_runner.py）+ 编排（index.py） |
| plan_agent/llm/ | Plan Agent 单轮 LLM（atomicity/decompose/format/quality） |
| task_agent/ | Task Agent：LLM 管道（llm/）+ ADK 驱动（adk_runner.py）+ 编排（runner.py） |
| task_agent/llm/ | Task Agent 单轮 LLM（任务执行、验证） |
| shared/ | 共享模块：graph、llm_client、adk_bridge、skill_utils、utils |
| visualization/ | 分解树、执行图布局（只读 db 数据，计算、渲染） |
| db/ | 文件存储：db/{plan_id}/ |
| test/ | Mock AI |

## 数据流

```
plan.json ← plan_agent     execution.json ← plan_agent (execution_builder)     task_agent → 状态更新
layout ← visualization (读 db 数据，计算布局)
```

## 目录结构

三个 Agent 保持统一目录结构，详见 [docs/design/agent-structure.md](../docs/design/agent-structure.md)。Skills 的 list/load/read 由 `shared/skill_utils` 统一提供。
