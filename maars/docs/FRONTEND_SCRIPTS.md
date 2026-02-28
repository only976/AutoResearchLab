# 前端脚本与模块依赖

`frontend/index.html` 中脚本加载顺序及模块依赖。

## 加载顺序

```
Socket.io → marked → DOMPurify → highlight.js  (第三方库)
    ↓
utils.js          # 工具函数 (escapeHtml, escapeHtmlAttr)，无依赖
    ↓
config.js         # API/存储配置，创建 window.MAARS
    ↓
task-tree.js      # 任务树渲染，依赖 utils
    ↓
theme.js          # 主题切换、API 配置模态框，依赖 config, utils
    ↓
api.js            # API 客户端，依赖 config
    ↓
plan.js           # 规划器 UI，依赖 config, api
    ↓
thinking.js       # 规划/执行 thinking 区域 + 任务输出，依赖 utils
    ↓
views.js          # 执行图、布局、执行状态，依赖 config, api, taskTree
    ↓
websocket.js      # Socket.io 事件分发，依赖 config, plan, views, thinking, output
    ↓
app.js            # 入口，组装各模块
```

## 模块依赖图

```
                    config
                      │
        ┌─────────────┼─────────────┐
        │             │             │
     theme          api           plan
        │             │             │
        └─────────────┴─────────────┘
                      │
              utils, task-tree
                      │
                  thinking
                      │
                   views
                      │
                 websocket
                      │
                    app
```

## 关键依赖说明

| 模块 | 依赖 | 说明 |
|------|------|------|
| utils | 无 | 必须最先加载（在 task-tree、thinking 之前） |
| task-tree | utils | 弹窗中 escapeHtml 用于安全渲染 |
| theme | config, utils | API 配置模态框 |
| websocket | plan, views, thinking, output | 所有 thinking/output 模块必须在 websocket 之前加载 |

## window.MAARS 结构

| 命名空间 | 模块 | 说明 |
|----------|------|------|
| `state.socket` | websocket | Socket.io 实例 |
| `state` | views, thinking, websocket | 共享状态 |
| `views` | views.js | 执行图、布局、执行状态 |
| `thinking` | thinking.js | 规划/执行 thinking 区域 |
| `output` | thinking.js | 任务输出渲染 |
| `plan` | plan.js | 规划器 UI |
| `taskTree` | task-tree.js | 任务树渲染 |

## 注意

- thinking 模块必须在 websocket 之前
- utils 必须在 task-tree、thinking 之前
