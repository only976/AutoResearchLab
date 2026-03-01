import json
from typing import Any, Dict

def parse_json_text(text: str) -> Dict[str, Any]:
    try:
        if isinstance(text, dict):
            return text
        # Try to find JSON object if mixed with text
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            json_str = text[start : end + 1]
            return json.loads(json_str)
        return json.loads(text)
    except Exception:
        return {"raw": text, "error": "Failed to parse JSON"}
