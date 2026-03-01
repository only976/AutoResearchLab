# MAARS Flows - 流程约定

三个流程（idea、plan、task）相互独立，通过事件通信，不直接依赖。

> 架构规则见 `.cursor/rules/agent-flow-architecture.mdc`，三 Agent 基本流程与底层架构须统一。

## 事件约定

### Start 事件（流程开始）

| 事件 | 派发方 | 监听方 | 作用 |
|------|--------|--------|------|
| `maars:idea-start` | idea | thinking, output, task, taskTree | Idea 开始 → 各模块自清空 |
| `maars:plan-start` | plan | thinking, output, task, taskTree | Plan 开始 → 各模块自清空 |
| `maars:task-start` | task | thinking, output | Task 开始 → 各模块自清空 |
| `maars:restore-start` | api | thinking, output | Restore 开始 → 清空 thinking、output |
| `maars:restore-complete` | api | taskTree, task, output, idea, plan | Restore 完成 → 各模块自行恢复 UI |

### Complete 事件（流程完成）

| 事件 | 派发方 | 监听方 | 作用 |
|------|--------|--------|------|
| `maars:idea-complete` | websocket | plan, output | Idea 完成 → plan 更新按钮；output 展示 Refine 结果 |
| `maars:plan-complete` | websocket / settings | plan, task, taskTree, thinking | Plan 完成 → plan 更新 config、重置 UI；task 更新按钮、生成 layout；taskTree 渲染树、质量徽章；thinking 高亮 |
| `maars:task-complete` | websocket | task, thinking, output | Task 完成 → task 重置按钮；thinking/output 高亮 |

### Error 事件（流程失败）

| 事件 | 派发方 | 监听方 | 作用 |
|------|--------|--------|------|
| `maars:idea-error` | websocket | idea | Idea 失败 → idea.resetRefineUI |
| `maars:plan-error` | websocket | plan | Plan 失败 → plan.resetPlanUI |
| `maars:task-error` | websocket | task | Task 失败 → task.resetExecutionButtons |

### WebSocket 转发事件（websocket 仅转发，不直接调用业务模块）

| 事件 | 监听方 | 作用 |
|------|--------|------|
| `maars:plan-tree-update` | taskTree | 增量更新任务树 |
| `maars:execution-layout` | task | 设置执行布局 |
| `maars:task-states-update` | task, taskTree | 更新任务状态 |
| `maars:task-output` | output | 设置任务产出 |
| `maars:execution-sync` | task, taskTree | 连接时同步执行状态 |

### 用户操作事件

| 事件 | 派发方 | 监听方 | 作用 |
|------|--------|--------|------|
| `maars:task-retry` | taskTree | task | Popover Retry → task 调用 api.retryTask |
| `maars:task-resume` | taskTree | task | Popover Run from here → task 调用 api.resumeFromTask |
| `maars:switch-to-output-tab` | output | app | Refine 完成 → 切换到 Output 标签 |

### 后端事件（Socket.io，三个 Agent 前缀统一）

| 前缀 | 基本事件 | 额外事件 |
|------|----------|----------|
| plan | plan-start, plan-thinking, plan-error, plan-complete | plan-tree-update |
| idea | idea-start, idea-thinking, idea-error, idea-complete | — |
| task | task-start, task-thinking, task-error, task-complete | task-states-update, task-output, execution-layout |

**基本事件语义**：
- **start**：数据流起点，不触发 UI 清空
- **thinking**：按前缀确定样式，流式写入 thinking 区域（由 `ws/handlers/thinking-handler.js` 处理）
- **error**：websocket 派发 `maars:*-error`，由对应 flow 监听并重置 UI
- **complete**：websocket 派发 `maars:*-complete`（含 detail），由各模块自行处理

### 前后端事件职责分离

- **前端事件**（`maars:idea-start`、`maars:plan-start`、`maars:task-start`）：用户点击时派发；thinking、output、taskTree 各自监听并清空
- **websocket**：仅转发后端事件为 `maars:*` 事件，不直接调用 idea/plan/task/output/taskTree
- **各模块**：监听对应事件，自行处理 UI 更新

## 流程对称性

```
idea-start   → idea-complete
plan-start   → plan-complete
task-start   → task-complete（由 websocket 收到 task-complete 后派发）
```

## 按钮启用规则

| 按钮 | 管理方 | 启用条件 |
|------|--------|----------|
| Refine | idea | 输入框有内容 |
| Plan | plan | hasIdea（db 有 idea_id） |
| Execute | task | hasIdea && hasPlan（db 有 idea_id 和 plan_id） |
| Stop（Refine/Plan/Execute） | 各 flow | 运行时显示，点击调用 api.stopAgent |

## 统一终止函数

- **api.stopAgent(agent)**：`agent` 为 `'idea'|'plan'|'task'`
- 对应后端：`POST /api/idea/stop`、`/api/plan/stop`、`/api/execution/stop`
- 后端停止后通过 WebSocket 推送 `*-error`；前端监听并调用各模块的 reset 方法
- 用户主动停止时 error 含 "stopped by user"，前端不弹 alert

## 模块职责

| 模块 | 职责 | 依赖 |
|------|------|------|
| idea.js | Refine 流程、Refine 按钮 | config, api |
| plan.js | Plan 流程、Plan 按钮 | config, api |
| task.js | Execute 流程、Execute 按钮、layout、stats | config, api |

## 派发时机

- **idea-start**：idea.runRefine 开始时
- **idea-complete**：websocket 收到 idea-complete → 派发 maars:idea-complete
- **idea-error**：websocket 收到 idea-error → 派发 maars:idea-error
- **plan-start**：plan.generatePlan 开始时
- **plan-complete**：websocket 收到 plan-complete → 派发 maars:plan-complete
- **restore-complete**：api.restoreRecentPlan 成功 → 派发 maars:restore-complete（各模块监听并恢复 UI，不再派发 idea-complete/plan-complete）
- **plan-error**：websocket 收到 plan-error → 派发 maars:plan-error
- **task-start**：task.runExecution 开始时
- **task-complete**：websocket 收到 task-complete → 派发 maars:task-complete
- **task-retry / task-resume**：taskTree popover 点击 Retry/Run from here 时派发
