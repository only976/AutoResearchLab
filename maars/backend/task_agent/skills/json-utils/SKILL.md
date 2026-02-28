---
name: json-utils
description: Validate, format, and structure JSON output. Use when task output format is JSON, or when producing structured data (lists, configs, API responses). Ensures valid JSON and correct schema. Essential for FormatTask output spec format: JSON.
---

# JSON Utils

Guidelines for producing valid, well-structured JSON output.

## Output Rules

- **Valid JSON only**: No trailing commas, no comments, no single quotes. Use double quotes for strings.
- **Proper escaping**: In strings, escape `"` as `\"`, `\` as `\\`, newlines as `\n`.
- **Structure**: Match the output spec exactly (keys, types, nesting).
- **Arrays**: Use `[]` for lists. Ensure consistent element types (all objects, or all strings, etc.).
- **Objects**: Use `{}` for key-value structures. Keys must be strings.
- **Null**: Use `null` for missing/empty values, not `undefined` or empty string when null is intended.
- **Finish tool**: Pass a JSON string to Finish—no extra text, no markdown fences. Validator expects raw JSON.

## Common Patterns

| Use Case | Structure | Example |
|----------|-----------|---------|
| List of items | `{"items": [...], "count": N}` | Search results, task list |
| Key-value config | `{"key": "value", ...}` | Configuration object |
| Nested data | `{"parent": {"child": value}}` | Hierarchical data |
| API response | `{"data": ..., "meta": {...}}` | Paginated or wrapped response |
| Comparison result | `{"options": [...], "recommendation": "..."}` | A/B comparison |
| Key-value pairs | `{"key1": "val1", "key2": "val2"}` | Simple mapping |
| Search config | `{"keywords": [...], "databases": [...]}` | Literature search scope |

## Schema Alignment

- Read the task's output spec. If it specifies `format: "JSON: { keywords: string[], databases: string[] }"`, produce exactly that structure.
- Include all required keys. Omit optional keys only if not applicable.
- Use correct types: string, number, boolean, null, array, object.
- Key names must match exactly (case-sensitive).

## Validation Checklist

- [ ] Valid JSON (parseable by `JSON.parse`)
- [ ] All required keys present
- [ ] Correct types (no string where number expected)
- [ ] Arrays homogeneous (same structure per element)
- [ ] No trailing commas
- [ ] Special characters in strings properly escaped
- [ ] No BOM or leading/trailing whitespace when passing to Finish

## Edge Cases

- **Empty arrays**: Use `[]`, not `null` when the spec says "array".
- **Optional fields**: Omit entirely or use `null` per spec; be consistent.
- **Large output**: Consider saving to `sandbox/result.json` and passing path or summary if Finish has size limits.
- **Unicode**: JSON supports UTF-8; ensure proper encoding.

## Sandbox Usage

- Save intermediate JSON to `sandbox/data.json` for debugging
- Final output via Finish (pass JSON string only—no markdown wrapper)
