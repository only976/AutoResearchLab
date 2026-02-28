"""
Stage-based graph layout for Execution Graph sub-view.

Uses task.stage (1-based) to arrange nodes in rows. Equivalent tasks (same stage,
same upstream set, same downstream set) are merged into a single node.

See EXECUTION_LAYOUT_RULES.md for full sorting and alignment rules.
"""

from typing import Any, Dict, List, Optional, Set, Tuple

from shared.graph import natural_task_id_key

from .constants import (
    DEFAULT_NODE_H,
    DEFAULT_NODE_SEP,
    DEFAULT_NODE_W,
    DEFAULT_PADDING,
    DEFAULT_RANK_SEP,
)


def _slot_sort_key(
    slot: List[str],
    conn_type: str,
    max_cross: int,
) -> Tuple[int, int, Tuple]:
    """Sort key: (conn_priority, -max_cross for cross-layer, id)."""
    # 一对多=0, 一对一=1, 多对一=2, 跨层=3
    priority = {"一对多": 0, "一对一": 1, "多对一": 2, "跨层": 3}.get(conn_type, 4)
    rep_id = slot[0]
    # 跨层时按 max_cross 升序（小先大后），同值按 id
    return (priority, max_cross if conn_type == "跨层" else 0, natural_task_id_key(rep_id))


