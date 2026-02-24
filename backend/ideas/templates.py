from typing import Dict, Any, List

# Template Definitions

HEILMEIER_TEMPLATE = {
    "template_id": "heilmeier_catechism",
    "description": "Best for engineering projects, applied research, and system building. Focuses on value proposition, risks, and execution plan.",
    "schema": {
        "idea_name": "Short identifier",
        "title": "Project Title",
        "template_type": "heilmeier_catechism",
        "content": {
            "problem_statement": "What specific problem are you solving? articulate the objectives with high precision and no jargon. Explain WHY this is a hard problem.",
            "state_of_the_art": "Detailed analysis of current approaches. Cite specific types of methods (e.g., 'MCTS variants', 'AlphaZero-style learning'). Explain exactly WHERE they fail or fall short.",
            "key_insight": "The core technical innovation. What is the 'Secret Sauce'? How does your approach structurally differ from existing ones? Be specific (e.g., 'Replacing the scalar reward with a vector-based ...').",
            "impact": "If successful, what is the concrete impact? (e.g., 'Reduces inference time by 40%', 'Enables transfer learning to...').",
            "technical_plan": ["Phase 1: Detailed design of [Component X]...", "Phase 2: Implementation of [Algorithm Y]...", "Phase 3: Evaluation on [Dataset Z]..."],
            "risks_and_mitigations": [
                {"risk": "Specific technical risk (e.g., 'Gradient variance too high')", "mitigation": "Concrete solution (e.g., 'Use baseline subtraction')"}
            ]
        }
    }
}

SCIENTIFIC_DISCOVERY_TEMPLATE = {
    "template_id": "scientific_discovery",
    "description": "Best for theoretical AI research, algorithm development, and empirical studies (e.g., NeurIPS/ICLR style). Focuses on hypothesis, methodology, and experiments.",
    "schema": {
        "idea_name": "Short identifier",
        "title": "Paper Title",
        "template_type": "scientific_discovery",
        "content": {
            "research_question": "The precise scientific question. Must be falsifiable and non-trivial.",
            "hypothesis": "A formal hypothesis statement (e.g., 'Mechanism X improves generalization by Y because...').",
            "related_work_gap": "Critical analysis of the literature. Identify the specific 'Gap' that this work fills.",
            "proposed_method": {
                "concept": "The core theoretical concept or mathematical formulation.",
                "details": "Step-by-step algorithmic details, loss functions, or architecture changes."
            },
            "experimental_design": {
                "datasets": ["Specific Dataset (e.g., ImageNet, Mujoco)"],
                "baselines": ["SOTA Baseline 1", "SOTA Baseline 2"],
                "metrics": ["Primary Metric (e.g., Accuracy)", "Secondary Metric (e.g., Sample Efficiency)"]
            },
            "expected_results": "What outcomes would validate the hypothesis? What would invalidate it?"
        }
    }
}

SYSTEM_OPTIMIZATION_TEMPLATE = {
    "template_id": "system_optimization",
    "description": "Best for performance tuning, resource efficiency, and infrastructure projects. Focuses on bottlenecks, optimization techniques, and benchmarks.",
    "schema": {
        "idea_name": "Short identifier",
        "title": "Optimization Title",
        "template_type": "system_optimization",
        "content": {
            "target_system": "The specific system, component, or pipeline being optimized (e.g., 'Transformer Attention Mechanism').",
            "bottleneck_analysis": "Quantitative or qualitative analysis of the current bottleneck (e.g., 'Memory bandwidth limited during decoding').",
            "optimization_strategy": "The proposed technical solution. Be specific (e.g., 'Sparse attention with low-rank approximation').",
            "implementation_steps": ["Step 1: Profiling...", "Step 2: Prototype implementation...", "Step 3: Integration..."],
            "evaluation_metrics": ["Latency (ms)", "Throughput (tokens/sec)", "Peak Memory (GB)"],
            "success_criteria": "Specific, measurable goals (e.g., 'Maintain 99% accuracy while reducing memory by 50%')."
        }
    }
}

ALL_TEMPLATES = [HEILMEIER_TEMPLATE, SCIENTIFIC_DISCOVERY_TEMPLATE, SYSTEM_OPTIMIZATION_TEMPLATE]

RESEARCH_TOPIC_SCHEMA = {
    "title": "A concise, academic title for the research direction",
    "keywords": ["Keyword1", "Keyword2", "Keyword3"],
    "tldr": "A one-sentence hook (e.g., 'If X happens, will Y still work?')",
    "abstract": "A 150-word abstract describing the specific problem, proposed methodology, and expected outcome. This should serve as the 'Scope' for further ideation.",
    "refinement_reason": "Why was this topic refined? (e.g., 'Original input was too broad', 'Original input lacked technical specificity')"
}

def get_template_descriptions() -> str:
    """Returns a formatted string describing available templates AND their schemas for the LLM."""
    descriptions = []
    for t in ALL_TEMPLATES:
        schema_str = str(t['schema'])
        descriptions.append(f"- ID: {t['template_id']}\n  Description: {t['description']}\n  Schema: {schema_str}")
    return "\n\n".join(descriptions)

def get_template_schema(template_id: str) -> Dict[str, Any]:
    """Returns the schema for a specific template ID."""
    for t in ALL_TEMPLATES:
        if t['template_id'] == template_id:
            return t['schema']
    return SCIENTIFIC_DISCOVERY_TEMPLATE['schema'] # Default
