# 四 Agent 流程

Idea / Plan / Task / Paper 各 Agent 的触发、流程、产出。Research 流水线串联四阶段时，由后端依次调用并通过 SSE 派发对应事件。

## 概览

| Agent | 职责 | 触发 | 产出 |
|-------|------|------|------|
| **Idea** | 关键词提取、arXiv 检索、Refined Idea | Refine 阶段 | keywords + papers + refined_idea |
| **Plan** | 任务分解 | Plan 阶段 | 任务树（Tree View） |
| **Task** | 执行原子任务、验证 | Execute 阶段 | task artifact |
| **Paper** | 论文草稿生成 | Paper 阶段 | Markdown/LaTeX 草稿 |

## Idea Agent

**流程**：用户 idea → Keywords（流式）→ arXiv 检索 → Refine（流式）→ 保存 idea

**Agent 模式**：ExtractKeywords、SearchArxiv、EvaluatePapers、FilterPapers、AnalyzePapers、RefineIdea、ValidateRefinedIdea、FinishIdea、ListSkills、LoadSkill、ReadSkillFile

**产出**：`idea-complete` 回传 `{ideaId, keywords, papers, refined_idea}`

## Plan Agent

**流程**：idea → 递归：Atomicity → [Decompose | Format] → Quality 评估 → 任务树

**Agent 模式**：CheckAtomicity、Decompose、FormatTask、AddTasks、GetPlan、GetNextTask、FinishPlan、LoadSkill 等

**产出**：`plan-tree-update` 推送到 Tree View，`plan-complete` 标记阶段完成

## Task Agent

**流程**：任务依赖满足 → Execute → Validate → artifact

**Agent 模式**：ReadArtifact、ReadFile、WriteFile、WebSearch、WebFetch、Finish、ListSkills、LoadSkill、ReadSkillFile、RunSkillScript

**产出**：`task-output` 更新 Output 区域 / 弹窗，`task-states-update` 与 `task-complete` 更新执行状态

## Paper Agent

**流程**：Plan + Task 产出 → 单轮 LLM 或 agent-style MVP（outline → sections → assembly）→ 论文草稿

**产出**：`paper-complete` 回传 `{content, format}`

**说明**：支持 Mock / LLM / Agent 三种模式；Agent 模式为不依赖 ADK 的 drafting MVP
