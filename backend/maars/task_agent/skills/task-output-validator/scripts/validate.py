#!/usr/bin/env python3
"""
Validate task output against criteria. Used by task-output-validator skill.
Run from skill dir: python scripts/validate.py <output_path> [--criteria-json '...']
Outputs JSON: {"passed": bool, "report": "markdown"}
"""

import argparse
import json
import re
import sys
from pathlib import Path


def _load_output(path: str) -> tuple[str | None, str]:
    """Load output file. Returns (content, error)."""
    p = Path(path)
    if not p.exists():
        return None, f"File not found: {path}"
    if not p.is_file():
        return None, f"Not a file: {path}"
    try:
        return p.read_text(encoding="utf-8", errors="replace"), ""
    except Exception as e:
        return None, str(e)


def _check_json(content: str, criteria: list[str]) -> tuple[bool, list[str]]:
    """Check JSON output. Returns (all_passed, report_lines)."""
    report = []
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        report.append(f"- Valid JSON: FAIL ({e})")
        return False, report

    report.append("- Valid JSON: PASS")
    all_passed = True

    for c in criteria:
        c_lower = c.lower()
        if "valid json" in c_lower or "is valid json" in c_lower:
            continue  # already checked
        if "non-empty array" in c_lower or "nonempty array" in c_lower:
            # e.g. "keywords is non-empty array"
            m = re.search(r"(\w+)\s+is\s+non-?empty\s+array", c_lower, re.I)
            if m:
                key = m.group(1)
                if isinstance(data, dict) and key in data:
                    val = data[key]
                    if isinstance(val, list) and len(val) > 0:
                        report.append(f"- {c}: PASS")
                    else:
                        report.append(f"- {c}: FAIL (not a non-empty array)")
                        all_passed = False
                else:
                    report.append(f"- {c}: FAIL (key '{key}' missing)")
                    all_passed = False
            else:
                report.append(f"- {c}: (manual check)")
        elif "key" in c_lower or "keys" in c_lower:
            # e.g. "Output must contain keys X, Y"
            m = re.findall(r"keys?\s+([A-Za-z0-9_,\s]+)", c, re.I)
            if m:
                keys = [k.strip() for k in re.split(r"[,&\s]+", m[0]) if k.strip()]
                if isinstance(data, dict):
                    missing = [k for k in keys if k not in data]
                    if not missing:
                        report.append(f"- {c}: PASS")
                    else:
                        report.append(f"- {c}: FAIL (missing: {missing})")
                        all_passed = False
                else:
                    report.append(f"- {c}: FAIL (output is not an object)")
                    all_passed = False
            else:
                report.append(f"- {c}: (manual check)")
        else:
            report.append(f"- {c}: (manual check)")

    return all_passed, report


