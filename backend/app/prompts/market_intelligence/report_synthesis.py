import json
from typing import Any

# Replace these constants directly when the report prompt changes.
REPORT_SYNTHESIS_SYSTEM_PROMPT = (
    "You generate evidence-bound e-commerce market intelligence reports. "
    "Use only the supplied structured data. Separate facts, inferences, "
    "opportunities, risks, and actions. Never invent numbers or evidence IDs. "
    "Facts, inferences, opportunities, and risks must cite allowed evidence IDs. "
    "Every item in facts, inferences, opportunity_signals, and risk_signals must "
    "contain at least one evidence_id from allowed_evidence_ids. Omit any unsupported statement. "
    "Use INSUFFICIENT_DATA when critical evidence or cost data is missing. "
    "Preserve allowed limitation IDs exactly and return JSON only."
    " Write all user-facing text fields, including summaries, facts, inferences,"
    " opportunities, risks, and suggested actions, in Simplified Chinese."
    " Keep schema field names, enum values, evidence IDs, and limitation IDs unchanged."
)
REPORT_SYNTHESIS_USER_PROMPT = "Generate a report from this JSON payload:"


def build_report_synthesis_prompt(payload: dict[str, Any]) -> tuple[str, str]:
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return REPORT_SYNTHESIS_SYSTEM_PROMPT, f"{REPORT_SYNTHESIS_USER_PROMPT}\n{payload_json}"
