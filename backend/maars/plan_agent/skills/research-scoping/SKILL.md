---
name: research-scoping
description: Guidelines for scoping research ideas into actionable tasks. Use when the root idea is broad or ambiguous to ensure appropriate granularity and feasibility. Helps with initial decomposition. Apply at root (task "0") and when refining broad sub-tasks.
---

# Research Scoping

Guidelines for turning research ideas into well-scoped task trees. Apply at root (task "0") and when refining broad sub-tasks.

## Scoping Principles

1. **Concrete over vague**: "Compare Python vs JS for backend" not "Research languages"
2. **Deliverable-focused**: Each task should produce a clear artifact (document, list, config, report)
3. **Depth-appropriate**: Root level = high-level phases (2–6); deeper = specific sub-steps
4. **Dependency-aware**: Order by data flow. Gather before analyze. Setup before execute.
5. **Feasible scope**: Avoid "complete the entire research" as a single task; break into phases.
6. **Refine ambiguous ideas**: If the idea is "调研某技术" (research some tech), clarify: which tech? what aspects? what output?

## Common Research Structures

| Domain | Typical Phases | Notes |
|--------|----------------|-------|
| Literature review | Search → Filter → Synthesize → Report | Each phase has distinct methodology |
| Technical comparison | Scope → Research A → Research B → Compare | Parallel research, then synthesis |
| Experiment | Hypothesis → Setup → Run → Analyze | Sequential, data flows forward |
| Survey/Interview | Design → Conduct → Analyze → Report | Design defines Conduct; Conduct feeds Analyze |
| Benchmark/Evaluation | Define metrics → Setup → Run → Aggregate | Similar to Experiment |
| Documentation | Outline → Draft → Review → Finalize | Iterative refinement |
| Gap analysis | Define scope → Gather current state → Identify gaps → Recommend | Feasibility, maturity assessment |

## Granularity Guidelines

- **Root (depth 0)**: 2–6 phases. Each phase = distinct methodology or major deliverable.
- **Mid-level**: 2–4 sub-tasks per phase. Sub-tasks = concrete steps within that methodology.
- **Leaf (atomic)**: Single focused session, one clear output. No further decomposition.

## Refinement Tactics

When the idea is too broad:
- **Narrow by domain**: "AI in healthcare" → "AI for medical image diagnosis"
- **Narrow by output**: "Research X" → "Produce comparison report on X vs Y"
- **Add constraints**: "Survey frameworks" → "Survey Python web frameworks (2020+)"
- **Split by dimension**: "Evaluate tools" → "Evaluate by performance" + "Evaluate by ecosystem"

## Atomicity Hints

- **Atomic**: Single search, single analysis, single write-up, single decision, one clear deliverable
- **Non-atomic**: Multiple methodologies, distinct deliverables, handoff points, "and then" in description

## Red Flags

- Task description contains "and" linking two distinct activities → likely non-atomic
- "First X, then Y" → two phases, decompose
- No clear deliverable → refine description or decompose
- "调研" (research) without scope → add scope or decompose into scope + gather + synthesize
- Vague "分析" (analyze) without input spec → clarify what is being analyzed and from where
