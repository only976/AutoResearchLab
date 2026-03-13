# MAARS Backend

运行方式见项目根 [README](../README.md#快速开始)。

## 叙事：Multi Agent

- **Idea Agent** (`idea_agent/`)：文献收集（Refine），LLM 单轮或 ADK 驱动
- **Plan Agent** (`plan_agent/`)：规划分解，LLM 单轮或 ADK 驱动
- **Task Agent** (`task_agent/`)：任务执行与验证，LLM 单轮或 ADK 驱动
- **Paper Agent** (`paper_agent/`)：论文草稿生成（Write），支持 Mock / 单轮 LLM / Agent-style MVP

## 四模式架构

| 模式 | 说明 | 实现 |
|------|------|------|
| **Mock** | 模拟输出，不调用真实 LLM | `*UseMock=True`（含 ideaUseMock、planUseMock、taskUseMock、paperUseMock），走 LLM 管道（mock_chat_completion） |
| **LLM** | 固定步骤 + 单轮 chat_completion | `*AgentMode=False`，collect_literature / _atomicity_and_decompose_recursive / execute_task |
| **Agent** | 多步编排（部分 Agent 为 ADK，Paper 为 Agent-style MVP） | `*AgentMode=True` |

Mock 与 LLM 共用同一 LLM 管道；Paper Agent 当前为轻量多步 MVP（outline → sections → assembly）。

## 会话隔离

- 后端按 `sessionId` 维护独立运行上下文（Idea/Plan/Paper run state + Task `ExecutionRunner`）
- `POST /api/session/init` 由后端签发 `sessionId + sessionToken`
- WebSocket 连接通过 `auth.sessionId + auth.sessionToken` 进入对应 room
- HTTP 请求通过 `X-MAARS-SESSION-ID + X-MAARS-SESSION-TOKEN` 绑定同一上下文
- 事件发射按 room 定向，不再全局广播
- 空闲会话按 TTL 自动回收（默认 7200 秒，可由 `MAARS_SESSION_IDLE_TTL_SECONDS` 配置）

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

## 解耦要点

1. **Skill I/O**：统一由 `shared/skill_utils` 提供，各 `agent_tools` 仅传入 `*_SKILLS_ROOT`
2. **ADK 桥接**：工具格式转换、`ExecutorTool` 封装由 `shared/adk_bridge` 统一处理
3. **ADK 运行时**：Runner 生命周期、事件循环、中止控制由 `shared/adk_runtime` 统一处理，减少三个 `adk_runner.py` 重复逻辑
4. **Realtime 事件**：thinking 事件 payload 组装由 `shared/realtime` 统一处理，减少路由重复代码
5. **LLM 调用**：单轮调用由 `shared/llm_client.chat_completion` 统一；Mock 由 `test/mock_stream.mock_chat_completion` 统一
