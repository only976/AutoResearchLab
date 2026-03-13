"""Task title helpers.

Provide a compact, human-friendly title for task nodes while keeping full
description/objective in detail views.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable


_SPACE_RE = re.compile(r"\s+")
_LEADING_MARK_RE = re.compile(r"^[\-\*\d\.)\s]+")
_SPLIT_RE = re.compile(r"[\n\.;:!?]+")
_ZH_RE = re.compile(r"[\u4e00-\u9fff]")


def derive_task_title(description: str, *, max_len: int = 48) -> str:
    """Derive a compact title from a longer task description."""
    text = str(description or "").strip()
    if not text:
        return ""
    text = _SPACE_RE.sub(" ", text)
    text = _LEADING_MARK_RE.sub("", text).strip()
    if not text:
        return ""

    head = _SPLIT_RE.split(text, maxsplit=1)[0].strip() or text

    # Chinese-first shortening: cap to short phrase (~12 chars)
    if _ZH_RE.search(head):
        compact_zh = head[:12].strip()
        if len(head) > len(compact_zh):
            compact_zh = compact_zh.rstrip("，。；：、 ") + "…"
        return compact_zh

    # English/space-separated text: cap to ~8 words
    words = [w for w in head.split(" ") if w]
    if len(words) > 8:
        return " ".join(words[:8]).strip() + "…"

    # Final guard for very long single-token strings
    if len(head) <= max_len:
        return head
    return head[: max_len - 1].rstrip() + "…"


def ensure_task_title(task: Dict) -> Dict:
    """Fill `task['title']` in place when absent, or keep provided title from LLM.
    
    Prefers LLM-generated title if present and reasonable (not blank).
    Only derives title from description if no title is provided.
    """
    if not isinstance(task, dict):
        return task

    # If title already provided (e.g., from LLM in Decompose/AddTasks), keep it
    existing_title = str(task.get("title") or "").strip()
    if existing_title:
        # Still apply length limits for display safety (max 20 chars Chinese, 12 words English)
        if _ZH_RE.search(existing_title):
            # Chinese: limit to 20 characters with ellipsis if too long
            if len(existing_title) > 20:
                task["title"] = existing_title[:20].rstrip("，。；：、 ") + "…"
            else:
                task["title"] = existing_title
        else:
            # English: limit to 12 words with ellipsis if too long
            words = existing_title.split()
            if len(words) > 12:
                task["title"] = " ".join(words[:12]) + "…"
            else:
                task["title"] = existing_title
    else:
        # No title provided: derive from description
        source = str(task.get("description") or task.get("objective") or "")
        task["title"] = derive_task_title(source)
    
    return task


def ensure_task_titles(tasks: Iterable[Dict]) -> None:
    """Fill missing title for each task dict in place."""
    for task in tasks or []:
        ensure_task_title(task)
