"""
MAARS 内部可调参数集中定义。
开发者可在此微调 temperature、agent loop 上限、并发数等参数，无需逐文件搜索。
用户侧不暴露这些参数。
"""

import os

# ── LLM Temperature ──────────────────────────────────────────────
# 结构化提取 / 工具调用：低温保证确定性
TEMP_EXTRACT = 0.2
# 通用结构化输出（format spec、quality 评分等）
TEMP_STRUCTURED = 0.2
# Agent loop 工具选择决策
TEMP_AGENT_LOOP = 0.3
# Task execution 生成
TEMP_TASK_EXECUTE = 0.3
# 创意生成（idea refine）
TEMP_CREATIVE = 0.6
# 论文分析
TEMP_ANALYSIS = 0.4
# 重试时提高多样性
TEMP_RETRY = 0.5
# 确定性输出（atomicity 首次、validation）
TEMP_DETERMINISTIC = 0.0

# ── Agent Loop 最大轮数 ──────────────────────────────────────────
# ADK 中每个 event (tool call/response/text) 都计为一轮
# Idea agent workflow 需要 20-30+ events (ListSkills, LoadSkill*N, ExtractKeywords, 
# SearchArxiv, EvaluatePapers, FilterPapers, AnalyzePapers, RefineIdea, ValidateRefinedIdea, FinishIdea)
IDEA_AGENT_MAX_TURNS = 50
PLAN_AGENT_MAX_TURNS = 30
TASK_AGENT_MAX_TURNS = 100
ADK_IDLE_TIMEOUT_SECONDS = int(os.getenv("MAARS_ADK_IDLE_TIMEOUT_SECONDS", "45"))
ADK_TOOL_WAIT_TIMEOUT_SECONDS = int(os.getenv("MAARS_ADK_TOOL_WAIT_TIMEOUT_SECONDS", "900"))
TASK_AGENT_CONTEXT_TARGET_TOKENS = int(os.getenv("MAARS_TASK_AGENT_CONTEXT_TARGET_TOKENS", "20000"))
TASK_AGENT_CONTEXT_HARD_LIMIT_TOKENS = int(os.getenv("MAARS_TASK_AGENT_CONTEXT_HARD_LIMIT_TOKENS", "100000"))

# ── Plan LLM 并发 / 重试 ────────────────────────────────────────
PLAN_MAX_CONCURRENT_CALLS = 10
PLAN_MAX_VALIDATION_RETRIES = 2

# ── Execution Runner ─────────────────────────────────────────────
MAX_FAILURES = 3
MAX_EXECUTION_CONCURRENCY = 7

# ── Mock 模式概率 ────────────────────────────────────────────────
MOCK_EXECUTION_PASS_PROBABILITY = float(os.getenv("MAARS_MOCK_EXECUTION_PASS_PROBABILITY", "0.95"))
MOCK_VALIDATION_PASS_PROBABILITY = float(os.getenv("MAARS_MOCK_VALIDATION_PASS_PROBABILITY", "0.95"))

# ── LLM 超时（秒） ──────────────────────────────────────────────
# 非流式单次调用（含 tool-use）
LLM_REQUEST_TIMEOUT = 120
# 流式每个 chunk 间隔上限
LLM_STREAM_CHUNK_TIMEOUT = 60

# ── Self-Reflection（自迭代） ──────────────────────────────────
REFLECT_MAX_ITERATIONS = 2
REFLECT_QUALITY_THRESHOLD = 70
TEMP_REFLECT = 0.2
TEMP_SKILL_GEN = 0.4

# ── Default Model ────────────────────────────────────────────────
DEFAULT_MODEL = "gemini-2.5-flash"
