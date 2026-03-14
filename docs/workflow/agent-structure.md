# Agent 目录结构规范

Idea、Plan、Task 三个 Agent 保持统一目录结构；Paper 结构不同，但已支持 `runner.py` 内的 agent-style MVP。

## 统一结构（Idea / Plan / Task）

```
{agent}/
├── agent.py           # Agent 入口（*AgentMode=True 时调用）
├── adk_runner.py      # Google ADK 驱动（仅 Agent 模式）
├── agent_tools.py     # 工具定义 + execute 逻辑
├── llm/               # Mock/LLM 模式
│   └── executor.py
├── prompts/           # {agent}-agent-prompt.txt、reflect-prompt.txt 及阶段 prompt
├── skills/            # SKILL.md + references/、scripts/（Task 专属）
└── __init__.py
```

## 各 Agent 差异

| 组件 | Idea | Plan | Task |
|------|------|------|------|
| 编排 | 无 | `index.py` | `runner.py` |
| 领域模块 | `arxiv.py`, `rag_engine.py` | `execution_builder.py` | `artifact_resolver.py`, `pools.py`, `web_tools.py`, `docker_runtime.py`, `docker/` |
| LLM | `executor.py` | `executor.py` | `executor.py`, `validation.py` |

## Paper Agent

仅 `runner.py` + `__init__.py`，无 agent.py、adk_runner、skills。Mock / LLM / agent-style MVP 均由 runner 直接编排并调用 `shared/llm_client`。

## Skills

- 位置：`{agent}/skills/{skill-name}/`，入口 `SKILL.md`（YAML frontmatter：`name`, `description`）
- 发现/加载：`shared/skill_utils.list_skills`、`load_skill`
- Task 可含 `scripts/`、`references/`；Idea/Plan 以 SKILL.md 为主

## 解耦要点

- **Skill**：`shared/skill_utils` 统一 I/O
- **ADK**：`shared/adk_bridge` 工具封装，`shared/adk_runtime` 生命周期与事件循环
- **Realtime**：`shared/realtime` 组装 thinking 事件
- **LLM**：`shared/llm_client.chat_completion`；Mock 走 `test/mock_stream`

## 会话

- `api/state.py`：`sessionId -> SessionState`，含 ExecutionRunner、各 Agent run_state
- `POST /api/session/init` 签发 sessionId + sessionToken
- HTTP 头 `X-MAARS-SESSION-*`、SSE query `sessionId/sessionToken` 绑定
- 后端 emitter 按 session 定向到 SSE 订阅者，并保留 Socket.IO auth / room 兼容层；空闲会话 TTL 回收
