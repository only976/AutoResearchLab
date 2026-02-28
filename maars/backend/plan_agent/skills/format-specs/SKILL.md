---
name: format-specs
description: Guidelines for defining input/output specifications of atomic tasks. Use when formatting tasks (FormatTask) to ensure Task Agent and validator have clear, checkable criteria. Apply when CheckAtomicity returns atomic=true.
---

# Format Specifications

Guidelines for defining input/output/validation for atomic tasks. Apply when CheckAtomicity returns atomic=true.

## Input Spec

```json
{
  "description": "Human-readable description of what the task consumes",
  "artifacts": ["artifact_from_task_1", "artifact_from_task_2"],
  "parameters": ["optional_param_1"]
}
```

- **artifacts**: List artifact names or types from dependency tasks. Reference by task_id or semantic name (e.g. `task_1.output`, `search_config`).
- **parameters**: Optional explicit params (e.g. comparison_scope, target_audience). Omit if none.
- **description**: What the task needs to start. Be specific. For root-level tasks with no deps, use "Parent scope, idea, or plan context".

## Output Spec

```json
{
  "description": "What the task produces",
  "artifact": "output_artifact_name",
  "format": "JSON | Markdown | document | table"
}
```

- **artifact**: Name/type of produced artifact. Used by downstream tasks. Use consistent naming (e.g. `synthesis_report`, `comparison_table`).
- **format**: JSON (structured), Markdown (document), document (generic), table (tabular). For JSON, specify schema when known: `JSON: { key: type }`.
- **description**: Clear statement of deliverable.

## Validation Spec

```json
{
  "description": "What to validate",
  "criteria": [
    "Output must contain keys X, Y",
    "All sources must be cited",
    "Table has columns A, B, C"
  ],
  "optionalChecks": ["Optional: style consistency"]
}
```

- **criteria**: Concrete, checkable rules. Validator can verify without subjective judgment.
- **optionalChecks**: Nice-to-have; do not fail validation if missing.
- **Aligned**: Criteria must match output format (e.g. JSON schema for JSON; section names for Markdown).

## Format-Specific Examples

### JSON Output
```json
{
  "output": {
    "artifact": "search_config",
    "format": "JSON: { keywords: string[], databases: string[] }"
  },
  "validation": {
    "criteria": [
      "Output is valid JSON",
      "keywords is non-empty array",
      "databases lists at least one valid database"
    ]
  }
}
```

### Markdown Output

**Generic:**
```json
{
  "output": {
    "artifact": "synthesis_report",
    "format": "Markdown document"
  },
  "validation": {
    "criteria": [
      "Document has ## Summary section",
      "Document has ## Findings section"
    ]
  }
}
```

**Research/Comparison Report (add citation criteria):**
```json
{
  "output": {
    "artifact": "research_report",
    "format": "Markdown document"
  },
  "validation": {
    "criteria": [
      "Document has ## Summary section",
      "Document has ## References section",
      "References section is non-empty"
    ],
    "optionalChecks": ["Quantitative claims include inline source attribution"]
  }
}
```

### Table Output
```json
{
  "output": {
    "artifact": "comparison_table",
    "format": "Markdown table"
  },
  "validation": {
    "criteria": [
      "Output contains pipe-separated table",
      "Table has header row",
      "All comparison criteria from input are represented as rows"
    ]
  }
}
```

## Artifact Naming Conventions

| Task type | Suggested artifact name |
|-----------|-------------------------|
| Search config | `search_config` |
| Filtered list | `filtered_papers`, `filtered_results` |
| Synthesis report | `synthesis_report`, `literature_review` |
| Comparison | `comparison_report`, `comparison_table` |
| Experiment results | `experiment_results`, `benchmark_data` |
| Analysis | `analysis_report`, `findings` |

## Research Report Output (Citation Requirements)

When the task produces a **research report**, **comparison report**, or **synthesis document** (e.g. "调研报告", "对比报告", "综合分析"), add validation criteria for source attribution:

```json
"validation": {
  "criteria": [
    "Document has ## References section",
    "References section is non-empty"
  ],
  "optionalChecks": ["Quantitative claims include inline source attribution"]
}
```

This ensures reports include citations and a References section, improving credibility.

## Anti-Patterns

- Vague criteria: "output should be good" → use concrete checks
- Subjective criteria: "writing quality" → use structural or content rules
- Mismatched format: JSON output with "must have Introduction" → align with format
- Missing artifacts: Task has dependencies but artifacts list is empty → list what each dep produces
- Over-specifying: Too many optionalChecks → keep 1–3 optional; rest in criteria
