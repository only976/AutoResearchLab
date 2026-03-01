---
name: decomposition-patterns
description: Common patterns for decomposing research tasks. Use when decomposing complex tasks to ensure MECE (mutually exclusive, collectively exhaustive) splits and clear phase boundaries. Essential for Decompose tool. Apply when CheckAtomicity returns atomic=false.
---

# Decomposition Patterns

Reference patterns for task decomposition in research planning. Apply when CheckAtomicity returns atomic=false.

## Pattern Selection Flow

1. **Identify domain** → Literature, Technical comparison, Experiment, Survey, Documentation, Benchmark
2. **Identify boundaries** → Where does methodology change? Where is a handoff?
3. **Match pattern** → Use domain-specific pattern as template; adapt to boundaries found
4. **Verify MECE** → No overlap, no gaps; each child has one deliverable

## Phase-Based Decomposition

| Pattern | Phases | Example |
|---------|--------|---------|
| Research → Analyze → Report | 3 phases | Literature review, analysis, synthesis |
| Scope → Gather → Synthesize | 3 phases | Define scope, collect data, combine |
| Setup → Execute → Validate | 3 phases | Config, run, verify |
| Design → Implement → Test | 3 phases | Design first, then build, then test |
| Compare A → Compare B → Synthesize | 3 phases | Technical comparison (Python vs JS) |
| Search → Filter → Rank | 3 phases | Information retrieval pipeline |
| Hypothesis → Experiment → Analyze | 3 phases | Empirical research |
| Outline → Draft → Review → Finalize | 4 phases | Documentation, report writing |

## Domain-Specific Patterns

### Literature Review
- Search (keywords, databases) → Filter (relevance, quality) → Extract (key points) → Synthesize (themes, gaps) → Report
- **Parallel variant**: Search DB1 + Search DB2 (parallel) → Merge → Filter → Synthesize

### Technical Comparison
- Define criteria → Research option A → Research option B → Compare (table, pros/cons) → Recommend
- **N-way**: Define criteria → Research A, B, C (parallel) → Compare all → Recommend

### Survey/Interview Study
- Design (questions, sample) → Conduct (collect) → Transcribe/Code → Analyze → Report

### Experiment / Benchmark
- Hypothesis → Setup (env, config) → Run (execute) → Analyze (stats) → Conclusion
- **A/B variant**: Define metrics → Run A → Run B → Compare → Report

### Documentation / Report Writing
- Outline → Draft sections → Review/Revise → Finalize
- **Iterative**: Outline → Draft → Feedback → Revise → Finalize

### Gap Analysis / Feasibility Study
- Define scope → Gather current state → Identify gaps → Prioritize → Recommend

## Boundary Rules

- **One responsibility per child**: Each child has exactly one deliverable. If you cannot state it in one sentence, split further.
- **No overlap**: Siblings must not cover the same ground. MECE = Mutually Exclusive, Collectively Exhaustive.
- **Clear handoff**: Phase N's output is Phase N+1's explicit input. Name artifacts.
- **2–6 children typical**: Avoid single-child (task is atomic) or 7+ (over-split; consider merging).
- **Depth-appropriate**: Root = high-level phases; deeper levels = specific sub-steps.
- **Parallel vs sequential**: Parallel children have empty deps; sequential children depend on prior siblings.

## Task ID Convention

- Parent "0": children "1", "2", "3", ...
- Parent "1": children "1_1", "1_2", "1_3", ...
- Parent "1_1": children "1_1_1", "1_1_2", ...

## Anti-Patterns

- Splitting by "easy/hard" instead of phase or methodology
- Mixing methodology changes in one task (e.g. "collect and analyze")
- Tasks that depend on vague "context" instead of concrete artifacts
- Circular or redundant dependencies between siblings
- Including parent in dependencies (use task_id hierarchy instead)
- Over-splitting: 7+ children at one level → merge or introduce intermediate phases
- Under-splitting: "research and write report" as one task → split into gather + synthesize

## References

- For concrete examples, see [references/examples.md](references/examples.md)
