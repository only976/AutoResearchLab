---
name: web-research
description: Conduct web research, gather information from multiple sources, and synthesize findings. Use when task involves searching, comparing sources, or aggregating information. Covers process, synthesis techniques, and output structure. Note: MAARS Task Agent uses provided artifacts and general knowledge—no live web search.
---

# Web Research

Guidelines for research tasks that involve gathering and synthesizing information from multiple sources.

## MAARS Context

**Live web search available**: Use **WebSearch** to find current information, benchmarks, and documentation. Use **WebFetch** to retrieve full page content from URLs for citations. Combine with ReadArtifact for dependency outputs. When citing, include the URL from WebSearch/WebFetch results in your References section.

## Research Process

1. **Define scope**: Clarify what information is needed, from which domains, and what format the output should take.
2. **Gather sources**: Use **WebSearch** for external data (benchmarks, docs, comparisons); **WebFetch** for full page content from URLs; ReadArtifact for dependency outputs; ReadFile for local files. Extract key points from each.
3. **Synthesize**: Combine findings. Note agreements, conflicts, and gaps. Use tables for side-by-side comparison.
4. **Cite**: When referencing sources from input artifacts, include clear attribution. **Required formats**:
   - Inline: `[Task N]` or `[Source Name]` for artifact-derived claims
   - Quantitative claims (RPS, benchmarks, metrics): **must** have attribution—never state numbers without a source
   - End of report: `## References` section listing all sources (artifact names, URLs if available, or "Official documentation" for general knowledge)

## Synthesis Techniques

- **Thematic synthesis**: Group findings by theme or topic. Preferred when many sources.
- **Comparative synthesis**: Side-by-side table when comparing options (technologies, approaches).
- **Chronological**: When timeline or evolution matters.
- **Gap analysis**: What is known vs unknown; recommend next steps.
- **Pro-con synthesis**: Aggregate pros/cons across sources when comparing alternatives.

## Output Structure

| Section | Purpose |
|---------|---------|
| Findings | Organized by topic or source. Use subsections. Use inline [Source] for attribution. |
| Summary | Key takeaways in bullet or paragraph form. |
| Gaps | What could not be determined; limitations. |
| Recommendations | Next steps, conclusions, or suggested actions. |
| **References** | **Required.** List all sources: [Task N] artifact, [Official Docs] framework name, or [URL](link) when available. |

## Handling Conflicting Sources

When sources disagree:
- Present both views with attribution.
- Note the conflict explicitly.
- If possible, suggest resolution (e.g. "more recent", "broader sample").
- Do not arbitrarily pick one; let the reader see the conflict.

## Sandbox Usage

- Save intermediate notes to `sandbox/notes.md`
- Store raw or structured data to `sandbox/data.json` if needed
- Draft sections in `sandbox/draft.md` before finalizing
- Final output via Finish tool

## Quality Checklist

- [ ] Findings organized logically
- [ ] **All sources attributed**—inline [Source] for claims; no unsourced quantitative data
- [ ] **## References section** present and non-empty
- [ ] Summary captures main points
- [ ] Gaps/limitations acknowledged when relevant
- [ ] Recommendations actionable when appropriate
- [ ] Conflicts between sources noted when present
