# 前端脚本与模块依赖

`frontend/index.html` 中脚本加载顺序及模块依赖。

## 加载顺序

```
Socket.io → marked → DOMPurify → highlight.js  (第三方库)
    ↓
utils.js          # 工具函数 (escapeHtml, escapeHtmlAttr)，无依赖
    ↓
toast.js          # 轻量通知组件，依赖 utils
    ↓
config.js         # API/存储配置，创建 window.MAARS
    ↓
state.js          # 共享状态
    ↓
task-tree.js      # 任务树渲染，依赖 utils
    ↓
theme.js          # 主题切换、API 配置模态框，依赖 config, utils
    ↓
api.js            # API 客户端，依赖 config
    ↓
idea.js / plan.js / task.js / paper.js   # 各 Agent 流程（flows）
    ↓
output.js         # Output 区域渲染
    ↓
thinking.js       # Thinking 区域渲染
    ↓
thinking-handler.js   # WebSocket thinking 事件注册
    ↓
websocket.js      # Socket.io 连接与事件分发
    ↓
settings.js       # Settings 弹窗
    ↓
app.js            # 入口，组装各模块
```

## 模块依赖图

```
                    config
                      │
        ┌─────────────┼─────────────┐
        │             │             │
     theme          api        flows (idea/plan/task/paper)
        │             │             │
        └─────────────┴─────────────┘
                      │
              utils, task-tree, state
                      │
              output, thinking
                      │
            thinking-handler, websocket
                      │
              settings, app
```

## 关键依赖说明

| 模块 | 依赖 | 说明 |
|------|------|------|
| utils | 无 | 必须最先加载（在 task-tree、thinking 之前） |
| task-tree | utils | 弹窗中 escapeHtml 用于安全渲染 |
| theme | config, utils | API 配置模态框 |
| flows | config, api | idea.js、plan.js、task.js、paper.js 各 Agent 流程 |
| websocket | config, flows, output, thinking | 所有 thinking/output 模块必须在 websocket 之前加载 |

## window.MAARS 结构

| 命名空间 | 模块 | 说明 |
|----------|------|------|
| `config` | config.js | API 配置、getCurrentIdeaId、resolvePlanIds |
| `state` | state.js, websocket | 共享状态，含 `state.socket` |
| `api` | api.js | API 客户端 |
| `idea` | idea.js | Idea 流程（Refine 按钮） |
| `plan` | plan.js | Plan 流程（Plan 按钮） |
| `task` | task.js | Task 流程（Execute 按钮） |
| `paper` | paper.js | Paper 流程（Write 按钮） |
| `output` | output.js | Output 区域 |
| `thinking` | thinking.js | Thinking 区域 |
| `taskTree` | task-tree.js | 任务树渲染 |
| `theme` | theme.js | 主题切换 |
| `toast` | toast.js | 轻量通知 API |
| `settings` | settings.js | Settings 弹窗 |
| `ws` | websocket.js | WebSocket 初始化 |
| `wsHandlers.thinking` | thinking-handler.js | WebSocket thinking 事件注册 |

## 注意

- thinking、output 模块必须在 websocket 之前
- utils 必须在 task-tree、thinking 之前
- flows 在 api 之后、websocket 之前
