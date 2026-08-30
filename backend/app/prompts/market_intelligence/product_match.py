import json


PRODUCT_MATCH_PROMPT_VERSION = "market-metric-product-match-v1"

PRODUCT_MATCH_SYSTEM_PROMPT = """You determine whether two product descriptions refer to the same product type.
Category names are context only and may differ completely. Decide from the product meaning.
Return same_product only when the two descriptions identify the same sellable product type.
Return different_product when they identify different products. Return uncertain when evidence is insufficient.
Provide concise Chinese reasoning and normalized product names. Output only the requested JSON object."""


def build_product_match_prompt(payload: dict[str, str]) -> tuple[str, str]:
    return (
        PRODUCT_MATCH_SYSTEM_PROMPT,
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
    )


__all__ = ["PRODUCT_MATCH_PROMPT_VERSION", "build_product_match_prompt"]
