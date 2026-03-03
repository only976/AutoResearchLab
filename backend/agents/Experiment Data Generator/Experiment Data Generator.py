import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

# Add parent project directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from backend.agents.data_agent import DataAgent


def generate_experiment_json(idea_json_str):
    """
    Wrapper function that delegates to DataAgent.generate_experiment_design()
    Maintains compatibility with existing code.
    Input/Output completely consistent with original implementation.
    """
    agent = DataAgent()
    return agent.generate_experiment_design(idea_json_str)


def _read_idea_json(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def main():
    # 默认读取仓库根目录下的 report_20260220_101714.json
    default_path = "report_20260220_101714.json"
    idea_json_input = _read_idea_json(default_path)
    result_json = generate_experiment_json(idea_json_input)

    # 输出到当前脚本目录下的 output 文件夹
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(script_dir, "output")
    os.makedirs(output_dir, exist_ok=True)

    sgt_time = datetime.now(ZoneInfo("Asia/Singapore")).strftime("%Y%m%d_%H%M%S")
    output_filename = f"experiment_design_{sgt_time}.json"
    output_path = os.path.join(output_dir, output_filename)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(result_json)

    print(f"Saved output to: {output_path}")


if __name__ == "__main__":
    main()
