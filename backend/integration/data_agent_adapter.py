import base64
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from backend.agents.data_agent import docker_data_agent as dda


def _collect_data_files(workspace_path: str) -> List[str]:
    """Collect CSV/LOG files from experiment workspace for data-agent checks."""
    candidates: List[str] = []
    for root, _, files in os.walk(workspace_path):
        for name in files:
            lowered = name.lower()
            if lowered.endswith(".csv") or lowered.endswith(".log"):
                candidates.append(os.path.join(root, name))
    return sorted(candidates)


def _save_visuals(report: Dict[str, Any], workspace_path: str) -> Dict[str, Any]:
    """Persist inline base64 visuals to files and replace with file references."""
    visuals = report.get("visuals", [])
    if not isinstance(visuals, list) or not visuals:
        return report

    out_dir = os.path.join(workspace_path, "data_agent_visuals")
    os.makedirs(out_dir, exist_ok=True)

    saved_visuals: List[Dict[str, Any]] = []
    for idx, visual in enumerate(visuals):
        if not isinstance(visual, dict):
            continue

        visual_copy = dict(visual)
        payload = visual_copy.get("image_base64")
        file_name: Optional[str] = None
        if isinstance(payload, str) and payload:
            if payload.startswith("data:image/svg+xml;base64,"):
                data = base64.b64decode(payload.split(",", 1)[1])
                file_name = f"{idx:02d}_{visual_copy.get('id', 'visual')}.svg"
            elif payload.startswith("data:image/png;base64,"):
                data = base64.b64decode(payload.split(",", 1)[1])
                file_name = f"{idx:02d}_{visual_copy.get('id', 'visual')}.png"
            else:
                data = base64.b64decode(payload)
                file_name = f"{idx:02d}_{visual_copy.get('id', 'visual')}.bin"

            file_path = os.path.join(out_dir, file_name)
            with open(file_path, "wb") as handle:
                handle.write(data)

            visual_copy.pop("image_base64", None)
            visual_copy["image_file"] = os.path.relpath(file_path, workspace_path)

        saved_visuals.append(visual_copy)

    report["visuals"] = saved_visuals
    return report


def _build_quantitative_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    """Convert data-agent report into quantitative_summary style payload."""
    checks = report.get("checks", [])
    visuals = report.get("visuals", [])

    pass_count = 0
    warn_count = 0
    fail_count = 0
    failed_checks: List[str] = []
    observations: List[str] = []

    for check in checks:
        if not isinstance(check, dict):
            continue
        status = check.get("status")
        name = str(check.get("name", "unknown_check"))
        detail = str(check.get("details", "")).strip()
        if status == "pass":
            pass_count += 1
        elif status == "warn":
            warn_count += 1
            observations.append(f"[warn] {name}: {detail}" if detail else f"[warn] {name}")
        elif status == "fail":
            fail_count += 1
            failed_checks.append(str(check.get("id", name)))
            observations.append(f"[fail] {name}: {detail}" if detail else f"[fail] {name}")

    chart_files: List[str] = []
    for visual in visuals:
        if isinstance(visual, dict) and visual.get("image_file"):
            chart_files.append(str(visual["image_file"]))

    return {
        "metrics": {
            "data_agent_pass_checks": pass_count,
            "data_agent_warn_checks": warn_count,
            "data_agent_fail_checks": fail_count,
            "data_agent_series_count": report.get("metadata", {}).get("parsed_series_count", 0),
            "data_agent_llm_used": bool(report.get("metadata", {}).get("llm_identification_used", False)),
            "data_agent_failed_checks": failed_checks,
        },
        "observations": observations,
        "generated_charts": chart_files,
    }


def run_data_agent_analysis(
    workspace_path: str,
    use_llm: bool = True,
    report_name: str = "data_agent_report.json",
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Run data-agent parsing/check/visualization on workspace data files.

    Returns:
        (report, quantitative_summary_like_payload)
        Returns (None, None) when no data files were found.
    """
    input_files = _collect_data_files(workspace_path)
    if not input_files:
        return None, None

    parsed = dda.parse_input_files(input_files, use_llm=use_llm)
    checks = dda.run_checks(parsed)
    visuals = dda.generate_visuals(parsed)
    report = dda.build_report(",".join(input_files), parsed, checks, visuals)
    report = _save_visuals(report, workspace_path)

    report_path = os.path.join(workspace_path, report_name)
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)

    summary = _build_quantitative_summary(report)
    return report, summary
