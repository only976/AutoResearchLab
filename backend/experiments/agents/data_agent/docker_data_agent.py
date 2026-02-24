"""独立 Data Agent（面向仿真/实验结果分析） - LLM 增强版

功能：
- 支持读取 `.csv` 和 `.log`（简单数字序列）作为仿真输出输入
- **使用 LLM 智能识别列的语义类型**（可回退到规则识别）
- 执行物理/逻辑可靠性校验（收敛性、NaN/无穷、能量守恒近似等）
- 在关键失败时触发 Git 回滚机制（通过 `backend.tools.git_ops.rollback_last_commit`）
- 生成科研可视化（收敛曲线 SVG，base64）并输出 JSON 报告

设计原则：优先使用标准库以减少新增依赖；与原先 Dockerfile 检测功能兼容性降低，转为聚焦于仿真数据分析。
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import math
import os
import re
import statistics
import uuid
import datetime
import subprocess
import tempfile
import shutil
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

# Import visualization module
try:
    from .visualizer import DataVisualizer, create_line_chart, create_bar_chart
    VISUALIZER_AVAILABLE = True
except ImportError:
    # Fallback to legacy inline functions
    VISUALIZER_AVAILABLE = False

# Load .env file if exists
def load_env():
    """Load environment variables from .env file"""
    env_path = Path(__file__).parent.parent.parent / '.env'
    if env_path.exists():
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    if key and value:
                        os.environ[key] = value

load_env()

# optional: git ops helper
try:
    from backend.tools.git_ops import rollback_last_commit
except Exception:
    # Try dynamic import by file location (when script executed directly)
    try:
        import importlib.util
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        git_ops_path = os.path.join(repo_root, "backend", "tools", "git_ops.py")
        spec = importlib.util.spec_from_file_location("backend.tools.git_ops", git_ops_path)
        git_ops = importlib.util.module_from_spec(spec)  # type: ignore
        spec.loader.exec_module(git_ops)  # type: ignore
        rollback_last_commit = getattr(git_ops, "rollback_last_commit")
    except Exception:
        def rollback_last_commit(repo_path: Optional[str] = None, steps: int = 1) -> bool:  # type: ignore
            return False

# optional: LLM integration for intelligent column identification
LLM_AVAILABLE = False
try:
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.agents import Agent
    from google.adk import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai.types import Content, Part
    LLM_AVAILABLE = True
    print(f"✓ LLM modules imported successfully, LLM_AVAILABLE={LLM_AVAILABLE}")
except ImportError as e:
    print(f"✗ LLM import failed: {e}")
    pass

def build_docker_image(dockerfile_path: str, tag: str) -> bool:
    """Build a Docker image from the given Dockerfile path.

    Args:
        dockerfile_path: Absolute path to the Dockerfile.
        tag: Tag to assign to the built image.

    Returns:
        True if build succeeded, False otherwise.
    """
    context_dir = os.path.dirname(dockerfile_path)
    dockerfile_name = os.path.basename(dockerfile_path)
    try:
        subprocess.check_call(
            ["docker", "build", "-t", tag, "-f", dockerfile_name, "."],
            cwd=context_dir,
        )
        return True
    except subprocess.CalledProcessError:
        return False
    except FileNotFoundError:
        # Docker not installed
        return False
 

def run_docker_container(image_tag: str, output_host_dir: str, container_output_path: str = "/output") -> bool:
    """Run a Docker container, mounting output_host_dir to container_output_path.

    Args:
        image_tag: The Docker image tag to run.
        output_host_dir: Host directory to bind-mount (will be created if not exists).
        container_output_path: Path inside container where output is expected.

    Returns:
        True if run succeeded (exit 0), False otherwise.
    """
    os.makedirs(output_host_dir, exist_ok=True)
    try:
        subprocess.check_call(
            ["docker", "run", "--rm", "-v", f"{output_host_dir}:{container_output_path}", image_tag],
        )
        return True
    except subprocess.CalledProcessError:
        return False
    except FileNotFoundError:
        return False


def collect_files_from_dir(base_dir: str, extensions: tuple = (".csv", ".log")) -> List[str]:
    """Recursively collect files with given extensions from base_dir."""
    found = []
    for root, dirs, files in os.walk(base_dir):
        for f in files:
            if f.lower().endswith(extensions):
                found.append(os.path.join(root, f))
    return found

def read_csv(path: str) -> Tuple[List[str], List[List[float]]]:
    """Read CSV and return header and columns as floats (non-numeric become NaN)."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        return [], []
    header = rows[0]
    cols: List[List[float]] = [[math.nan for _ in rows[1:]] for _ in header]
    for i, row in enumerate(rows[1:]):
        for j, val in enumerate(row[: len(header)]):
            try:
                cols[j][i] = float(val)
            except Exception:
                cols[j][i] = math.nan
    return header, cols


