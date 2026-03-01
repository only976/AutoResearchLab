"""
Level-order tree layout for decomposition (task_id hierarchy).
Each node gets a fixed slot — subtree width does not affect sibling spacing.

居中策略（统一公式 offset = (container - content) / 2）:
  - 树内居中: 每层在 max_level_width 内居中
  - 树整体居中: 整棵树在画布 width 内居中
"""

from typing import Any, Dict, List, Optional

from shared.graph import get_parent_id, natural_task_id_key

from .constants import (
    DEFAULT_NODE_H,
    DEFAULT_NODE_SEP,
    DEFAULT_NODE_W,
    DEFAULT_PADDING,
    DEFAULT_RANK_SEP,
)


def _build_tree(tasks: List[Dict]) -> Dict[str, List[str]]:
    """Build parent -> sorted children from task_id hierarchy."""
    ids = {t["task_id"] for t in tasks if t.get("task_id")}
    children: Dict[str, List[str]] = {}
    for t in tasks:
        tid = t.get("task_id")
        if not tid:
            continue
        parent = get_parent_id(tid)
        if parent in ids and parent != tid:
            children.setdefault(parent, []).append(tid)
    for pid in children:
        children[pid].sort(key=natural_task_id_key)
    return children


def compute_decomposition_layout(
    tasks: List[Dict[str, Any]],
    node_w: int = DEFAULT_NODE_W,
    node_h: int = DEFAULT_NODE_H,
    node_sep: int = DEFAULT_NODE_SEP,
    rank_sep: int = DEFAULT_RANK_SEP,
    padding: int = DEFAULT_PADDING,
) -> Optional[Dict[str, Any]]:
    """
    Level-order layout: each node gets a fixed slot. Subtree width does not
    affect the distance between sibling (parent) nodes.
    Returns {nodes: {id: {x,y,w,h}}, edges: [{from,to,points}], width, height}.
    """
    valid = [t for t in (tasks or []) if t.get("task_id")]
    if not valid:
        return None

    ids = {t["task_id"] for t in valid}
    children_map = _build_tree(valid)

    all_children = {c for cs in children_map.values() for c in cs}
    roots = sorted([tid for tid in ids if tid not in all_children], key=natural_task_id_key)
    if not roots:
        return None

    slot_w = node_w + node_sep

    # Level-order (BFS): nodes by depth, each level left-to-right by task_id
    levels: List[List[str]] = []
    frontier = list(roots)
    while frontier:
        levels.append(frontier[:])
        next_frontier = []
        for nid in frontier:
            kids = sorted(children_map.get(nid, []), key=natural_task_id_key)
            next_frontier.extend(kids)
        frontier = next_frontier

    # 统一居中公式: offset = (container - content) / 2
    # 1) 树内居中: 每层在其容器(max_level_width)内居中
    max_level_width = max(len(layer) * slot_w for layer in levels) if levels else 0
    positions: Dict[str, Dict[str, Any]] = {}
    for depth, layer in enumerate(levels):
        y = depth * (node_h + rank_sep)
        level_width = len(layer) * slot_w
        level_offset = (max_level_width - level_width) / 2
        for idx, nid in enumerate(layer):
            x = level_offset + idx * slot_w
            positions[nid] = {"x": x, "y": y, "w": node_w, "h": node_h}

    # Build edges
    edges: List[Dict[str, Any]] = []
    for parent, kids in children_map.items():
        if parent not in positions:
            continue
        pp = positions[parent]
        src_cx = pp["x"] + pp["w"] / 2
        src_bottom = pp["y"] + pp["h"]
        for c in kids:
            if c not in positions:
                continue
            cp = positions[c]
            dst_cx = cp["x"] + cp["w"] / 2
            dst_top = cp["y"]
            edges.append({
                "from": parent,
                "to": c,
                "points": [[round(src_cx, 1), round(src_bottom, 1)],
                          [round(dst_cx, 1), round(dst_top, 1)]],
            })

    # Normalize to origin and add padding
    min_x = min(p["x"] for p in positions.values())
    min_y = min(p["y"] for p in positions.values())
    max_x = max(p["x"] + p["w"] for p in positions.values())
    max_y = max(p["y"] + p["h"] for p in positions.values())
    content_w = max_x - min_x
    content_h = max_y - min_y
    off_x = min_x - padding
    off_y = min_y - padding

    width = round(max(content_w + padding * 2, 200), 1)
    height = round(max(content_h + padding * 2, 100), 1)
    # 2) 树整体居中: 内容在画布内居中（统一公式 container - content）
    center_offset = (width - content_w - padding * 2) / 2

    nodes_out = {}
    for nid, pos in positions.items():
        if nid in ids:
            nodes_out[nid] = {
                "x": round(pos["x"] - off_x + center_offset, 1),
                "y": round(pos["y"] - off_y, 1),
                "w": pos["w"],
                "h": pos["h"],
            }

    edges_out = []
    for e in edges:
        shifted = [[round(pt[0] - off_x + center_offset, 1), round(pt[1] - off_y, 1)] for pt in e["points"]]
        edges_out.append({"from": e["from"], "to": e["to"], "points": shifted})

    return {"nodes": nodes_out, "edges": edges_out, "width": width, "height": height}
