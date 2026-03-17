import json
from typing import Any, Callable, Dict, Optional

import json_repair

from shared.constants import DECISION_AGENT_MAX_REPAIR_ATTEMPTS, TEMP_DETERMINISTIC, TEMP_RETRY
from shared.llm_client import chat_completion, merge_phase_config
from shared.structured_output import generate_with_repair


_DEFAULT_IMMUTABLE_ITEMS = [
    "Do not change the core research question or final objective.",
    "Do not remove required datasets, key experiment objects, or mandatory comparison targets.",
    "Do not downgrade quantitative final requirements into purely narrative claims.",
    "Do not weaken final evidence requirements needed to support the research conclusion.",
    "Do not bypass reproducibility and traceability requirements for final claims.",
]

def _build_contract_messages(packet: Dict[str, Any]) -> list[dict]:
    immutable_items = packet.get("immutableItems") or _DEFAULT_IMMUTABLE_ITEMS
    system_prompt = (
        "You are Step-B Contract Review Agent in a task retry pipeline. "
        "Your only job is to decide whether validation criteria should be adjusted to reduce useless retry loops "
        "WITHOUT changing immutable research goals. "
        "Always return strict JSON only."
    )
    user_prompt = (
        "Review the packet and return JSON with keys: "
        "shouldAdjust (bool), immutableImpacted (bool), reasoning (string), "
        "proposedValidationCriteria (array of strings), patchSummary (string), "
        "equivalenceCheckRequired (bool), equivalenceCheckHint (string).\n\n"
        "Rules:\n"
        "1) You may adjust only mutable step-level validation checks.\n"
        "2) If any immutable item is impacted, set immutableImpacted=true and shouldAdjust=false.\n"
        "3) Keep final research conclusion standards intact.\n\n"
        "Equivalent-format rule (important):\n"
        "- If failure is caused by representational differences that are losslessly or tolerantly convertible "
        "(for example XML<->JSON, matrix<->CSV), you MAY adjust criteria to accept equivalent representation.\n"
        "- But you MUST require verifiable equivalence evidence in the adjusted criteria: "
        "conversion method, compared source/target artifacts, and concrete pass/fail checks.\n"
        "- If equivalence cannot be verified, do NOT relax criteria.\n\n"
        f"Immutable items:\n{json.dumps(immutable_items, ensure_ascii=False, indent=2)}\n\n"
        f"Packet:\n```json\n{json.dumps(packet, ensure_ascii=False, indent=2)}\n```"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _parse_contract_review(raw: str) -> Dict[str, Any]:
    cleaned = (raw or "").strip()
    if not cleaned:
        raise ValueError("Contract review agent returned empty response")
    parsed = json_repair.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("Contract review agent must return a JSON object")

    should_adjust = bool(parsed.get("shouldAdjust"))
    immutable_impacted = bool(parsed.get("immutableImpacted"))
    criteria = parsed.get("proposedValidationCriteria") or []
    if not isinstance(criteria, list):
        criteria = []
    criteria = [str(item).strip() for item in criteria if str(item).strip()]

    if immutable_impacted:
        should_adjust = False

    return {
        "shouldAdjust": should_adjust,
        "immutableImpacted": immutable_impacted,
        "reasoning": str(parsed.get("reasoning") or "").strip(),
        "proposedValidationCriteria": criteria,
        "patchSummary": str(parsed.get("patchSummary") or "").strip(),
        "equivalenceCheckRequired": bool(parsed.get("equivalenceCheckRequired")),
        "equivalenceCheckHint": str(parsed.get("equivalenceCheckHint") or "").strip(),
        "source": "step-b-agent",
    }


async def review_contract_adjustment(
    packet: Dict[str, Any],
    *,
    api_config: Optional[Dict[str, Any]] = None,
    abort_event: Optional[Any] = None,
    on_thinking: Optional[Callable[..., Any]] = None,
) -> Dict[str, Any]:
    messages = _build_contract_messages(packet)
    cfg = merge_phase_config(api_config or {}, "validate")
    stream = on_thinking is not None

    def _on_chunk(chunk: str):
        if on_thinking and chunk:
            task_id = (packet.get("task") or {}).get("taskId")
            return on_thinking(chunk, task_id=task_id, operation="Step-B")

    async def _model_call(message_list: list[dict], temperature: float) -> str:
        raw = await chat_completion(
            message_list,
            cfg,
            on_chunk=_on_chunk if stream else None,
            abort_event=abort_event,
            stream=stream,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        return raw if isinstance(raw, str) else (raw.get("content") or "")

    temps = [TEMP_DETERMINISTIC] + [TEMP_RETRY] * max(0, DECISION_AGENT_MAX_REPAIR_ATTEMPTS - 1)
    parsed, _raw = await generate_with_repair(
        base_messages=messages,
        model_call=_model_call,
        parse_fn=_parse_contract_review,
        temperatures=temps,
    )
    return parsed
