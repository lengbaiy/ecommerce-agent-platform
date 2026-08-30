import json
from typing import Any

# Replace these constants directly when the review prompt changes.
REVIEW_ANALYSIS_SYSTEM_PROMPT = (
    "You analyze e-commerce reviews. Analyze each review independently. "
    "Preserve every review_id exactly. Set sentiment to positive, neutral, "
    "or negative. Extract concise, reusable semantic labels for themes, "
    "pain_points, and unmet_needs. Use an empty list when the review does "
    "not support a label. Reuse the same label for semantically equivalent "
    "concepts. Do not infer unsupported facts. Return JSON only."
)
REVIEW_ANALYSIS_USER_PROMPT = "Analyze all reviews in this JSON array:"


def build_review_analysis_prompt(
    payload: list[dict[str, Any]],
    *,
    output_language: str,
) -> tuple[str, str]:
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    system_prompt = f"{REVIEW_ANALYSIS_SYSTEM_PROMPT} Write all labels in {output_language}."
    return system_prompt, f"{REVIEW_ANALYSIS_USER_PROMPT}\n{payload_json}"
