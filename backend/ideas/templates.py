from typing import Dict, Any, List

# 1. 定义核心 JSON 输出模板
ADVANCED_REPORT_SCHEMA = """
{
  "title": "研究标题",
  "gap": "现有研究不足及 gap（需带 [Source ID: X] 引用）",
  "hypothesis": "你的核心假设",
  "innovation": "核心创新点（需带 [Source ID: X] 引用）",
  "topology": "模型拓扑结构流程",
  "components": ["关键组件1", "关键组件2"],
  "success_metric": ["量化指标1", "量化指标2"],
  "deliverable": "预期交付产出",
  "baselines": ["对比基准列表"],
  "cited_source_ids": [0, 1],
  "ai_evaluation": {
      "scores": { 
          "novelty": 8.5, 
          "feasibility": 9.0, 
          "research_value": 8.8, 
          "writing": 9.2 
      },
      "feedback": "评价反馈"
  }
}
"""

# 2. 定义主题精炼阶段的 Schema
RESEARCH_TOPIC_SCHEMA = {
    "is_broad": "boolean",
    "analysis": "string",
    "topics": [
        {
            "title": "A concise, academic title",
            "keywords": ["Keyword1", "Keyword2"],
            "tldr": "A one-sentence hook",
            "abstract": "A 150-word abstract describing the problem and methodology",
            "refinement_reason": "Why was this topic refined?"
        }
    ]
}

def get_advanced_instruction(topic: str, vram: int, level: str, lang: str) -> str:
    """
    动态生成系统提示词。修复了由于粘贴导致的非法换行问题。
    """
    # 使用三引号保持格式整洁，注意不要在单词中间换行
    return f"""
You are a Senior Academic Reviewer & Research Architect.

CONTEXT:
- Primary Topic: {topic}
- Hardware Constraints: {vram} GB VRAM
- Academic Target: {level} level (e.g., Master / PhD)
- Output Language: {lang}

MANDATORY RULES:
1. GROUNDING: You MUST use [Source ID: X] tags for every technical claim, innovation, or gap.
2. SCORING: All scores in 'ai_evaluation' must be FLOAT between 1.0 and 10.0.
3. REALISM: Scores must reflect the actual quality of the idea. DO NOT copy example values.
4. FORMAT: Output MUST be a single, valid JSON object matching the schema below.

OUTPUT JSON SCHEMA:
{ADVANCED_REPORT_SCHEMA}
"""

def get_template_descriptions() -> str:
    """兼容旧接口名称"""
    return "Advanced RAG Research Template: Focuses on literature-grounded innovation and hardware-aware feasibility."