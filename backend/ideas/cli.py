import os, sys, json, datetime
from dotenv import load_dotenv

# 路径自修复逻辑
current_file_path = os.path.abspath(__file__)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file_path)))
if project_root not in sys.path: sys.path.insert(0, project_root)

from backend.ideas.agent import ResearchIdeaEngine
from backend.config import LLM_MODEL, LLM_API_BASE, LLM_API_KEY

def main():
    load_dotenv(os.path.join(project_root, ".env"))
    output_dir = os.path.join(project_root, "output")
    os.makedirs(output_dir, exist_ok=True)

    db_path = os.path.join(project_root, "qdrant_fulltext_db")

    engine = ResearchIdeaEngine(
        {"model_name": LLM_MODEL, "api_base": LLM_API_BASE, "api_key": os.getenv("GOOGLE_API_KEY") or LLM_API_KEY},
        db_path=db_path
    )

    input_json = {
        "broad_topic": "Transformer 在时间序列预测中的轻量化改进",
        "research_style": "novelty_seeking",
        "depth_level": "master",
        "language": "zh",
        "compute": "cuda",
        "vram_gb": 24,
        "max_runtime_minutes": 60,
        "frameworks": ["pytorch", "numpy", "scikit-learn"]
    }

    print(f"🛠️ 正在同步云端数据: {input_json['broad_topic']}...")
    engine.search_and_index_tool(input_json['broad_topic'], limit=20)

    # 【修复重点】：f-string 中的 JSON 必须使用双大括号 {{ }}
    SYSTEM_INSTRUCTION = f"""
    You are a Senior Academic Reviewer. 
    Topic: {input_json['broad_topic']}
    Constraints: {input_json['vram_gb']}GB VRAM, {input_json['depth_level']} level.

    MANDATORY:
    1. Use [Source ID: X] tags for every innovation or gap mentioned.
    2. Output in {input_json['language']}.
    3. JSON format must strictly follow the schema below.
    4. Scoring: All scores in ai_evaluation must be FLOAT between 1.0 and 10.0.
    5、“注意：ai_evaluation 中的分数必须根据你对当前 Idea 的真实评估给出，严禁照抄模板中的示例数值。优秀的 Idea 应该给高分，有缺陷的 Idea 必须如实给低分。”

    OUTPUT JSON FORMAT:
    {{
      "title": "研究标题",
      "gap": "现有研究不足及 gap（需带 Source ID 引用）",
      "hypothesis": "你的核心假设",
      "innovation": "核心创新点（需带 Source ID 引用）",
      "topology": "模型拓扑结构流程",
      "components": ["关键组件1", "关键组件2"],
      "success_metric": ["量化指标1", "量化指标2"],
      "deliverable": "预期交付产出",
      "baselines": ["对比基准列表"],
      "cited_source_ids": [0, 1],
      "ai_evaluation": {{
          "scores": {{ 
              "novelty": 8.5, 
              "feasibility": 9.0, 
              "research_value": 8.8, 
              "writing": 9.2 
          }},
          "feedback": "评价反馈"
      }}
    }}
    """

    print(f"🚀 启动 Agent 生成提案报告...")
    result = engine.run_agent_workflow(input_json['broad_topic'], SYSTEM_INSTRUCTION)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    full_path = os.path.join(output_dir, f"idea_report_{timestamp}.json")
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=4, ensure_ascii=False)

    print("\n" + "=" * 50)
    print(f"✅ 执行成功！")
    print(f"📄 完整报告路径: {full_path}")
    # 打印一下分数，看看是不是 10 分制了
    eval_scores = result.get('ai_evaluation', {}).get('scores', {})
    print(f"⭐ 评分 (10分制): {eval_scores}")
    print(f"📈 最终召回得分: {result.get('recall_metrics', {}).get('recall_score', 0)}")
    print("=" * 50)

if __name__ == "__main__":
    main()
