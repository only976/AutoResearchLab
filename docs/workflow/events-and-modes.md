# 事件与模式

## 实时事件（前端通过 SSE / EventSource 订阅）

后端 realtime emitter 会同时镜像到 SSE 订阅者，并保留 Socket.IO room 兼容层；当前浏览器前端默认走 SSE。

### 基本事件（四 Agent 统一）

| 事件 | 说明 |
|------|------|
| `{prefix}-start` | 数据流起点 |
| `{prefix}-thinking` | 流式推理内容，按 prefix 区分样式 |
| `{prefix}-error` | 失败时前端重置按钮 |
| `{prefix}-complete` | 携带完整数据，各模块处理 |

### 额外事件

| 前缀 | 额外事件 |
|------|----------|
| plan | `plan-tree-update` |
| task | `task-states-update`, `task-output`, `execution-layout` |
| research | `research-stage`（阶段状态）、`research-error`（Research 级错误） |

### Thinking 事件格式

```typescript
interface ThinkingPayload {
  chunk: string;
  source: 'plan' | 'task' | 'idea' | 'paper';
  taskId?: string;
  operation?: string;  // Keywords, Refine, Atomicity, Decompose, Execute, Validate...
  scheduleInfo?: { turn?: number; max_turns?: number; tool_name?: string; tool_args_preview?: string };
}
```

---

## 三模式架构

| 模式 | 说明 | 数据流 |
|------|------|--------|
| **Mock** | 模拟输出，不调用真实 LLM | `*UseMock=True` 时走 mock_chat_completion |
| **LLM** | 固定步骤 + 单轮 chat_completion | Idea: collect_literature；Plan: 递归分解；Task: execute_task |
| **Agent** | 多步编排；Idea/Plan/Task 用 Google ADK，Paper 用 agent-style MVP | `adk_runner.run_*_agent_adk` / `paper_agent.runner` |

Mock 与 LLM 共用 LLM 管道；Idea/Plan/Task 的 Agent 模式走 Google ADK，Paper Agent 的 Agent 模式走 agent-style MVP。

### 模式切换

| Agent | Mock | LLM | Agent |
|-------|------|-----|-------|
| Idea | ✅ | ✅ | ✅ |
| Plan | ✅ | ✅ | ✅ |
| Task | ✅ | ✅ | ✅ |
| Paper | ✅ | ✅ | ✅（MVP） |

---

## 实现位置速查

| Agent | 编排 | LLM 执行 | Agent 模式 |
|-------|------|----------|------------|
| Idea | `api/routes/idea.py` | `idea_agent/llm/executor.py` | `idea_agent/adk_runner.py` |
| Plan | `plan_agent/index.py` | `plan_agent/llm/executor.py` | `plan_agent/adk_runner.py` |
| Task | `task_agent/runner.py` | `task_agent/llm/executor.py` | `task_agent/adk_runner.py` |
| Paper | `api/routes/paper.py` | `paper_agent/runner.py` | `paper_agent/runner.py`（agent-style MVP） |

---

## phase 配置

| Agent / 阶段 | merge_phase_config phase |
|--------------|--------------------------|
| Idea | `idea` |
| Plan | `atomicity`, `decompose`, `format`, `quality` |
| Task | `execute`, `validate` |
| Paper | `paper` |
