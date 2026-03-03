# MAARS 工作流文档

## 文档索引

| 文档 | 说明 |
|------|------|
| [用户流程](user-flow.md) | 一图看懂：Refine → Plan → Execute → Paper |
| [四 Agent 流程](agents.md) | Idea / Plan / Task / Paper 各 Agent 的触发、流程、产出 |
| [事件与模式](events-and-modes.md) | WebSocket 事件、Mock/LLM/Agent 模式、技术参考 |

## 统一流程模型

```
用户点击 → HTTP POST 触发 → 后端后台任务 → WebSocket 数据回传 → 前端更新 UI
```

- **HTTP**：仅用于触发，立即返回 `{success, id}`
- **WebSocket**：所有流式数据、完成状态、错误均由后端推送
- **前端**：不依赖 HTTP 响应，仅用 WebSocket 事件更新 UI
