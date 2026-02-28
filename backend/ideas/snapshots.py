import os
import json
from datetime import datetime
from typing import Dict, List, Any

# 定义快照存储路径
SNAPSHOT_DIR = os.path.join(os.getcwd(), "data", "cache", "snapshots")


def save_snapshot(refinement_data: Dict, results: List[Dict], custom_name: str = None):
    """
    保存当前的科研状态（细化数据 + 结果报告）到 JSON 文件。
    """
    if not os.path.exists(SNAPSHOT_DIR):
        os.makedirs(SNAPSHOT_DIR)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 智能抓取标题逻辑
    if not custom_name:
        if results and len(results) > 0:
            res = results[0]
            # 兼容多种结构：优先找根部的 title，再找 topic 里的 title
            title = res.get("title") or res.get("topic", {}).get("title") or "untitled研究"

            # 清理文件名中的非法字符
            safe_title = "".join([c if c.isalnum() or c == ' ' else "_" for c in title])
            safe_title = "_".join(safe_title.split())  # 合并多余空格
            safe_title = safe_title[:50]  # 限制长度

            custom_name = f"{timestamp}_{safe_title}"
        else:
            custom_name = f"{timestamp}_empty_snapshot"

    if not custom_name.endswith(".json"):
        custom_name += ".json"

    filepath = os.path.join(SNAPSHOT_DIR, custom_name)

    data = {
        "timestamp": timestamp,
        "refinement_data": refinement_data,
        "results": results
    }

    # 【优化点】使用 encoding="utf-8" 和 ensure_ascii=False 确保中文正常显示
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return custom_name


def list_snapshots() -> List[Dict]:
    """
    返回所有已保存快照的元数据列表，按修改时间倒序（最新的在前）。
    """
    if not os.path.exists(SNAPSHOT_DIR):
        return []

    files = [f for f in os.listdir(SNAPSHOT_DIR) if f.endswith(".json")]
    # 按修改时间排序
    files.sort(key=lambda x: os.path.getmtime(os.path.join(SNAPSHOT_DIR, x)), reverse=True)

    snapshots = []
    for f in files:
        try:
            # 解析文件名: YYYYMMDD_HHMMSS_Title.json
            parts = f.replace(".json", "").split("_", 2)
            timestamp_display = ""
            title_display = f

            if len(parts) >= 2:
                # 格式化时间显示 e.g., 2026-03-01 02:15
                timestamp_display = f"{parts[0][:4]}-{parts[0][4:6]}-{parts[0][6:8]} {parts[1][:2]}:{parts[1][2:4]}"
                if len(parts) > 2:
                    title_display = parts[2].replace("_", " ")

            snapshots.append({
                "filename": f,
                "timestamp": timestamp_display,
                "title": title_display,
                "path": os.path.join(SNAPSHOT_DIR, f)
            })
        except Exception:
            snapshots.append({
                "filename": f,
                "timestamp": "未知时间",
                "title": f,
                "path": os.path.join(SNAPSHOT_DIR, f)
            })

    return snapshots


def load_snapshot(filename: str) -> Any:
    """
    加载特定的快照 JSON 文件。
    """
    filepath = os.path.join(SNAPSHOT_DIR, filename)
    if not os.path.exists(filepath):
        return None

    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)