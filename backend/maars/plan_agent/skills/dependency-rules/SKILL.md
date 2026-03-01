---
name: dependency-rules
description: Rules for task dependencies in decomposition. Use when defining dependencies in Decompose/AddTasks to ensure acyclic, sibling-only, correct execution order. Critical for valid plan structure.
---

# Dependency Rules

Rules for the `dependencies` field when decomposing tasks. Dependencies define execution order among siblings.

## Core Rules

1. **Siblings only**: Dependencies reference only tasks at the same level (same parent). Parent-child relationship is expressed by task_id hierarchy (e.g. `1_1` is child of `1`).

2. **No parent in dependencies**: Do NOT include the parent task_id. A child does not "depend on" its parent—it is a child of it.

3. **Earlier siblings only**: A task can depend only on siblings that appear earlier in the list. This ensures valid topological order.

4. **Acyclic**: The dependency graph among siblings must be acyclic. No circular dependencies.

## Parallel vs Sequential

| Pattern | dependencies | Use when |
|---------|---------------|----------|
| **Parallel** | `[]` | Tasks can run independently (e.g. Research A, Research B) |
| **Sequential** | `["1_1"]` | Task needs prior sibling's output (e.g. Analyze needs Gather) |
| **Fan-in** | `["1", "2"]` | Task combines multiple prior outputs (e.g. Compare needs both A and B) |

## Task ID Hierarchy

- `0` = root (idea)
- `1`, `2`, `3` = top-level phases (children of 0)
- `1_1`, `1_2`, `1_3` = children of task 1
- `1_1_1`, `1_1_2` = children of task 1_1

## Valid Examples

**Parallel research + synthesis:**
```json
{
  "tasks": [
    {"task_id": "1", "description": "Research A", "dependencies": []},
    {"task_id": "2", "description": "Research B", "dependencies": []},
    {"task_id": "3", "description": "Compare and report", "dependencies": ["1", "2"]}
  ]
}
```

**Sequential pipeline:**
```json
{
  "tasks": [
    {"task_id": "1_1", "description": "Define scope", "dependencies": []},
    {"task_id": "1_2", "description": "Gather data", "dependencies": ["1_1"]},
    {"task_id": "1_3", "description": "Analyze", "dependencies": ["1_2"]}
  ]
}
```

**Mixed (parallel + fan-in):**
```json
{
  "tasks": [
    {"task_id": "1", "description": "Search DB1", "dependencies": []},
    {"task_id": "2", "description": "Search DB2", "dependencies": []},
    {"task_id": "3", "description": "Merge and filter results", "dependencies": ["1", "2"]},
    {"task_id": "4", "description": "Synthesize report", "dependencies": ["3"]}
  ]
}
```

## Invalid Examples

- `"dependencies": ["0"]` — Do not depend on parent
- `"dependencies": ["2"]` when current task is "1" and "2" not yet listed — Depend only on earlier siblings
- `"dependencies": ["1_2"]` when task is "1" — Cross-level: 1 and 1_2 are not siblings
- Circular: A depends on B, B depends on A — Not allowed
- `"dependencies": ["3"]` when task is "2" — Cannot depend on later sibling

## Validation Checklist

Before returning tasks, verify:
- [ ] No parent_id in any dependencies
- [ ] All dependency IDs are earlier siblings in the same list
- [ ] No circular dependencies
- [ ] Each dependency ID exists in the tasks array

## Execution Order

Tasks with empty dependencies run first. Tasks with dependencies run after all their dependencies complete. The Runner resolves full dependency graph (including inherited dependencies from ancestors) at execution time.
