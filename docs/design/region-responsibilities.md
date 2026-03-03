# Thinking / Output 区域职责规划

定义 MAARS 前端 **Thinking** 与 **Output** 两区域的职责边界、数据模型及 Agent 划分。

## 一、职责定义

| 区域 | 展示内容 | 不展示 |
|------|----------|--------|
| **Thinking** | AI 推理过程（reasoning + schedule） | 最终产出 |
| **Output** | 最终产出（idea 文献、task artifact、paper） | 推理过程、树结构 |

### Thinking 区域

- **LLM thinking**：Plan/Task/Idea 的流式 `content`
- **Agent schedule**：turn、tool_name、tool_args_preview
- 每个 block 带 `source`（Plan / Task / Idea）、`taskId`、`operation`

### Output 区域

| 来源 | Key | 产出类型 |
|------|-----|----------|
| Idea Agent | `idea` | 文献列表（keywords + papers） |
| Task Agent | `task_{task_id}` | 任务 artifact |
| Paper Agent | `paper` | 论文草稿 |
| Plan Agent | — | 不进入 Output，由 Tree View 承载 |

## 二、数据流

```
plan-thinking / task-thinking / idea-thinking / paper-thinking  →  Thinking 区域
task-output / idea-complete / paper-complete                   →  Output 区域
plan-tree-update                                               →  Tree View
```

## 三、事件格式

### ThinkingPayload

```typescript
interface ThinkingPayload {
  chunk: string;
  source: 'plan' | 'task' | 'idea' | 'paper';
  taskId?: string;
  operation?: string;
  scheduleInfo?: { turn?: number; max_turns?: number; tool_name?: string; tool_args_preview?: string };
}
```

### Output Key 规范

| source | key 格式 | 示例 |
|--------|----------|------|
| idea | `idea` | 固定 |
| task | `task_{task_id}` | `task_1`, `task_2` |
| paper | `paper` | 固定 |

## 四、实现要点

- **Clear 策略**：Refine/Plan 清空所有区域；Execute 清空 Thinking、任务状态、Output
- **Output 排序**：idea 置顶，task 按 task_id 排序
- **向后兼容**：旧 payload 无 `source` 时，前端按 `taskId` 推断
