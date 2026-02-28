---
name: atomicity-criteria
description: Criteria for judging if a task is atomic (executable in one step). Use with CheckAtomicity to decide when to Decompose vs FormatTask. Essential for atomicity decisions. Apply when processing each task in the planning workflow.
---

# Atomicity Criteria

A task is **atomic** (atomic: true) if ALL of the following hold. Otherwise, call Decompose.

## Four Criteria

1. **Single-step executable**: Can be completed in one LLM/expert call or one focused work session.
2. **Clear deliverable**: Has a well-defined output (document, list, report, artifact). No ambiguity about "done".
3. **No sub-phases**: Cannot be meaningfully split into distinct steps with different responsibilities.
4. **Reasonable granularity**: Appropriate scope for one session—neither trivial ("open a browser") nor too broad ("complete the entire research").

## Decision Flow

```
Can you name 2+ distinct sub-phases with different deliverables?
├── YES → atomic: false (Decompose)
└── NO → Is there one clear output in one session?
         ├── YES → atomic: true (FormatTask)
         └── UNCERTAIN → Prefer atomic if deliverable is well-defined
```

## Decision Rule

- **atomic: false** → You must be able to list 2+ specific sub-phases with different deliverables. Example: "Phase 1: collect data produces A; Phase 2: analyze produces B."
- **atomic: true** → One clear output, one focused session. When in doubt between one vs multiple sessions, prefer atomic if the deliverable is well-defined.

## Examples: Atomic

| Task | Why atomic |
|------|------------|
| "确定文献检索关键词与数据库范围" | One scoping decision, one output: keywords + scope |
| "检索并筛选2023-2024年AI领域核心论文" | One search session, one deliverable: filtered list |
| "撰写文献综述报告" | One writing session, one document |
| "定义假设与评估指标" | One decision, one output: hypothesis + metrics |
| "整理要点并撰写 Python 后端调研报告" | One synthesis session, one report (input already gathered) |
| "对比两者优缺点并撰写总结报告" | One comparison session, one report (inputs from prior tasks) |

## Examples: Non-Atomic

| Task | Why non-atomic |
|------|----------------|
| "文献调研：系统收集和综述..." | Explicit phases: collect + review, different deliverables |
| "实现并测试数据预处理模块" | Implementation vs testing are distinct phases |
| "调研Python与JavaScript生态并撰写对比报告" | Research phase + synthesis phase |
| "设计并执行实验" | Design vs execute are distinct |
| "调研 Python 后端生态：框架、性能、适用场景" | Scope → Gather → Synthesize are distinct phases |
| "收集资料并分析趋势" | Gather vs analyze are distinct methodologies |

## Borderline Cases

- **Single search + single filter**: Often atomic if one session produces one list.
- **Multiple methodologies**: If "research A" and "research B" are parallel, they can be separate atomic tasks. If "research then analyze" are sequential, decompose.
- **Deep hierarchy**: At deeper levels, tasks are often already more specific—lean toward atomic when deliverable is clear.
- **"整理并撰写" vs "收集并撰写"**: "整理并撰写" (organize + write from existing input) → often atomic. "收集并撰写" (gather + write) → non-atomic.
- **Context from siblings**: If a task's input comes from prior sibling artifacts, it may be atomic (e.g. "对比并撰写报告" when 1 and 2 produced research outputs).
