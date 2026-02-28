---
name: task-output-validator
description: Validate task output against criteria before calling Finish. Use when the task has a validation spec (criteria, optionalChecks). Load this skill, write output to sandbox, run validate script, fix issues if validation fails, then call Finish.
---

# Task Output Validator

Validate task output against the task's validation criteria **before** calling Finish. Ensures output meets all required criteria so the task passes validation.

## When to Use

- The task has a `validation` spec with `criteria` or `optionalChecks`
- You have produced output and are about to call Finish
- You want to catch format/structure errors before submission

## Workflow

1. **Write output to sandbox**  
   Save your output to a file in the task sandbox, e.g. `sandbox/output.json` or `sandbox/result.md`.

2. **Load this skill**  
   `LoadSkill("task-output-validator")`

3. **Run validation**  
   `RunSkillScript(skill="task-output-validator", script="scripts/validate.py", args=["{{sandbox}}/output.json", "--criteria-json", "<JSON string of validation spec>"])`

4. **Interpret result**  
   - If `passed: true` → call `Finish` with the output
   - If `passed: false` → read the report, fix the issues, re-run validation, then `Finish`

## Validation Spec Format

Pass the task's validation spec as JSON. Example:

```json
{
  "criteria": [
    "Output is valid JSON",
    "keywords is non-empty array",
    "Document has ## Summary section"
  ],
  "optionalChecks": ["Optional: style consistency"]
}
```

## Script Usage

```
python scripts/validate.py <output_file_path> [--criteria-json '{"criteria":[...],"optionalChecks":[...]}']
```

- `output_file_path`: Full path to the output file (use `{{sandbox}}/output.json` in RunSkillScript args)
- `--criteria-json`: JSON string of validation spec. If omitted, only format validity is checked.

## Output Format

The script prints JSON to stdout:

```json
{
  "passed": true,
  "report": "# Validation Report\n\n- Criterion 1: PASS\n- Criterion 2: PASS\n\n**Result: PASS**"
}
```

## Criteria Support

The script performs structural checks:

- **JSON**: Valid JSON, required keys present, non-empty arrays/objects where specified
- **Markdown**: Section headers (e.g. `## Summary`), table structure, pipe syntax
- **References section**: `Document has ## References section` and `References section is non-empty` (for research reports)
- **Generic**: Substring/keyword presence

For semantic criteria (e.g. "content is complete"), verify manually before Finish. The script reports automatable checks; you judge the rest.

## Example

Task has validation: `{"criteria": ["Output is valid JSON", "keywords is non-empty array"]}`

1. Write output to `sandbox/search_config.json`
2. `RunSkillScript("task-output-validator", "scripts/validate.py", ["{{sandbox}}/search_config.json", "--criteria-json", "{\"criteria\":[\"Output is valid JSON\",\"keywords is non-empty array\"]}"])`
3. If passed → `Finish(output)`