def read_log_numbers(path: str) -> List[float]:
    """Extract numbers from a simple log file (one numeric value per line or lines containing a numeric token)."""
    nums: List[float] = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # find first numeric token
            m = re.search(r"(-?\d+\.?\d*(e[-+]?\d+)?)", line, re.IGNORECASE)
            if m:
                try:
                    nums.append(float(m.group(1)))
                except Exception:
                    pass
    return nums


def call_llm_for_column_mapping(headers: List[str], file_name: str = "") -> Optional[Dict[str, str]]:
    """使用 LLM 智能识别 CSV 表头的语义类型。
    
    Args:
        headers: CSV 表头列表
        file_name: 文件名（提供上下文）
    
    Returns:
        字典映射 {column_name: semantic_type}，例如:
        {
            'residual_error': 'loss',
            'Total_Joule': 'conserved',
            'val_acc': 'accuracy'
        }
        如果 LLM 不可用或失败，返回 None
    """
    if not LLM_AVAILABLE:
        print("⚠️ LLM not available (LLM_AVAILABLE=False)")
        return None
    
    api_key = os.getenv("SF_API_KEY")
    if not api_key:
        print("⚠️ SF_API_KEY not found in environment")
        return None
    
    print(f"✓ Starting LLM call with SiliconFlow API, key: {api_key[:10]}...")
    
    try:
        model = LiteLlm(
            model="openai/Qwen/Qwen2.5-7B-Instruct",
            api_base="https://api.siliconflow.cn/v1",
            api_key=api_key,
        )
        
        context_info = f"文件名: {file_name}\n" if file_name else ""
        prompt = f"""分析以下 CSV 表头并识别每列的语义类型。

{context_info}表头列表: {headers}

请为每个列名分配最合适的语义类型：
- 'loss': 损失/误差类（如 loss, error, mse, rmse, residual, cost, 损失）
- 'accuracy': 准确率/性能类（如 accuracy, precision, recall, f1, score, auc, 准确率）
- 'conserved': 守恒量（如 energy, momentum, mass, charge, 能量, 动量）
- 'time': 时间/迭代计数（如 time, step, epoch, iteration, 时间, 步数）
- 'physical': 一般物理量（如 temperature, pressure, velocity, 温度, 压力）
- 'unknown': 无法确定

请以 JSON 格式返回，例如:
{{"residual_error": "loss", "Total_Joule": "conserved", "epoch": "time", "val_acc": "accuracy"}}

只返回 JSON，不要其他解释文字。"""
        
        agent = Agent(
            model=model,
            name="column_identifier",
            instruction="你是一个数据分析助手，专门识别数据表头的语义类型。只返回 JSON 格式的结果。",
        )
        
        runner = Runner(
            agent=agent,
            app_name="auto_research",
            session_service=InMemorySessionService(),
            auto_create_session=True,
        )
        
        events = runner.run(
            user_id="user",
            session_id=str(uuid.uuid4()),
            new_message=Content(role="user", parts=[Part(text=prompt)]),
        )
        
        response = ""
        for event in events:
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        response += part.text
        
        # Parse JSON response
        response = response.strip()
        # Extract JSON from markdown code blocks if present
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            response = response.split("```")[1].split("```")[0].strip()
        
        mapping = json.loads(response)
        
        # Validate mapping
        valid_types = {'loss', 'accuracy', 'conserved', 'time', 'physical', 'unknown'}
        filtered_mapping = {k: v for k, v in mapping.items() if v in valid_types}
        
        return filtered_mapping if filtered_mapping else None
        
    except Exception as e:
        # LLM call failed, return None to fall back to rule-based
        print(f"LLM column identification failed: {e}")
        return None


