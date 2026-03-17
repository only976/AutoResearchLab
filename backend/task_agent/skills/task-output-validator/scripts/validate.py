#!/usr/bin/env python3
"""
Validate task output against criteria. Used by task-output-validator skill.
Run from skill dir: python scripts/validate.py <output_path> [--criteria-json '...']
Outputs JSON: {"passed": bool, "report": "markdown"}
"""

import argparse
import csv
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


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


def _looks_like_equivalence_criterion(text: str) -> bool:
    t = (text or "").lower()
    return (
        "equivalent" in t
        or "equivalence" in t
        or "convertible" in t
        or "lossless" in t
        or "可等价" in t
        or "可转换" in t
    )


def _criterion_mentions_matrix_csv(text: str) -> bool:
    t = (text or "").lower()
    return ("matrix" in t and "csv" in t) or ("矩阵" in t and "csv" in t)


def _criterion_mentions_json_xml(text: str) -> bool:
    t = (text or "").lower()
    return ("json" in t and "xml" in t)


def _criterion_mentions_textual(text: str) -> bool:
    t = (text or "").lower()
    return "text" in t or "markdown" in t or "line" in t or "文本" in t


def _parse_tolerance(criteria: list[str], default_tol: float) -> float:
    joined = "\n".join(criteria or [])
    match = re.search(r"(1e-\d+|0\.\d+)", joined, re.I)
    if not match:
        return default_tol
    try:
        return float(match.group(1))
    except ValueError:
        return default_tol


def _matrix_from_csv(path: Path) -> list[list[float]]:
    rows: list[list[float]] = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            rows.append([float(cell.strip()) for cell in row])
    return rows


def _matrix_from_json_obj(obj: object) -> list[list[float]]:
    if isinstance(obj, list) and obj and all(isinstance(r, list) for r in obj):
        return [[float(cell) for cell in row] for row in obj]
    if isinstance(obj, dict):
        for key in ("matrix", "data", "values", "array"):
            val = obj.get(key)
            if isinstance(val, list) and val and all(isinstance(r, list) for r in val):
                return [[float(cell) for cell in row] for row in val]
    raise ValueError("JSON does not contain a numeric matrix")


def _load_numeric_matrix(path: str) -> list[list[float]]:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".csv":
        return _matrix_from_csv(p)
    if suffix in (".json", ".jsn"):
        obj = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        return _matrix_from_json_obj(obj)
    # best effort: try CSV then JSON
    try:
        return _matrix_from_csv(p)
    except Exception:
        obj = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        return _matrix_from_json_obj(obj)


def _compare_matrices(a: list[list[float]], b: list[list[float]], tol: float) -> tuple[bool, str]:
    if len(a) != len(b):
        return False, f"row count mismatch: {len(a)} vs {len(b)}"
    if a and b and len(a[0]) != len(b[0]):
        return False, f"column count mismatch: {len(a[0])} vs {len(b[0])}"
    max_abs = 0.0
    for i, row in enumerate(a):
        if len(row) != len(b[i]):
            return False, f"ragged row mismatch at row {i}: {len(row)} vs {len(b[i])}"
        for j, val in enumerate(row):
            diff = abs(val - b[i][j])
            if diff > max_abs:
                max_abs = diff
    if max_abs <= tol:
        return True, f"max absolute diff {max_abs:.6g} <= tolerance {tol:.6g}"
    return False, f"max absolute diff {max_abs:.6g} > tolerance {tol:.6g}"


def _xml_to_obj(elem: ET.Element) -> object:
    children = list(elem)
    if not children:
        text = (elem.text or "").strip()
        if text == "":
            return ""
        if text.lower() in ("true", "false"):
            return text.lower() == "true"
        try:
            if "." in text:
                return float(text)
            return int(text)
        except ValueError:
            return text

    grouped: dict[str, list[object]] = {}
    for child in children:
        grouped.setdefault(child.tag, []).append(_xml_to_obj(child))
    out: dict[str, object] = {}
    for key, vals in grouped.items():
        out[key] = vals[0] if len(vals) == 1 else vals
    return out