def compute_execution_graph_layout(
    tasks: List[Dict[str, Any]],
    node_w: int = DEFAULT_NODE_W,
    node_h: int = DEFAULT_NODE_H,
    node_sep: int = DEFAULT_NODE_SEP,
    rank_sep: int = DEFAULT_RANK_SEP,
    padding: int = DEFAULT_PADDING,
) -> Optional[Dict[str, Any]]:
    """
    Compute layout from staged tasks. Each stage = one row.
    Equivalent tasks (same pred, same succ) are merged into one node.

    Returns {nodes: {id: {x,y,w,h} or {x,y,w,h,ids}}, edges, width, height}
    or None if tasks are empty.
    """
    valid = [t for t in (tasks or []) if t.get("task_id")]
    if not valid:
        return None

    stages: Dict[int, List[Dict]] = {}
    for t in valid:
        idx = (t.get("stage") or 1) - 1
        if idx not in stages:
            stages[idx] = []
        stages[idx].append(t)

    if not stages:
        return None

    stage_indices = sorted(stages.keys())
    layers = [stages[i] for i in stage_indices]

    # Detect parallel groups within each stage (same stage)
    task_by_id = {t["task_id"]: t for t in valid}
    succ_map: Dict[str, Set[str]] = {}
    pred_map: Dict[str, Set[str]] = {}
    for t in valid:
        tid = t["task_id"]
        succ_map[tid] = set()
        pred_map[tid] = set()
    for t in valid:
        for dep in t.get("dependencies") or []:
            if dep in task_by_id and dep != t["task_id"]:
                succ_map[dep].add(t["task_id"])
                pred_map[t["task_id"]].add(dep)

    # Equivalent tasks: same (pred, succ) in same stage → merge into one slot
    node_to_group: Dict[str, List[str]] = {}
    merged_slots_by_layer: List[List[List[str]]] = []
    for layer in layers:
        by_pred_succ: Dict[tuple, List[str]] = {}
        for t in layer:
            tid = t["task_id"]
            pred = frozenset(pred_map.get(tid, set()))
            succ = frozenset(succ_map.get(tid, set()))
            key = (pred, succ)
            by_pred_succ.setdefault(key, []).append(tid)
        seen: Set[tuple] = set()
        slots: List[List[str]] = []
        for t in layer:
            tid = t["task_id"]
            pred = frozenset(pred_map.get(tid, set()))
            succ = frozenset(succ_map.get(tid, set()))
            key = (pred, succ)
            if key not in seen:
                seen.add(key)
                ids = by_pred_succ[key]
                slots.append(ids)
                if len(ids) >= 2:
                    for nid in ids:
                        node_to_group[nid] = ids
        merged_slots_by_layer.append(slots)

    # Build slot-level pred/succ with stage info (rep_id -> {(rep_id, stage_diff)})
    slot_succ: Dict[str, Set[Tuple[str, int]]] = {}
    slot_pred: Dict[str, Set[Tuple[str, int]]] = {}
    slot_max_cross_out: Dict[str, int] = {}  # 仅连出线：跨层任务排序用
    for layer_idx, slots in enumerate(merged_slots_by_layer):
        for slot in slots:
            rep = slot[0]
            slot_succ.setdefault(rep, set())
            slot_pred.setdefault(rep, set())
            slot_max_cross_out[rep] = 0
    for t in valid:
        tid = t["task_id"]
        stage_t = (t.get("stage") or 1) - 1
        t_rep = tid if tid not in node_to_group else node_to_group[tid][0]
        for dep_id in t.get("dependencies") or []:
            if dep_id not in task_by_id or dep_id == tid:
                continue
            dep = task_by_id[dep_id]
            stage_dep = (dep.get("stage") or 1) - 1
            if stage_dep >= stage_t:
                continue
            dep_rep = dep_id if dep_id not in node_to_group else node_to_group[dep_id][0]
            diff = stage_t - stage_dep
            slot_succ[dep_rep].add((t_rep, diff))
            slot_pred[t_rep].add((dep_rep, diff))
            # 仅连出线：跨层任务按最大跨层数排序时只用连出线
            slot_max_cross_out[dep_rep] = max(slot_max_cross_out[dep_rep], diff)

    slot_w = node_w + node_sep

    # Sort and position slots per layer (recursive top-down)
    slot_positions: Dict[str, Dict[str, Any]] = {}
    for layer_idx, slots in enumerate(merged_slots_by_layer):
        # 1. 先摘出有跨层连出线的任务，放最后，不参与后续对齐计算
        has_cross_out = {
            slot[0]: any(d > 1 for _, d in slot_succ.get(slot[0], set()))
            for slot in slots
        }
        non_cross_slots = [s for s in slots if not has_cross_out.get(s[0], False)]
        cross_slots = [s for s in slots if has_cross_out.get(s[0], False)]

        def classify_non_cross(rep: str) -> str:
            """仅用于非跨层 slot，不包含跨层类型"""
            succs = slot_succ.get(rep, set())
            adj_succ = {r for r, d in succs if d == 1}
            if not adj_succ:
                return "跨层"  # sink，按 id 排
            if len(adj_succ) > 1:
                return "一对多"
            child = next(iter(adj_succ))
            preds_of_child = slot_pred.get(child, set())
            adj_pred_of_child = {r for r, d in preds_of_child if d == 1}
            return "多对一" if len(adj_pred_of_child) > 1 else "一对一"

        non_cross_sorted = sorted(
            non_cross_slots,
            key=lambda s: _slot_sort_key(s, classify_non_cross(s[0]), 0),
        )
        cross_sorted = sorted(
            cross_slots,
            key=lambda s: (slot_max_cross_out.get(s[0], 0), natural_task_id_key(s[0])),
        )
        sorted_slots = non_cross_sorted + cross_sorted

        y = layer_idx * (node_h + rank_sep)

        if layer_idx == 0:
            for pos, slot in enumerate(sorted_slots):
                rep_id = slot[0]
                x = pos * slot_w
                slot_positions[rep_id] = {"id": rep_id, "x": float(x), "y": float(y), "w": node_w, "h": node_h, "slot": slot}
        else:
            # Downstream alignment from prev layer（仅非跨层任务参与）
            preds = slot_pred
            prev_slots = merged_slots_by_layer[layer_idx - 1]
            prev_positions = {s[0]: slot_positions[s[0]] for s in prev_slots if s[0] in slot_positions}

            # 仅对 non_cross_sorted 做对齐计算，跨层任务不参与
            alignments: List[Tuple[float, List[List[str]]]] = []  # (target_x, list of slots to place)

            placed: Set[str] = set()
            for slot in non_cross_sorted:
                rep = slot[0]
                if rep in placed:
                    continue
                pred_tuples = preds.get(rep, set())
                adj_preds = [r for r, d in pred_tuples if d == 1]
                if not adj_preds:
                    # no adjacent pred: use next free position
                    alignments.append((len(alignments) * slot_w, [slot]))
                    placed.add(rep)
                    continue
                if len(adj_preds) == 1:
                    p = adj_preds[0]
                    if p not in prev_positions:
                        alignments.append((len(alignments) * slot_w, [slot]))
                        placed.add(rep)
                        continue
                    px = prev_positions[p]["x"] + prev_positions[p]["w"] / 2
                    # Check if one-to-one or one-to-many (we are one of many)
                    p_succs = slot_succ.get(p, set())
                    adj_p_succ = [r for r, d in p_succs if d == 1]
                    if len(adj_p_succ) == 1:
                        alignments.append((px, [slot]))
                    else:
                        # one-to-many: we're one of many, need to group all siblings
                        siblings = [slot]
                        for s in non_cross_sorted:
                            if s[0] == rep:
                                continue
                            if s[0] in placed:
                                continue
                            s_preds = [r for r, d in preds.get(s[0], set()) if d == 1]
                            if set(s_preds) == {p}:
                                siblings.append(s)
                        siblings.sort(key=lambda s: natural_task_id_key(s[0]))
                        alignments.append((px, siblings))
                        for s in siblings:
                            placed.add(s[0])
                    placed.add(rep)
                else:
                    # many-to-one: align with center of parents
                    cx = sum(prev_positions.get(r, {}).get("x", 0) + prev_positions.get(r, {}).get("w", 0) / 2 for r in adj_preds if r in prev_positions) / len([r for r in adj_preds if r in prev_positions])
                    if not adj_preds or not any(r in prev_positions for r in adj_preds):
                        cx = len(alignments) * slot_w
                    alignments.append((cx, [slot]))
                    placed.add(rep)

            # Assign x: 非跨层按对齐规则；跨层任务紧接其后，不参与对齐
            x_assign: Dict[str, float] = {}
            cursor = float("-inf")  # allow negative x; final normalization will shift
            for target_x, group in sorted(alignments, key=lambda a: a[0]):
                n = len(group)
                total_w = node_w if n == 1 else n * slot_w - node_sep
                start_x = target_x - total_w / 2
                start_x = max(start_x, cursor)  # avoid overlap with previous groups
                for i, s in enumerate(group):
                    x_assign[s[0]] = start_x + i * slot_w
                cursor = max(cursor, max(x_assign[s[0]] for s in group)) + slot_w

            # 跨层任务放在最后，顺序排列
            cross_start = cursor if cursor != float("-inf") else 0
            for i, slot in enumerate(cross_sorted):
                x_assign[slot[0]] = cross_start + i * slot_w

            for slot in sorted_slots:
                rep_id = slot[0]
                x = x_assign.get(rep_id, len(slot_positions) * slot_w)
                slot_positions[rep_id] = {"id": rep_id, "x": float(x), "y": float(y), "w": node_w, "h": node_h, "slot": slot}

    edges = []
    emitted: Set[tuple] = set()
    for t in valid:
        tid = t["task_id"]
        deps = t.get("dependencies") or []
        stage_t = (t.get("stage") or 1) - 1
        t_slot = node_to_group.get(tid)
        t_rep = tid if not t_slot else t_slot[0]
        for dep_id in deps:
            if dep_id not in task_by_id or dep_id == tid:
                continue
            dep = task_by_id[dep_id]
            stage_dep = (dep.get("stage") or 1) - 1
            if stage_dep >= stage_t:
                continue
            dep_slot = node_to_group.get(dep_id)
            dep_rep = dep_id if not dep_slot else dep_slot[0]
            if dep_slot and dep_id != dep_slot[0]:
                continue
            key = (dep_rep, t_rep)
            if key in emitted:
                continue
            emitted.add(key)
            sp = slot_positions[dep_rep]
            dp = slot_positions[t_rep]
            adjacent = (stage_t - stage_dep) == 1
            src_pt = [sp["x"] + sp["w"] / 2, sp["y"] + sp["h"]]
            dst_pt = [dp["x"] + dp["w"] / 2, dp["y"]]
            from_val = dep_slot if dep_slot else dep_id
            to_val = t_slot if t_slot else tid
            edges.append({"from": from_val, "to": to_val, "points": [src_pt, dst_pt], "adjacent": adjacent})

    if not slot_positions:
        return None

    min_x = min(p["x"] for p in slot_positions.values())
    min_y = min(p["y"] for p in slot_positions.values())
    max_x = max(p["x"] + p["w"] for p in slot_positions.values())
    max_y = max(p["y"] + p["h"] for p in slot_positions.values())
    width = max(max_x - min_x + padding * 2, 200)
    height = round(max(max_y - min_y + padding * 2, 100), 1)
    off_x = (min_x + max_x) / 2 - width / 2
    off_y = (min_y + max_y) / 2 - height / 2

    nodes_out = {}
    for rep_id, pos in slot_positions.items():
        slot = pos["slot"]
        node_data = {
            "x": round(pos["x"] - off_x, 1),
            "y": round(pos["y"] - off_y, 1),
            "w": pos["w"],
            "h": pos["h"],
        }
        if len(slot) >= 2:
            node_data["ids"] = slot
        nodes_out[rep_id] = node_data

    edges_out = []
    for e in edges:
        shifted = [[round(pt[0] - off_x, 1), round(pt[1] - off_y, 1)] for pt in e["points"]]
        from_val = e["from"]
        to_val = e["to"]
        edges_out.append({"from": from_val, "to": to_val, "points": shifted, "adjacent": e["adjacent"]})

    width = round(width, 1)

    return {
        "nodes": nodes_out,
        "edges": edges_out,
        "width": width,
        "height": height,
    }


