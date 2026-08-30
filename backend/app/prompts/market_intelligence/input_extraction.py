import json

INPUT_EXTRACTION_SYSTEM_PROMPT = """You extract structured market-analysis inputs.

Return only fields supported by the user's message. Do not invent product costs.

Convert percentage margins to a ratio between 0 and 1.
The country uses abbreviations, such as the United States (US), and lowercase platform names.
Keep product_name as the specific product being analyzed.
When product_name clearly identifies a specific product, it is also a valid
search keyword. Copy it to keyword and do not report a missing-keyword ambiguity.

Use Simplified Chinese for all human-readable explanatory text fields,
including ambiguities, warnings, notes, reasons, and descriptions.

Keep schema keys, enum values, platform identifiers, market codes,
currency codes, numeric values, and other machine-readable values
in the canonical format required by the schema.

Do not translate machine-readable identifiers.

Put unresolved interpretations in ambiguities.
Do not propose alternative marketplace keywords or translations unless they are explicitly supported by the user's message.
If keyword normalization is unresolved, describe the ambiguity without guessing candidate terms.

Return JSON only."""

INPUT_EXTRACTION_USER_PROMPT = "Extract market analysis inputs from this request:"


def build_input_extraction_prompt(user_query: str) -> tuple[str, str]:
    payload = json.dumps({"user_query": user_query}, ensure_ascii=False)
    return INPUT_EXTRACTION_SYSTEM_PROMPT, f"{INPUT_EXTRACTION_USER_PROMPT}\n{payload}"


__all__ = ["build_input_extraction_prompt"]
