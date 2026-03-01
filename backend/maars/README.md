# MAARS Backend

运行方式见项目根 [README](../README.md#快速开始)。

## 叙事：Multi Agent

- **Plan Agent** (`plan_agent/`)：规划分解，Agent 实现；单轮 LLM 位于 `plan_agent/llm/`
- **Task Agent** (`task_agent/`)：任务执行与验证，Agent 实现；单轮 LLM 位于 `task_agent/llm/`

## 结构

| 目录 | 职责 |
|------|------|
| api/ | 路由、schemas、共享状态 |
| plan_agent/ | Plan Agent 实现：ReAct 循环（agent.py）+ 编排（index.py） |
| plan_agent/llm/ | Plan Agent 单轮 LLM（atomicity/decompose/format/quality） |
| task_agent/ | Task Agent 实现：ReAct 循环（agent.py）+ 编排（runner.py） |
| task_agent/llm/ | Task Agent 单轮 LLM（任务执行） |
| visualization/ | 分解树、执行图布局（只读 db 数据，计算、渲染） |
| db/ | 文件存储：db/{plan_id}/ |
| shared/ | 共享模块：graph、llm_client、skill_utils、utils |
| test/ | Mock AI |

## 数据流

```
plan.json ← plan_agent     execution.json ← plan_agent (execution_builder)     task_agent → 状态更新
layout ← visualization (读 db 数据，计算布局)
```
