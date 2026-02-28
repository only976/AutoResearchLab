#!/usr/bin/env python3

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path


RE_REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9_.-]+)")


@dataclass(frozen=True)
class AuditResult:
    required_distributions: set[str]
    unknown_modules: set[str]
    scanned_modules: set[str]


def _normalize_dist_name(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def _is_stdlib_module(mod: str, stdlib: set[str]) -> bool:
    return mod in stdlib


def _iter_py_files(base: Path) -> list[Path]:
    return [
        p
        for p in base.rglob("*.py")
        if "__pycache__" not in p.parts and "/.venv/" not in str(p)
    ]


def _top_module(name: str) -> str:
    return name.split(".", 1)[0]


def collect_third_party_modules(scan_dirs: list[Path], repo_root: Path) -> set[str]:
    stdlib = set(getattr(sys, "stdlib_module_names", ()))
    stdlib |= set(sys.builtin_module_names)

    local_toplevel: set[str] = set()
    for p in [repo_root / "backend", repo_root / "maars", repo_root / "frontend"]:
        if p.exists() and p.is_dir():
            local_toplevel.add(p.name)
    for child in repo_root.iterdir():
        if child.is_dir() and (child / "__init__.py").exists():
            local_toplevel.add(child.name)
    # Also treat top-level packages within scan dirs as local. MAARS backend uses
    # absolute imports like `from api import ...` which are local to maars/backend.
    for scan_dir in scan_dirs:
        if not scan_dir.exists() or not scan_dir.is_dir():
            continue
        for child in scan_dir.iterdir():
            if child.is_dir() and (child / "__init__.py").exists():
                local_toplevel.add(child.name)

    ident = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    imported: set[str] = set()
    for base in scan_dirs:
        if not base.exists():
            continue
        for file in _iter_py_files(base):
            try:
                src = file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                src = file.read_text(encoding="latin-1")
            try:
                tree = ast.parse(src, filename=str(file))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        mod = _top_module(alias.name)
                        if ident.match(mod):
                            imported.add(mod)
                elif isinstance(node, ast.ImportFrom):
                    if node.level and node.level > 0:
                        continue
                    if node.module:
                        mod = _top_module(node.module)
                        if ident.match(mod):
                            imported.add(mod)

    third_party = {
        mod
        for mod in imported
        if not _is_stdlib_module(mod, stdlib) and mod not in local_toplevel
    }
    return third_party


def infer_required_distributions(modules: set[str]) -> AuditResult:
    try:
        from importlib.metadata import packages_distributions

        mod_to_dists = packages_distributions()
    except Exception:
        mod_to_dists = {}

    manual_module_to_dist = {
        # Common mismatches
        "yaml": "PyYAML",
        "dotenv": "python-dotenv",
        "json_repair": "json-repair",
        "fitz": "PyMuPDF",
        "PIL": "Pillow",
        "bs4": "beautifulsoup4",
        "sklearn": "scikit-learn",
        "duckduckgo_search": "duckduckgo-search",
        "qdrant_client": "qdrant-client",
    }

    required: set[str] = set()
    unknown: set[str] = set()
    for mod in sorted(modules):
        dist_list = mod_to_dists.get(mod)
        if dist_list:
            required.add(_normalize_dist_name(dist_list[0]))
            continue
        if mod in manual_module_to_dist:
            required.add(_normalize_dist_name(manual_module_to_dist[mod]))
            continue
        # Fallback heuristic: for most ecosystems, top-level import name matches
        # the distribution name closely (fastapi, uvicorn, pydantic, aiofiles, etc).
        # We still report it as unknown so it can be reviewed.
        unknown.add(mod)
        required.add(_normalize_dist_name(mod))

    return AuditResult(required_distributions=required, unknown_modules=unknown, scanned_modules=modules)


def parse_requirements(requirements_path: Path) -> list[str]:
    reqs: list[str] = []
    for raw in requirements_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Drop inline comments.
        if " #" in line:
            line = line.split(" #", 1)[0].strip()
        reqs.append(line)
    return reqs


def requirement_name(req_line: str) -> str:
    # Handles: pkg, pkg==1.2, pkg>=1, pkg[extra], pkg @ url
    base = req_line.split("@", 1)[0].strip()
    base = base.split("[", 1)[0].strip()
    m = RE_REQUIREMENT_NAME.match(base)
    if not m:
        return _normalize_dist_name(req_line)
    return _normalize_dist_name(m.group(1))


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit requirements.txt against code imports")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repo root (default: parent of scripts/)",
    )
    parser.add_argument(
        "--scan",
        type=Path,
        action="append",
        default=[Path("backend"), Path("maars/backend")],
        help="Relative paths under repo-root to scan (repeatable)",
    )
    parser.add_argument(
        "--requirements",
        type=Path,
        default=Path("requirements.txt"),
        help="Requirements file path (relative to repo-root unless absolute)",
    )
    args = parser.parse_args()

    repo_root: Path = args.repo_root
    scan_dirs = [repo_root / p for p in args.scan]
    req_path = args.requirements
    if not req_path.is_absolute():
        req_path = repo_root / req_path

    modules = collect_third_party_modules(scan_dirs, repo_root)
    audit = infer_required_distributions(modules)

    req_lines = parse_requirements(req_path)
    req_names = {_normalize_dist_name(requirement_name(r)) for r in req_lines}

    missing = sorted(audit.required_distributions - req_names)
    extra = sorted(req_names - audit.required_distributions)

    print("SCAN_DIRS")
    for d in scan_dirs:
        print(f"  {d}")

    print("\nREQUIRED_DISTS")
    for d in sorted(audit.required_distributions):
        print(f"  {d}")

    print("\nMISSING_IN_REQUIREMENTS")
    for d in missing:
        print(f"  {d}")

    print("\nEXTRA_IN_REQUIREMENTS")
    for d in extra:
        print(f"  {d}")

    print("\nUNKNOWN_MODULES")
    for m in sorted(audit.unknown_modules):
        print(f"  {m}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