def _load_structured(path: str) -> object:
    p = Path(path)
    suffix = p.suffix.lower()
    raw = p.read_text(encoding="utf-8", errors="replace")
    if suffix in (".json", ".jsn"):
        return json.loads(raw)
    if suffix == ".xml":
        root = ET.fromstring(raw)
        return {root.tag: _xml_to_obj(root)}

    stripped = raw.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return json.loads(stripped)
    root = ET.fromstring(raw)
    return {root.tag: _xml_to_obj(root)}


def _load_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


def _normalize_text(content: str) -> str:
    # Normalize whitespace and common quoting noise for format-conversion checks.
    text = (content or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n+", "\n", text)
    return text.strip()


def _compare_text_normalized(left: str, right: str) -> tuple[bool, str]:
    l = _normalize_text(left)
    r = _normalize_text(right)
    if l == r:
        return True, "normalized texts match"
    return False, "normalized texts differ"


def _compare_line_set(left: str, right: str) -> tuple[bool, str]:
    lset = {line.strip() for line in _normalize_text(left).split("\n") if line.strip()}
    rset = {line.strip() for line in _normalize_text(right).split("\n") if line.strip()}
    if lset == rset:
        return True, f"line sets match ({len(lset)} unique lines)"
    missing = sorted(list(rset - lset))[:5]
    extra = sorted(list(lset - rset))[:5]
    return False, f"line sets differ; missing={missing} extra={extra}"


def _auto_compare(left_path: str, right_path: str, tol: float) -> tuple[bool, str]:
    # Try structured data first.
    try:
        if _load_structured(left_path) == _load_structured(right_path):
            return True, "auto compare: canonical structured objects match"
    except Exception:
        pass

    # Then try numeric matrix equivalence.
    try:
        ok, detail = _compare_matrices(_load_numeric_matrix(left_path), _load_numeric_matrix(right_path), tol)
        if ok:
            return True, f"auto compare: {detail}"
    except Exception:
        pass

    # Finally fallback to normalized text equivalence.
    try:
        return _compare_text_normalized(_load_text(left_path), _load_text(right_path))
    except Exception as e:
        return False, f"auto compare failed: {e}"


def _resolve_equivalence_paths(output_path: str, left: str, right: str) -> tuple[str, str]:
    l = output_path if (left or "").strip() in ("", "[[output]]") else left
    r = output_path if (right or "").strip() in ("", "[[output]]") else right
    return l, r


def _infer_mode_from_criterion(text: str) -> str:
    if _criterion_mentions_matrix_csv(text):
        return "numeric_matrix"
    if _criterion_mentions_json_xml(text):
        return "structured"
    if _criterion_mentions_textual(text):
        return "text_normalized"
    return "auto"


def _run_single_equivalence_check(
    *,
    output_path: str,
    check: dict[str, Any],
    default_reference: str,
    default_tol: float,
) -> tuple[bool, str]:
    mode = str(check.get("mode") or "auto").strip().lower()
    tol = float(check.get("tolerance") if check.get("tolerance") is not None else default_tol)
    left_raw = str(check.get("left") or "[[output]]")
    right_raw = str(check.get("right") or default_reference)
    left_path, right_path = _resolve_equivalence_paths(output_path, left_raw, right_raw)

    if not right_path:
        return False, "equivalence reference path is missing"

    if mode == "numeric_matrix":
        return _compare_matrices(_load_numeric_matrix(left_path), _load_numeric_matrix(right_path), tol)
    if mode == "structured":
        if _load_structured(left_path) == _load_structured(right_path):
            return True, "canonical structured objects match"
        return False, "canonical structured objects differ"
    if mode == "text_normalized":
        return _compare_text_normalized(_load_text(left_path), _load_text(right_path))
    if mode == "line_set":
        return _compare_line_set(_load_text(left_path), _load_text(right_path))
    if mode == "auto":
        return _auto_compare(left_path, right_path, tol)
    return False, f"unsupported equivalence mode: {mode}"


def _check_equivalence(
    *,
    output_path: str,
    equivalent_to: str,
    criteria: list[str],
    default_tol: float,
    config: dict[str, Any] | None = None,
) -> tuple[bool, list[str]]:
    report: list[str] = []
    selected = [c for c in (criteria or []) if _looks_like_equivalence_criterion(c)]
    if not selected:
        return True, report

    all_passed = True
    tol = _parse_tolerance(selected, default_tol)

    configured_checks = []
    if isinstance(config, dict):
        checks = config.get("checks")
        if isinstance(checks, list):
            configured_checks = [c for c in checks if isinstance(c, dict)]

    for c in selected:
        try:
            if configured_checks:
                criterion_ok = True
                for idx, check in enumerate(configured_checks, start=1):
                    ok, detail = _run_single_equivalence_check(
                        output_path=output_path,
                        check=check,
                        default_reference=equivalent_to,
                        default_tol=tol,
                    )
                    if ok:
                        report.append(f"- {c}: PASS (check#{idx}: {detail})")
                    else:
                        report.append(f"- {c}: FAIL (check#{idx}: {detail})")
                        criterion_ok = False
                if not criterion_ok:
                    all_passed = False
                continue

            mode = _infer_mode_from_criterion(c)
            ok, detail = _run_single_equivalence_check(
                output_path=output_path,
                check={"mode": mode, "left": "[[output]]", "right": equivalent_to, "tolerance": tol},
                default_reference=equivalent_to,
                default_tol=tol,
            )
            if ok:
                report.append(f"- {c}: PASS ({detail})")
            else:
                report.append(f"- {c}: FAIL ({detail})")
                all_passed = False
        except Exception as e:
            report.append(f"- {c}: FAIL ({e})")
            all_passed = False

    return all_passed, report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate task output against criteria")
    parser.add_argument("output_path", help="Path to output file")
    parser.add_argument("--criteria-json", default="", help="JSON string of validation spec")
    parser.add_argument("--equivalent-to", default="", help="Path to reference artifact for equivalence checks")
    parser.add_argument("--equivalence-tol", type=float, default=1e-6, help="Default tolerance for numeric equivalence checks")
    parser.add_argument("--equivalence-config-json", default="", help="JSON config for custom equivalence checks")
    args = parser.parse_args()

    content, err = _load_output(args.output_path)
    if err:
        out = {"passed": False, "report": f"# Validation\n\n**Error:** {err}"}
        print(json.dumps(out, ensure_ascii=False))
        return 1

    criteria = []
    optional_checks = []
    equivalence_config = None
    if args.criteria_json:
        try:
            spec = json.loads(args.criteria_json)
            criteria = spec.get("criteria") or []
            optional_checks = spec.get("optionalChecks") or []
        except json.JSONDecodeError as e:
            out = {"passed": False, "report": f"# Validation\n\n**Error:** Invalid criteria JSON: {e}"}
            print(json.dumps(out, ensure_ascii=False))
            return 1

    if args.equivalence_config_json:
        try:
            equivalence_config = json.loads(args.equivalence_config_json)
        except json.JSONDecodeError as e:
            out = {"passed": False, "report": f"# Validation\n\n**Error:** Invalid equivalence config JSON: {e}"}
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

    equivalence_criteria = [c for c in criteria if _looks_like_equivalence_criterion(c)]
    if equivalence_criteria:
        if not args.equivalent_to:
            all_passed = False
            report_lines.append("- Equivalence verification prerequisites: FAIL (--equivalent-to is required when equivalence criteria are present)")
        else:
            eq_passed, eq_report = _check_equivalence(
                output_path=args.output_path,
                equivalent_to=args.equivalent_to,
                criteria=criteria,
                default_tol=args.equivalence_tol,
                config=equivalence_config,
            )
            all_passed = all_passed and eq_passed
            report_lines.extend(eq_report)

    for c in optional_checks:
        report_lines.append(f"- [optional] {c}: (manual check)")

    report = "# Validation Report\n\n" + "\n".join(report_lines) + f"\n\n**Result: {'PASS' if all_passed else 'FAIL'}**"
    out = {"passed": all_passed, "report": report}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