def _check_markdown(content: str, criteria: list[str]) -> tuple[bool, list[str]]:
    """Check Markdown output. Returns (all_passed, report_lines)."""
    report = []
    all_passed = True

    for c in criteria:
        c_lower = c.lower()
        if "section" in c_lower or "has ##" in c_lower:
            # e.g. "Document has ## Summary section" or "References section is non-empty"
            section = None
            m = re.search(r"##\s*([^\s]+)", c)
            if m:
                section = m.group(1).strip()
            elif "references" in c_lower and ("non-empty" in c_lower or "nonempty" in c_lower):
                section = "References"
            if section:
                pattern = rf"^#{{1,6}}\s*{re.escape(section)}\s*$"
                if re.search(pattern, content, re.MULTILINE | re.IGNORECASE):
                    # Check "References section is non-empty" if that's the criterion
                    if "non-empty" in c_lower or "nonempty" in c_lower:
                        # Extract content after ## Section until next ## or end
                        ref_match = re.search(
                            rf"^#{{1,6}}\s*{re.escape(section)}\s*$(.*?)(?=^#{{1,6}}\s|\Z)",
                            content,
                            re.MULTILINE | re.DOTALL | re.IGNORECASE,
                        )
                        body = (ref_match.group(1) if ref_match else "").strip()
                        if body and len(body) > 10:
                            report.append(f"- {c}: PASS")
                        else:
                            report.append(f"- {c}: FAIL (section '## {section}' is empty or too short)")
                            all_passed = False
                    else:
                        report.append(f"- {c}: PASS")
                else:
                    report.append(f"- {c}: FAIL (section '## {section}' not found)")
                    all_passed = False
            else:
                report.append(f"- {c}: (manual check)")
        elif "table" in c_lower and ("pipe" in c_lower or "header" in c_lower):
            has_pipe = "|" in content
            has_header = bool(re.search(r"^\|.+\|", content, re.MULTILINE))
            if "pipe" in c_lower and has_pipe:
                report.append(f"- {c}: PASS")
            elif "header" in c_lower and has_header:
                report.append(f"- {c}: PASS")
            elif "pipe" in c_lower and not has_pipe:
                report.append(f"- {c}: FAIL (no pipe-separated table)")
                all_passed = False
            elif "header" in c_lower and not has_header:
                report.append(f"- {c}: FAIL (no header row)")
                all_passed = False
            else:
                report.append(f"- {c}: (manual check)")
        elif "contain" in c_lower or "contains" in c_lower:
            # Substring check
            m = re.search(r"contain[s]?\s+['\"]?([^'\"]+)['\"]?", c, re.I)
            if m:
                sub = m.group(1).strip()
                if sub in content:
                    report.append(f"- {c}: PASS")
                else:
                    report.append(f"- {c}: FAIL (substring not found)")
                    all_passed = False
            else:
                report.append(f"- {c}: (manual check)")
        else:
            report.append(f"- {c}: (manual check)")

    return all_passed, report


def _detect_format(content: str) -> str:
    """Guess output format: json or markdown."""
    stripped = content.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return "json"
    return "markdown"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate task output against criteria")
    parser.add_argument("output_path", help="Path to output file")
    parser.add_argument("--criteria-json", default="", help="JSON string of validation spec")
    args = parser.parse_args()

    content, err = _load_output(args.output_path)
    if err:
        out = {"passed": False, "report": f"# Validation\n\n**Error:** {err}"}
        print(json.dumps(out, ensure_ascii=False))
        return 1

    criteria = []
    optional_checks = []
    if args.criteria_json:
        try:
            spec = json.loads(args.criteria_json)
            criteria = spec.get("criteria") or []
            optional_checks = spec.get("optionalChecks") or []
        except json.JSONDecodeError as e:
            out = {"passed": False, "report": f"# Validation\n\n**Error:** Invalid criteria JSON: {e}"}
            print(json.dumps(out, ensure_ascii=False))
            return 1

    if not criteria and not optional_checks:
        fmt = _detect_format(content)
        if fmt == "json":
            try:
                json.loads(content)
                report = ["- Format validity: PASS (valid JSON)"]
            except json.JSONDecodeError as e:
                out = {"passed": False, "report": f"# Validation\n\n- Format validity: FAIL ({e})"}
                print(json.dumps(out, ensure_ascii=False))
                return 1
        else:
            report = ["- Format: PASS (content present)"]
        out = {"passed": True, "report": "# Validation\n\n" + "\n".join(report) + "\n\n**Result: PASS**"}
        print(json.dumps(out, ensure_ascii=False))
        return 0

    fmt = _detect_format(content)
    if fmt == "json":
        all_passed, report_lines = _check_json(content, criteria)
    else:
        all_passed, report_lines = _check_markdown(content, criteria)

    for c in optional_checks:
        report_lines.append(f"- [optional] {c}: (manual check)")

    report = "# Validation Report\n\n" + "\n".join(report_lines) + f"\n\n**Result: {'PASS' if all_passed else 'FAIL'}**"
    out = {"passed": all_passed, "report": report}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
