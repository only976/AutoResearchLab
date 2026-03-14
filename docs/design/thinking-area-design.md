# Thinking 区域设计说明

Thinking 区域只负责展示 **AI 推理过程**，不展示最终产出。

## 核心原则

所有块统一为 **thinking 块结构**（header + 可选 body）：

| 有推理内容 | 无推理（调度/纯 JSON） |
|------------|-------------------------|
| header + body（Markdown 渲染） | header only（body 隐藏） |

「无 thinking」时 JSON 由树和 Output 消费，但 **header 仍展示**（source、operation、taskId、turn、tool_name）。

## 展示逻辑

- `blockType === 'schedule'` 或 `_isNoThinking(block)` → header-only
- 否则 → header + body

Header 格式：`source | operation | taskId | Turn N/M | tool_name(args)`，由 `_buildHeaderText(block)` 生成。

## 后端职责

| 模式 | 行为 |
|------|------|
| **LLM 单轮** | 流式 `chat_completion`，`on_chunk` 逐 token 转发到 `on_thinking` |
| **Agent 模式** | tool 调用时发 `on_thinking("", schedule_info={...})`，LLM 的 `content` 作为 thinking 发送 |

后端不做内容过滤：**完整流式输出**均发往 thinking。有 reasoning 则前端展示 thinking 块，纯 JSON 则用 schedule 样式。

## Prompt 约定

所有 prompt 统一鼓励「先 reasoning，再输出」，明确告知模型其推理会被展示。

## 数据流

```
SSE (*-thinking) → appendChunk → blocks[] → renderThinking
有 thinking：header + body；无 thinking：header only
```

JSON 由后端解析后写入 plan.json、idea.json、task artifact，由树和 Output 消费，不参与 Thinking 展示。