def classify_column_semantic(col_name: str, data: List[float]) -> str:
    """智能识别列的语义类型，基于列名和数据特征（规则方法）。
    
    返回类型：
    - 'loss': 损失/误差类（应递减）
    - 'accuracy': 准确率/性能类（应递增，范围0-1）
    - 'conserved': 守恒量（能量、动量等，应稳定）
    - 'time': 时间/迭代计数器（严格递增）
    - 'physical': 一般物理量（温度、压力等）
    - 'unknown': 未知类型
    """
    col_lower = col_name.lower()
    
    # 关键词映射（支持中英文）
    loss_keywords = ['loss', 'error', 'mse', 'rmse', 'mae', 'cost', '损失', '误差']
    accuracy_keywords = ['accuracy', 'acc', 'precision', 'recall', 'f1', 'score', 'auc', '准确率', '精度']
    conserved_keywords = ['energy', 'momentum', 'mass', 'charge', 'entropy', '能量', '动量', '质量', '电荷', '熵']
    time_keywords = ['time', 'step', 'epoch', 'iteration', 'iter', 't', '时间', '步数', '迭代']
    physical_keywords = ['temperature', 'temp', 'pressure', 'velocity', 'speed', 'force', '温度', '压力', '速度', '力']
    
    # 基于列名的初步判断
    if any(kw in col_lower for kw in loss_keywords):
        return 'loss'
    if any(kw in col_lower for kw in accuracy_keywords):
        return 'accuracy'
    if any(kw in col_lower for kw in conserved_keywords):
        return 'conserved'
    if any(kw in col_lower for kw in time_keywords):
        return 'time'
    if any(kw in col_lower for kw in physical_keywords):
        return 'physical'
    
    # 基于数据特征的辅助判断
    clean = [v for v in data if not (math.isnan(v) or math.isinf(v))]
    if len(clean) < 3:
        return 'unknown'
    
    # 计算数据特征
    is_monotonic_increasing = all(clean[i] <= clean[i+1] for i in range(len(clean)-1))
    is_monotonic_decreasing = all(clean[i] >= clean[i+1] for i in range(len(clean)-1))
    value_range = max(clean) - min(clean)
    mean_val = statistics.mean(clean)
    relative_variation = value_range / abs(mean_val) if mean_val != 0 else float('inf')
    
    # 特征匹配
    if is_monotonic_increasing:
        # 严格递增
        if all(abs(clean[i+1] - clean[i] - 1) < 0.01 for i in range(min(10, len(clean)-1))):
            return 'time'  # 可能是计数器
        elif max(clean) <= 1.2 and min(clean) >= -0.1:
            return 'accuracy'  # 可能是准确率（接近0-1范围）
    
    if is_monotonic_decreasing and mean_val > 0:
        return 'loss'  # 单调递减可能是损失
    
    if relative_variation < 0.1:
        return 'conserved'  # 相对变化小于10%可能是守恒量
    
    return 'unknown'


def parse_input_files(paths: List[str], use_llm: bool = True) -> Dict[str, Any]:
    """Parse multiple input files (.csv/.log). Returns a structured dict with series data.
    
    Args:
        paths: 输入文件路径列表
        use_llm: 是否启用 LLM 智能识别（默认 True，如果不可用会自动回退）
    """
    parsed: Dict[str, Any] = {"series": {}, "column_types": {}, "llm_used": False}
    
    for p in paths:
        p = os.path.abspath(p)
        if not os.path.exists(p):
            continue
        ext = os.path.splitext(p)[1].lower()
        name = os.path.basename(p)
        
        if ext == ".csv":
            header, cols = read_csv(p)
            
            # 尝试使用 LLM 批量识别所有列（更智能，考虑上下文）
            llm_mapping = None
            if use_llm and header:
                print(f"🔍 Attempting LLM column identification for {name} with headers: {header}")
                llm_mapping = call_llm_for_column_mapping(header, file_name=name)
                if llm_mapping:
                    parsed["llm_used"] = True
                    print(f"✓ LLM mapping successful: {llm_mapping}")
                else:
                    print(f"✗ LLM mapping returned None, falling back to rule-based")
            
            for i, col in enumerate(cols):
                key = header[i] if header and i < len(header) and header[i].strip() else f"col_{i}"
                full_key = f"{name}::{key}"
                parsed["series"][full_key] = col
                
                # 优先使用 LLM 识别结果，回退到规则识别
                if llm_mapping and key in llm_mapping:
                    parsed["column_types"][full_key] = llm_mapping[key]
                else:
                    parsed["column_types"][full_key] = classify_column_semantic(key, col)
        else:
            # Log 文件使用规则识别
            nums = read_log_numbers(p)
            parsed["series"][name] = nums
            parsed["column_types"][name] = classify_column_semantic(name, nums)
    
    return parsed


