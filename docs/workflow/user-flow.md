# 用户流程

## 一图看懂

```
用户输入 idea
      │
      ▼
┌─────────────┐
│   Refine    │  可选：提取关键词 → arXiv 检索 → 文献列表
└─────────────┘
      │
      ▼
┌─────────────┐
│    Plan     │  任务分解：Atomicity → Decompose → Format → 任务树
└─────────────┘
      │
      ▼
┌─────────────┐
│  Execute    │  执行原子任务 → 验证 → artifact
└─────────────┘
      │
      ▼
┌─────────────┐
│ 生成论文    │  Plan + Task 产出 → 论文草稿
└─────────────┘
```

## 按钮行为

| 按钮 | 触发 | 清空范围 |
|------|------|----------|
| **Refine** | Idea Agent | 所有区域（Thinking、Output、Plan 树、Execution 树） |
| **Plan** | Plan Agent | 所有区域，并创建新 plan |
| **Execute** | Task Agent | Thinking、任务状态、Output |
| **Write** | Paper Agent | 仅 paper 槽位 |

**层级**：Refine 与 Plan 同级；Execute 在 Plan 之下，对当前 plan 重新执行。

## 数据流向

| 区域 | 内容来源 |
|------|----------|
| **Thinking** | 各 Agent 的推理过程（*-thinking） |
| **Output** | idea 文献、task artifact、paper 草稿 |
| **Tree View** | plan-tree-update（任务树） |
