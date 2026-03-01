---
name: comparison-report
description: Produce comparison reports between two or more options (technologies, approaches, products). Use when task involves comparing, evaluating alternatives, or making recommendations. Output typically includes criteria, comparison table, pros/cons, and recommendation.
---

# Comparison Report

Guidelines for producing comparison reports between two or more options.

## Output Structure

1. **Criteria**: List the dimensions used for comparison (e.g. performance, ecosystem, learning curve).
2. **Comparison Table**: Side-by-side comparison. Rows = criteria, columns = options. Use inline [Source] for metrics when citing.
3. **Pros and Cons**: Per-option strengths and weaknesses.
4. **Recommendation**: Clear conclusion with rationale. Map to scenarios when appropriate.
5. **References**: **Required.** `## References` section listing all sources (artifact names, URLs, or "Official documentation" for general knowledge). Quantitative claims in the table must have attribution.

## Table Format

```markdown
| Criterion    | Option A | Option B | Option C |
|--------------|----------|----------|----------|
| Performance  | High     | Medium   | High     |
| Ecosystem    | Mature   | Growing | Mature   |
| Learning     | Moderate | Easy    | Steep    |
```

- Use consistent scale or labels (e.g. High/Medium/Low, or specific metrics).
- Add a brief "Notes" row if needed for context.
- When metrics are numeric, include units (e.g. "10ms", "50 req/s").

## Pros/Cons Format

**Option A**
- Pros: ...
- Cons: ...

**Option B**
- Pros: ...
- Cons: ...

- Aggregate pros/cons from input artifacts; avoid duplication.
- Prioritize by importance when many items.

## Recommendation

- State the recommended option clearly.
- Include "when to use" or "best for" scenarios.
- Support with evidence from the comparison.
- If no clear winner: present trade-offs and suggest "depends on X".

## Input Artifacts

- Use ReadArtifact to get research outputs for each option (e.g. task_1, task_2, task_3).
- Combine into unified comparison. Ensure criteria align across sources.
- If artifacts use different criteria, create a unified criteria set and fill from each source.

## Output Format

- **Markdown** for human-readable reports.
- **JSON** for structured output when spec requires:
  ```json
  {
    "options": [{"name": "A", "pros": [...], "cons": [...]}],
    "comparison": {"criterion": {"A": "value", "B": "value"}},
    "recommendation": {"option": "A", "rationale": "..."}
  }
  ```

## Quality Checklist

- [ ] All options from input artifacts included
- [ ] Criteria cover key dimensions
- [ ] Table is complete (no empty cells without reason)
- [ ] Recommendation supported by evidence
- [ ] **## References section** present; quantitative metrics in table have source attribution
