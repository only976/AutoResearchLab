---
name: markdown-reporter
description: Generate structured Markdown reports, summaries, and documentation. Use when task output format is Markdown, document, report, summary, or README. Covers structure, tables, code blocks, and common report types. Essential for FormatTask output spec format: Markdown.
---

# Markdown Reporter

Guidelines for producing high-quality Markdown output in research and documentation tasks.

## Output Structure

- **Headings**: Use `##` for main sections, `###` for subsections. Keep hierarchy clear (h2 > h3 > h4). Do not skip levels.
- **Lists**: Use `-` for unordered, `1.` for ordered. Nest appropriately.
- **Code**: Use fenced blocks with language when including code: ` ```python ` ... ` ``` `
- **Tables**: Use pipe `|` syntax. Align columns for readability.
- **Links**: `[text](url)` for references. Use `[Author, Year]` or `[Source Name](url)` for citations.
- **Citations**: For research reports, include inline citations for quantitative claims (e.g. RPS, benchmarks) and a `## References` section listing all sources.
- **Bold/Italic**: `**bold**` for emphasis, `*italic*` for terms.

## Common Report Types

| Type | Structure | Sections |
|------|-----------|----------|
| Summary | Executive summary, key findings, conclusions | Summary, Findings, Conclusions |
| Comparison | Side-by-side table, pros/cons, recommendation | Criteria, Comparison Table, Pros/Cons, Recommendation |
| Analysis | Methodology, data, findings, implications | Methodology, Data/Results, Findings, Implications |
| Literature synthesis | Themes, gaps, synthesis | Overview, Key Themes, Gaps, Synthesis |
| Documentation | Overview, usage, examples | Overview, Usage, Examples, API/Reference |
| Technical report | Problem, approach, results, discussion | Problem, Approach, Results, Discussion |

## Table Format

```markdown
| Column A | Column B | Column C |
|----------|----------|----------|
| value 1  | value 2  | value 3  |
```

- Header row with `|` separators
- Alignment row: `|---|` or `:---:|` for center
- Consistent column width for readability
- Escape `|` inside cells with `\|` if needed

## Validation Alignment

When the task's validation spec requires specific sections (e.g. "Document has ## Summary section"), ensure those sections exist with exact heading text. Use the same heading level as specified.

## References and Citations (Research Reports)

For research, comparison, or synthesis reports, **always include**:

1. **Inline citations**: When stating quantitative data (e.g. "15k RPS", "4.4x faster"), attribute the source: `[Source Name]` or `[Task N output]` when from artifacts.
2. **## References section**: At the end of the document, list all sources with format:
   - From artifacts: `[Task N] Task N description or artifact name`
   - From general knowledge: `[Official Docs] Framework name - official documentation` or `[Industry Benchmark] Brief description`
   - If URL available: `[Source Name](url) - brief description`

3. **Avoid unsourced claims**: Do not state specific numbers (RPS, benchmarks) without attribution. Use "industry standard" or cite the source.

## Quality Checklist

- [ ] Clear section hierarchy (no skipped levels)
- [ ] Concise but complete coverage
- [ ] Code blocks with syntax hint when relevant
- [ ] Tables for comparative or tabular data
- [ ] **References section** for research/comparison reports (## References)
- [ ] Inline citations for quantitative or factual claims
- [ ] No raw HTML unless necessary
- [ ] Validation criteria from task spec satisfied

## Sandbox Usage

- Save drafts to `sandbox/draft.md` if iterating
- Final output via Finish tool (pass Markdown string)

## References

- For templates, see [references/templates.md](references/templates.md)
