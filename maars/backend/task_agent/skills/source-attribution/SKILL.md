---
name: source-attribution
description: Ensure research reports, comparison reports, and synthesis documents include proper citations and a References section. Use when task output is a Markdown report with quantitative claims, benchmarks, or findings that require source attribution for credibility. Load alongside markdown-reporter or web-research for citation-heavy tasks.
---

# Source Attribution

Guidelines for adding citations and references to research-style reports. **Credibility depends on source attribution**—readers need to verify claims.

## When to Apply

- Task output is a **research report**, **comparison report**, or **synthesis document**
- Report contains **quantitative data** (RPS, benchmarks, metrics, percentages)
- Report makes **factual claims** about technologies, frameworks, or tools
- Validation criteria include "References section" or "source attribution"

## Citation Rules

### 1. Inline Attribution

- **Quantitative claims**: Always cite. e.g. "FastAPI achieves 15k–30k RPS [Official Docs]" or "PyPy is up to 4.4x faster [Task 2_1]"
- **From artifacts**: Use `[Task N]` (e.g. `[Task 2_1]`, `[Task 3_2]`)
- **General knowledge**: Use `[Official Docs]`, `[Industry Benchmark]`, or `[Framework Name - documentation]`

### 2. References Section (Required)

At the end of the document, add:

```markdown
## References

- [Task 2_1] Python runtime research report - CPython, PyPy comparison
- [Task 3_2] Backend framework comparison - Express, NestJS, Fastify
- [Official Docs] FastAPI - https://fastapi.tiangolo.com
- [Industry Benchmark] TechEmpower benchmarks - web framework performance
```

- **From artifacts**: `[Task N] artifact name - brief description`
- **With URL** (from WebSearch/WebFetch): `[Source Name](url) - description`. Prefer real URLs when available.
- **General knowledge**: `[Official Docs] Framework - documentation` or `[Industry] benchmark description`

### 3. Never Do

- State specific numbers (RPS, benchmarks, percentages) without attribution
- Omit the ## References section for research/comparison reports
- Use vague "industry standard" for precise metrics—either cite or qualify ("typically", "commonly")

## Workflow

1. **While writing**: Add `[Source]` inline when stating facts or numbers
2. **Before Finish**: Ensure ## References section exists and lists all cited sources
3. **Validate**: Run task-output-validator; "References section is non-empty" must pass

## Quality Checklist

- [ ] Every quantitative claim has inline [Source]
- [ ] ## References section present
- [ ] References section lists all sources (no orphan citations)
- [ ] Format consistent (Task N, URL, or general source)
