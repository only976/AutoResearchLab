# 四 Agent 流程

## 概览

| Agent | 职责 | 触发 | 产出 |
|-------|------|------|------|
| **Idea** | 关键词提取、arXiv 检索、Refined Idea | Refine 按钮 | keywords + papers + refined_idea |
| **Plan** | 任务分解 | Plan 按钮 | 任务树（Tree View） |
| **Task** | 执行原子任务、验证 | Execute 启动 | task artifact |
| **Paper** | 论文草稿生成 | Write 按钮 | Markdown/LaTeX 草稿 |

---

## Idea Agent

**流程**：用户 idea → Keywords（流式）→ arXiv 检索 → Refine（流式）→ 保存 idea

**Agent 模式**：ExtractKeywords → SearchArxiv → EvaluatePapers → FilterPapers → AnalyzePapers → RefineIdea → ValidateRefinedIdea → FinishIdea

**产出**：`idea-complete` 回传 `{ideaId, keywords, papers, refined_idea}`

---

## Plan Agent

**流程**：idea → 递归：Atomicity → [Decompose | Format] → Quality 评估 → 任务树

**Agent 模式**：CheckAtomicity、Decompose、FormatTask、AddTasks、GetPlan、GetNextTask、FinishPlan、LoadSkill 等

**产出**：`plan-tree-update` 推送到 Tree View，不进入 Output

---

## Task Agent

**流程**：任务依赖满足 → Execute → Validate → artifact

**Agent 模式**：ReadArtifact、ReadFile、WriteFile、WebSearch、WebFetch、Finish 等

**产出**：`task-output` → `task_{task_id}`

**验证**：LLM 模式由 `llm/validation` 校验；Agent 模式由 task-output-validator 技能在 Finish 前自检

---

## Paper Agent

**流程**：Plan + Task 产出 → 单轮 LLM 生成 → 论文草稿（Write 按钮触发）

**产出**：`paper-complete` 回传 `{content, format}`

**说明**：当前仅 Mock/LLM 模式，Agent 模式待开发

---

## Self-Reflection（可选）

Idea / Plan / Task 支持自迭代：执行完成后评估质量 → 低分则生成 skill 并重执行。

**配置**：Settings → AI Config → Self-Reflection（enabled、maxIterations、qualityThreshold）

**事件**：复用 `*-thinking`，`operation="Reflect"`；`*-complete` 含 `reflection` 字段
