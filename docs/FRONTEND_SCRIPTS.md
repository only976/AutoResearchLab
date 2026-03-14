# 前端脚本与模块依赖

不同页面加载的脚本不同。Research 流程由 `research.js` 统一驱动，替代原先的 idea.js / plan.js / paper.js 独立流程。

当前前端实时通道使用浏览器原生 `EventSource` 订阅 `/api/events/stream`。文件名仍保留为 `websocket.js` / `thinking-handler.js`，但实现已经切到 SSE。

## 页面对应

| 页面 | 入口 | 主要脚本 |
|------|------|----------|
| 首页 | `index.html` | research.js、task.js、output、thinking、task-tree |
| Research 列表 | `research.html` | research.js（无 task/output/thinking） |
| Research 详情 | `research_detail.html` | research.js、task.js、output、thinking、task-tree |

## 加载顺序（Research 详情页 / 首页）

```
marked → DOMPurify → highlight.js  (第三方库；实时通道使用浏览器原生 EventSource)
    ↓
utils.js          # 工具函数 (escapeHtml, escapeHtmlAttr)，无依赖
    ↓
toast.js          # 轻量通知组件，依赖 utils
    ↓
config.js         # API/存储配置，创建 window.MAARS
    ↓
state.js          # 共享状态
    ↓
task-tree.js      # 任务树渲染，依赖 utils（详情页/首页）
    ↓
theme.js          # 主题切换、API 配置模态框，依赖 config, utils
    ↓
api.js            # API 客户端，依赖 config
    ↓
task.js           # Task 流程（任务输出弹窗等）
research.js       # Research 流程（Create、四阶段 Run/Resume/Retry/Stop）
    ↓
output.js         # Output 区域渲染（详情页/首页）
    ↓
thinking.js       # Thinking 区域渲染
    ↓
thinking-handler.js   # SSE thinking 事件注册
    ↓
websocket.js      # EventSource/SSE 连接与事件分发（文件名保留）
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
     theme          api        research, task
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
| research | config, api | Research 流程（Create、四阶段） |
| task | config, api | Task 输出弹窗、任务树交互 |
| websocket | config, wsHandlers.thinking | 建立 SSE 连接并转发后端事件；事件消费者需先完成注册 |

## 流程职责

| 模块 | 职责 |
|------|------|
| `research.js` | 首页 Create、Research 详情加载、四阶段 Run/Resume/Retry/Stop、阶段状态同步 |
| `task.js` | Execute 区域交互、任务树弹窗、任务级 retry/resume 入口 |
| `websocket.js` | 建立 `EventSource` 连接，把后端事件桥接成 `maars:*` 前端事件 |
| `thinking-handler.js` | 注册 `*-thinking` 事件并写入 Thinking 区域 |
| `idea.js` / `plan.js` / `paper.js` | 遗留 flow，当前主链路不再直接依赖 |

## 事件桥接

### 后端实时事件

| 事件 | 前端用途 |
|------|----------|
| `idea-start` / `plan-start` / `task-start` / `paper-start` | 触发 Thinking、Output、Tree 等区域自清空 |
| `idea-complete` | 更新 Refine 面板与 Output |
| `plan-tree-update` / `plan-complete` | 更新分解树、布局和阶段状态 |
| `task-states-update` / `task-output` / `task-complete` | 更新执行状态、输出流和 Output 区域 |
| `execution-layout` | 更新 Execute 视图布局 |
| `paper-complete` | 更新论文草稿面板与 Output |
| `research-stage` / `research-error` | 更新四阶段状态条与错误信息 |

### 前端事件

| 事件 | 作用 |
|------|------|
| `maars:task-retry` | 从任务树触发单任务重试 |
| `maars:task-resume` | 从任务树触发从指定节点继续执行 |
| `maars:switch-to-output-tab` | 产出更新后切换到 Output 标签 |

## window.MAARS 结构

| 命名空间 | 模块 | 说明 |
|----------|------|------|
| `config` | config.js | API 配置、ensureSession、resolvePlanIds |
| `state` | state.js, websocket | 共享状态，含 `state.es`（兼容保留 `state.socket` 槽位） |
| `api` | api.js | API 客户端 |
| `research` | research.js | Research 流程（Create、四阶段 Run/Resume/Retry/Stop） |
| `task` | task.js | Task 流程（Execute 输出弹窗、任务树） |
| `output` | output.js | Output 区域 |
| `thinking` | thinking.js | Thinking 区域 |
| `taskTree` | task-tree.js | 任务树渲染 |
| `theme` | theme.js | 主题切换 |
| `toast` | toast.js | 轻量通知 API |
| `settings` | settings.js | Settings 弹窗 |
| `ws` | websocket.js | SSE 初始化 |
| `wsHandlers.thinking` | thinking-handler.js | SSE thinking 事件注册 |

## 注意

- thinking、output 模块必须在 `websocket.js` 建立连接前完成加载
- utils 必须在 task-tree、thinking 之前
- research、task 在 api 之后、`websocket.js` 之前
- research.html 不加载 task、output、thinking、task-tree（仅创建/列表页），但仍会建立 SSE 连接以刷新 Research 列表与阶段状态
