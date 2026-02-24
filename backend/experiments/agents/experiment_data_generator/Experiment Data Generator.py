import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from google import genai

def generate_experiment_json(idea_json_str):
    # 1. 解析上游输入的 JSON
    idea_data = json.loads(idea_json_str)
    
    # 2. 构建面向大模型的指令 (Prompt)
    prompt = f"""
    你是一个深度学习实验室的 AI 研究助理。请根据以下论文 Idea JSON，生成一份详细的实验设计 JSON。
    
    【输入 Idea 核心内容】:
    - 标题: {idea_data['idea']['title']}
    - 创新点: {idea_data['idea']['innovation']}
    - 基准模型: {idea_data['idea']['baselines']}
    - 预期指标: {idea_data['idea']['success_metric']}
    
    【输出要求】:
    1. 必须包含 'Datasets'：根据时间序列领域惯例，推荐 5 个常用数据集（如 ETT, Traffic, Electricity）。
    2. 必须包含 'Experimental_Group'：即本项目的完整模型配置。
    3. 必须包含 'Ablation_Groups'：针对 4 个创新点分别设计“剔除变量”。
    4. 必须包含 'Variables'：明确自变量（预测长度 96, 192, 336, 720）和因变量。
    5. 必须包含 'Expected_Output_Headers'：数组形式，给出结果数据表的列名。
    6. 格式：严格返回 JSON，不要有任何正文描述。
    """

    # 3. 调用大模型（Gemini API）
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in environment variables.")

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=prompt,
        config={"response_mime_type": "application/json"}
    )

    return response.text


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