def check_convergence(series_name: str, data: List[float], expected_trend: str = "decrease") -> Dict[str, Any]:
    """检查单个序列的收敛性。
    
    Args:
        series_name: 序列名称
        data: 数据列表
        expected_trend: 期望趋势 ('decrease' 或 'increase')
    
    Returns:
        检查结果字典
    """
    clean = [v for v in data if not math.isnan(v)]
    if len(clean) < 5:
        return {
            "id": f"convergence_{series_name}",
            "name": f"收敛性检查 - {series_name}",
            "status": "warn",
            "details": "数据点不足5个，无法判断趋势"
        }
    
    n = len(clean)
    k = max(1, n // 10)
    start_avg = statistics.mean(clean[:k])
    end_avg = statistics.mean(clean[-k:])
    
    if expected_trend == "decrease":
        if end_avg < start_avg:
            improvement = (start_avg - end_avg) / start_avg * 100
            return {
                "id": f"convergence_{series_name}",
                "name": f"收敛性检查 - {series_name}",
                "status": "pass",
                "details": f"从 {start_avg:.4g} 降到 {end_avg:.4g}，改善 {improvement:.1f}%"
            }
        else:
            return {
                "id": f"convergence_{series_name}",
                "name": f"收敛性检查 - {series_name}",
                "status": "fail",
                "details": f"从 {start_avg:.4g} 增长到 {end_avg:.4g}，未见收敛（预期递减）"
            }
    else:  # increase
        if end_avg > start_avg:
            improvement = (end_avg - start_avg) * 100
            return {
                "id": f"improvement_{series_name}",
                "name": f"性能提升检查 - {series_name}",
                "status": "pass",
                "details": f"从 {start_avg:.4g} 升至 {end_avg:.4g}，提升 {improvement:.1f}%"
            }
        else:
            return {
                "id": f"improvement_{series_name}",
                "name": f"性能提升检查 - {series_name}",
                "status": "warn",
                "details": f"从 {start_avg:.4g} 降至 {end_avg:.4g}，未见提升（预期递增）"
            }


def check_conservation(series_name: str, data: List[float]) -> Dict[str, Any]:
    """检查守恒量的稳定性。"""
    clean = [v for v in data if not (math.isnan(v) or math.isinf(v))]
    if len(clean) < 3:
        return {
            "id": f"conservation_{series_name}",
            "name": f"守恒性检查 - {series_name}",
            "status": "warn",
            "details": "数据点不足，无法检查守恒性"
        }
    
    drift = max(clean) - min(clean)
    avg = statistics.mean(clean)
    relative_drift = abs(drift / avg) if avg != 0 else 0
    
    if relative_drift > 0.1:
        return {
            "id": f"conservation_{series_name}",
            "name": f"守恒性检查 - {series_name}",
            "status": "fail",
            "details": f"相对漂移 {relative_drift*100:.2f}% 超过阈值 10% (drift={drift:.4g}, avg={avg:.4g})"
        }
    elif relative_drift > 0.05:
        return {
            "id": f"conservation_{series_name}",
            "name": f"守恒性检查 - {series_name}",
            "status": "warn",
            "details": f"相对漂移 {relative_drift*100:.2f}% 略高 (drift={drift:.4g}, avg={avg:.4g})"
        }
    else:
        return {
            "id": f"conservation_{series_name}",
            "name": f"守恒性检查 - {series_name}",
            "status": "pass",
            "details": f"相对漂移 {relative_drift*100:.2f}% 良好 (drift={drift:.4g}, avg={avg:.4g})"
        }


def run_checks(parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Run reliability/physics checks on parsed series.

    智能检查策略（支持 LLM 增强识别）：
    1. 根据 column_types（可能来自 LLM 或规则）自动识别列的语义
    2. 对 'loss' 类型检查递减趋势
    3. 对 'accuracy' 类型检查递增趋势和范围
    4. 对 'conserved' 类型检查守恒性（低漂移）
    5. 对所有类型检查 NaN/Inf
    """
    checks: List[Dict[str, Any]] = []

    series: Dict[str, List[float]] = parsed.get("series", {})
    column_types: Dict[str, str] = parsed.get("column_types", {})
    llm_used = parsed.get("llm_used", False)
    
    # 添加识别方法的元信息
    if llm_used:
        checks.append({
            "id": "identification_method",
            "name": "列类型识别方法",
            "status": "info",
            "details": "使用 LLM 智能识别（更准确）"
        })

    if not series:
        checks.append({"id": "no_series", "name": "未检测到输入序列数据", "status": "fail", "details": "未找到可分析的 .csv 或 .log 数据文件"})
        return checks

    # 1. Generic NaN/inf detection
    total_points = 0
    nan_inf_points = 0
    for name, arr in series.items():
        for v in arr:
            total_points += 1
            if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
                nan_inf_points += 1
    if total_points == 0:
        checks.append({"id": "empty_series", "name": "数据序列为空", "status": "fail", "details": "没有数值点"})
        return checks
    frac_bad = nan_inf_points / total_points
    if frac_bad > 0.1:
        checks.append({"id": "nan_inf_fraction", "name": "NaN/Inf 比例", "status": "fail", "details": f"数据中 {nan_inf_points}/{total_points} 个点为 NaN/Inf"})
    elif frac_bad > 0:
        checks.append({"id": "nan_inf_fraction", "name": "NaN/Inf 比例", "status": "warn", "details": f"数据中 {nan_inf_points}/{total_points} 个点为 NaN/Inf"})
    else:
        checks.append({"id": "nan_inf_fraction", "name": "NaN/Inf 比例", "status": "pass"})

    # 2. 智能收敛性检查：基于动态识别的列类型
    loss_candidates = [name for name, ctype in column_types.items() if ctype == 'loss']
    accuracy_candidates = [name for name, ctype in column_types.items() if ctype == 'accuracy']
    conserved_candidates = [name for name, ctype in column_types.items() if ctype == 'conserved']
    
    # 检查 loss 类型列（应递减）
    for candidate_name in loss_candidates:
        candidate = series.get(candidate_name, [])
        check_result = check_convergence(candidate_name, candidate, expected_trend="decrease")
        check_result["name"] += " (loss类型)"
        checks.append(check_result)
    
    # 检查 accuracy 类型列（应递增）
    for candidate_name in accuracy_candidates:
        candidate = series.get(candidate_name, [])
        check_result = check_convergence(candidate_name, candidate, expected_trend="increase")
        check_result["name"] += " (accuracy类型)"
        checks.append(check_result)
        
        # 检查范围合理性（accuracy应在0-1之间）
        clean = [v for v in candidate if not math.isnan(v)]
        if clean and (max(clean) > 1.1 or min(clean) < -0.1):
            checks.append({
                "id": f"range_{candidate_name}",
                "name": f"范围检查 - {candidate_name}",
                "status": "warn",
                "details": f"数值范围 [{min(clean):.3f}, {max(clean):.3f}] 超出预期 [0, 1]"
            })
    
    # 检查守恒量（使用独立函数）
    for candidate_name in conserved_candidates:
        candidate = series.get(candidate_name, [])
        check_result = check_conservation(candidate_name, candidate)
        checks.append(check_result)
    
    # 如果没有识别出任何有意义的列类型，使用通用趋势分析
    if not loss_candidates and not accuracy_candidates and not conserved_candidates:
        # 选择最长序列或第一个非时间类型的列
        non_time_series = {k: v for k, v in series.items() 
                          if column_types.get(k, 'unknown') not in ['time']}
        if non_time_series:
            candidate_name = max(non_time_series.keys(), key=lambda k: len(non_time_series[k]))
            candidate = series.get(candidate_name, [])
            clean = [v for v in candidate if not math.isnan(v)]
            
            if len(clean) >= 5:
                n = len(clean)
                k = max(1, n // 10)
                start_avg = statistics.mean(clean[:k])
                end_avg = statistics.mean(clean[-k:])
                change_rate = ((end_avg - start_avg) / start_avg * 100) if start_avg != 0 else 0
                
                checks.append({
                    "id": "generic_trend",
                    "name": f"趋势检查 - {candidate_name} (通用分析)",
                    "status": "info",
                    "details": f"从 {start_avg:.4g} 变化到 {end_avg:.4g} (变化率: {change_rate:.1f}%)"
                })

    return checks


def make_bar_svg(labels: List[str], values: List[int]) -> str:
    """柱状图生成（使用新的 visualizer 模块）"""
    if VISUALIZER_AVAILABLE:
        viz = DataVisualizer()
        return viz.create_chart(
            chart_type="bar",
            data={"labels": labels, "values": values},
            output_format="svg"
        )
    else:
        # Fallback: legacy inline SVG generation
        width = 600
        bar_height = 24
        gap = 6
        height = (bar_height + gap) * max(1, len(labels)) + 40
        maxv = max(1, max(values) if values else 1)
        scale = (width - 140) / maxv

        parts: List[str] = []
        parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">')
        parts.append('<style>text{font-family:Arial;font-size:12px;}</style>')
        y = 20
        for i, lab in enumerate(labels):
            val = values[i]
            w = int(round(val * scale))
            parts.append(f'<text x="10" y="{y + 14}">{lab}</text>')
            parts.append(f'<rect x="120" y="{y}" width="{w}" height="{bar_height}" fill="#4c78a8"></rect>')
            parts.append(f'<text x="{120 + w + 6}" y="{y + 14}">{val}</text>')
            y += bar_height + gap
        parts.append('</svg>')
        return "\n".join(parts)


def make_line_svg(x: List[float], y: List[float], title: str = "") -> str:
    """折线图生成（使用新的 visualizer 模块）"""
    if VISUALIZER_AVAILABLE:
        viz = DataVisualizer()
        return viz.create_chart(
            chart_type="line",
            data={"x": x, "y": y},
            output_format="svg",
            title=title
        )
    else:
        # Fallback: legacy inline SVG generation
        width = 700
        height = 300
        pad_left = 50
        pad_bottom = 40
        pad_top = 20
        plot_w = width - pad_left - 20
        plot_h = height - pad_top - pad_bottom

        # clean data
        pts = [(xi, yi) for xi, yi in zip(x, y) if not (math.isnan(yi) or math.isinf(yi))]
        if not pts:
            return f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}'></svg>"
        xs, ys = zip(*pts)
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
        if maxx == minx:
            maxx = minx + 1
        if maxy == miny:
            maxy = miny + 1

        def sx(v):
            return pad_left + int((v - minx) / (maxx - minx) * plot_w)

        def sy(v):
            return pad_top + plot_h - int((v - miny) / (maxy - miny) * plot_h)

        parts = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}'>"]
        parts.append("<style>text{font-family:Arial;font-size:12px;}</style>")
        # title
        if title:
            parts.append(f"<text x='{width//2}' y='16' text-anchor='middle'>{title}</text>")

        # axes
        parts.append(f"<line x1='{pad_left}' y1='{pad_top}' x2='{pad_left}' y2='{pad_top+plot_h}' stroke='#333'/>")
        parts.append(f"<line x1='{pad_left}' y1='{pad_top+plot_h}' x2='{pad_left+plot_w}' y2='{pad_top+plot_h}' stroke='#333'/>")

        # polyline
        pts_attr = " ".join(f"{sx(xi)},{sy(yi)}" for xi, yi in pts)
        parts.append(f"<polyline fill='none' stroke='#ff7f0e' stroke-width='2' points='{pts_attr}' />")

        parts.append("</svg>")
        return "\n".join(parts)


def generate_visuals(parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
    """智能生成可视化，根据识别的列类型选择合适的绘图对象"""
    visuals: List[Dict[str, Any]] = []
    series: Dict[str, List[float]] = parsed.get("series", {})
    column_types: Dict[str, str] = parsed.get("column_types", {})
    
    if not series:
        return visuals

    # 优先级：loss > accuracy > conserved > 最长序列
    priority_order = ['loss', 'accuracy', 'conserved', 'physical', 'unknown']
    candidates_by_type = {ptype: [] for ptype in priority_order}
    
    for name, ctype in column_types.items():
        if ctype in candidates_by_type:
            candidates_by_type[ctype].append(name)
    
    # 选择第一个有数据的优先级类型
    selected_candidates = []
    for ptype in priority_order:
        if candidates_by_type[ptype]:
            selected_candidates = candidates_by_type[ptype][:2]  # 最多选2个
            break
    
    # 如果没有找到，使用最长的两个序列
    if not selected_candidates:
        sorted_series = sorted(series.items(), key=lambda x: len(x[1]), reverse=True)
        selected_candidates = [name for name, _ in sorted_series[:2]]
    
    # 为每个候选列生成可视化
    for idx, cand in enumerate(selected_candidates):
        y = series.get(cand, [])
        if not y:
            continue
        x = list(range(len(y)))
        ctype = column_types.get(cand, 'unknown')
        
        # 根据类型调整标题
        type_labels = {
            'loss': '损失曲线',
            'accuracy': '准确率曲线',
            'conserved': '守恒量变化',
            'physical': '物理量变化',
            'time': '时间序列',
            'unknown': '数据趋势'
        }
        title_suffix = type_labels.get(ctype, '趋势')
        
        svg = make_line_svg(x, y, title=f"{cand} ({title_suffix})")
        svg_b64 = "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")
        visuals.append({
            "id": f"plot_{idx}_{ctype}",
            "type": "line",
            "description": f"{cand} {title_suffix} (自动识别类型: {ctype})",
            "data": {"x": x, "y": y},
            "image_base64": svg_b64,
            "detected_type": ctype,
        })
    
    return visuals


def build_report(input_path: str, parsed: Dict[str, Any], checks: List[Dict[str, Any]], visuals: List[Dict[str, Any]]) -> Dict[str, Any]:
    column_types = parsed.get("column_types", {})
    # 使用新加坡时间 (UTC+8)
    singapore_time = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    return {
        "input": input_path,
        "metadata": {
            "parsed_series_count": len(parsed.get("series", {})),
            "llm_identification_used": parsed.get("llm_used", False),
            "detected_column_types": column_types,
            "type_summary": {
                "loss_columns": [k for k, v in column_types.items() if v == 'loss'],
                "accuracy_columns": [k for k, v in column_types.items() if v == 'accuracy'],
                "conserved_columns": [k for k, v in column_types.items() if v == 'conserved'],
                "unknown_columns": [k for k, v in column_types.items() if v == 'unknown'],
            }
        },
        "checks": checks,
        "visuals": visuals,
        "generated_at": singapore_time.strftime("%Y-%m-%d %H:%M:%S SGT"),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Data Agent: 解析、校验、可视化并输出 JSON 与图像文件（支持 LLM 智能识别）")
    parser.add_argument("-i", "--input", nargs='*', help="输入数据文件路径（支持 .csv 和 .log），可传入多个")
    parser.add_argument("-o", "--output", required=True, help="主要输出 JSON 路径 (将写入报告)")
    parser.add_argument("--dockerfile", help="Dockerfile 路径：构建镜像并运行，自动收集容器输出")
    parser.add_argument("--docker-image", help="已存在的 Docker 镜像 tag：直接运行并收集容器输出")
    parser.add_argument("--container-output-path", default="/output", help="容器内输出路径（默认 /output）")
    parser.add_argument("--repo-root", required=False, help="仓库根路径，用于回滚（可选）")
    parser.add_argument("--out-dir", required=False, help="基目录：为每次运行创建子目录以保存 report.json 与图像文件 (默认 backend/experiments/agents/data_agent/outputs)")
    parser.add_argument("--no-llm", action="store_true", help="禁用 LLM 智能识别，仅使用规则匹配")
    args = parser.parse_args(argv)

    input_paths = args.input if args.input else []

    # If Dockerfile or docker-image provided, run Docker and collect outputs
    if args.dockerfile or args.docker_image:
        temp_output_dir = tempfile.mkdtemp(prefix="docker_data_agent_")
        image_tag = args.docker_image

        if args.dockerfile:
            # Build image
            dockerfile_abs = os.path.abspath(args.dockerfile)
            image_tag = f"data_agent_build_{uuid.uuid4().hex[:8]}"
            print(f"Building Docker image from {dockerfile_abs} with tag {image_tag}...")
            if not build_docker_image(dockerfile_abs, image_tag):
                print("Docker build failed.")
                return 1
            print(f"Build succeeded: {image_tag}")

        # Run container
        print(f"Running Docker container {image_tag}, mounting {temp_output_dir} to {args.container_output_path}...")
        if not run_docker_container(image_tag, temp_output_dir, args.container_output_path):
            print("Docker run failed or exited non-zero.")
            # Attempt to collect partial outputs if any

        # Collect CSV/log files from temp_output_dir
        collected = collect_files_from_dir(temp_output_dir, extensions=(".csv", ".log"))
        print(f"Collected {len(collected)} files from container output: {collected}")
        input_paths.extend(collected)

    if not input_paths:
        print("Error: No input files provided. Use -i or --dockerfile/--docker-image.")
        return 1

    # 解析文件，根据参数决定是否使用 LLM
    use_llm = not args.no_llm
    parsed = parse_input_files(input_paths, use_llm=use_llm)
    
    checks = run_checks(parsed)
    visuals = generate_visuals(parsed)

    # If any critical failure (status == fail) then trigger rollback
    critical = [c for c in checks if c.get("status") == "fail"]
    actions = {"rollback_triggered": False, "rollback_details": None}
    if critical and args.repo_root:
        ok = rollback_last_commit(args.repo_root, steps=1)
        actions["rollback_triggered"] = ok
        actions["rollback_details"] = {"failed_checks": [c["id"] for c in critical]}

    report = build_report(
        ",".join(input_paths), parsed, checks, visuals
    )
    report["actions"] = actions

    # Determine base output folder for this run
    base_out = args.out_dir if args.out_dir else os.path.join(os.path.dirname(__file__), "outputs")
    os.makedirs(base_out, exist_ok=True)
    # 使用新加坡时间 (UTC+8) 生成时间戳
    singapore_time = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    ts = singapore_time.strftime("%Y%m%d_%H%M%S")
    run_id = f"run_{ts}_{str(uuid.uuid4())[:8]}"
    run_dir = os.path.join(base_out, run_id)
    os.makedirs(run_dir, exist_ok=True)

    # Save visuals as separate files and rewrite report visuals to reference files
    visuals_dir = os.path.join(run_dir, "visuals")
    os.makedirs(visuals_dir, exist_ok=True)
    saved_visuals = []
    for idx, v in enumerate(report.get("visuals", [])):
        img_b64 = v.get("image_base64")
        img_path = None
        if img_b64:
            # support data:image/svg+xml;base64, and data:image/png;base64,
            if img_b64.startswith("data:image/svg+xml;base64,"):
                payload = img_b64.split(",", 1)[1]
                data = base64.b64decode(payload)
                img_name = f"{idx:02d}_{v.get('id','visual')}.svg"
                img_path = os.path.join(visuals_dir, img_name)
                with open(img_path, "wb") as f:
                    f.write(data)
            elif img_b64.startswith("data:image/png;base64,"):
                payload = img_b64.split(",", 1)[1]
                data = base64.b64decode(payload)
                img_name = f"{idx:02d}_{v.get('id','visual')}.png"
                img_path = os.path.join(visuals_dir, img_name)
                with open(img_path, "wb") as f:
                    f.write(data)
            else:
                # unknown prefix: try decoding whole string
                try:
                    data = base64.b64decode(img_b64)
                    img_name = f"{idx:02d}_{v.get('id','visual')}.bin"
                    img_path = os.path.join(visuals_dir, img_name)
                    with open(img_path, "wb") as f:
                        f.write(data)
                except Exception:
                    img_path = None

        v_ref = dict(v)
        if img_path:
            v_ref.pop("image_base64", None)
            v_ref["image_file"] = os.path.relpath(img_path, run_dir)
        saved_visuals.append(v_ref)

    report["visuals"] = saved_visuals

    # write validated report JSON
    out_report_path = os.path.join(run_dir, os.path.basename(args.output))
    with open(out_report_path, "w", encoding="utf-8") as fo:
        json.dump(report, fo, ensure_ascii=False, indent=2)

    # also copy to args.output location requested (optional override)
    try:
        out_copy_dir = os.path.dirname(os.path.abspath(args.output))
        if out_copy_dir and not os.path.exists(out_copy_dir):
            os.makedirs(out_copy_dir, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as fo2:
            json.dump(report, fo2, ensure_ascii=False, indent=2)
    except Exception:
        pass

    print(f"Report written to {out_report_path}")
    print(f"Run outputs saved in {run_dir}")
    if parsed.get("llm_used"):
        print("✓ LLM 智能识别已启用")
    if critical:
        print("Critical checks failed:", [c["id"] for c in critical])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
