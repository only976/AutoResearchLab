---
name: data-analysis
description: Analyze structured data (JSON, tables, metrics) and produce insights. Use when task involves analyzing data, computing metrics, or deriving conclusions from structured input. Output can be report (Markdown) or structured (JSON). Covers aggregation, comparison, trends, and validation.
---

# Data Analysis

Guidelines for analyzing structured data and producing insights.

## Input Handling

- Use ReadArtifact to get dependency outputs (e.g. benchmark results, survey data, configs).
- Use ReadFile for `sandbox/*` or plan-level files.
- Parse JSON or tabular data. Identify structure (keys, arrays, nested objects).
- **Validate structure first**: Check for expected keys, types. Log structure if unclear.

## Analysis Types

| Type | Input | Output |
|------|-------|--------|
| Aggregate | List of items | Metrics (count, sum, avg, min, max), distribution |
| Compare | Multiple datasets | Side-by-side comparison, deltas |
| Trend | Time-series or ordered data | Patterns, trends, anomalies |
| Correlation | Multi-variate data | Relationships, dependencies |
| Summary | Large dataset | Key statistics, representative samples |
| Distribution | Categorical/numerical | Frequency table, percentiles |
| Ranking | Scored items | Ordered list, top-N, thresholds |

## Output Format

### Markdown Report
- **Methodology**: What was analyzed, data sources.
- **Results**: Key metrics, tables, findings.
- **Interpretation**: What the numbers mean.
- **Conclusions**: Takeaways, recommendations.

### JSON Output
```json
{
  "metrics": {"count": N, "avg": X, "min": Y, "max": Z},
  "findings": ["finding1", "finding2"],
  "recommendations": ["rec1", "rec2"]
}
```

- Match the output spec exactly when format is specified.
- Use consistent key names as defined in task output spec.

## Tables for Results

Use Markdown tables for numerical results:

```markdown
| Metric | Value A | Value B | Delta |
|--------|---------|---------|-------|
| Latency | 10ms | 15ms | +50% |
```

- Include units in header or first row when relevant.
- Use alignment row (`|---|`) for readability.

## Sandbox Usage

- Save intermediate parsed data to `sandbox/parsed.json`
- Save computed metrics to `sandbox/metrics.json`
- Final output via Finish (do not output inline for JSON/Markdown spec)

## Error Handling

- **Malformed input**: Document the issue, suggest correction. Proceed with partial data if possible.
- **Missing data**: Note gaps explicitly in report; state assumptions.
- **Empty input**: Return structured empty result with explanation, do not fail silently.
- **Type mismatch**: Coerce or skip; document in methodology.

## Edge Cases

- **Single-item list**: Still compute metrics; avoid division-by-zero.
- **Nested arrays**: Flatten or aggregate per level as appropriate.
- **Null/missing values**: Exclude from numeric aggregates; count separately if relevant.
