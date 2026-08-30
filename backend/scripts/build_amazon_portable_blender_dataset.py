import json
from decimal import Decimal, InvalidOperation
from math import ceil
from pathlib import Path
from typing import Any



# ============================================================
# 项目路径
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

OUTPUT_FILE = (
    BASE_DIR
    / "data"
    / "market_intelligence"
    / "amazon_us_portable_blender_v1"
    / "products.jsonl"
)


# ============================================================
# 数据源
# ============================================================

DATASET_REPO = "McAuley-Lab/Amazon-Reviews-2023"

# 固定数据版本，保证构建结果可复现。
META_REVISION = "e4458357e3499c762fb83a8c721fde557b7d0e8d"

META_FILES = [
    (
        "hf://datasets/"
        f"{DATASET_REPO}"
        f"@{META_REVISION}/"
        "raw_meta_Home_and_Kitchen/"
        f"full-{index:05d}-of-00021.parquet"
    )
    for index in range(21)
]


# ============================================================
# 筛选配置
# ============================================================

PRODUCT_LIMIT = 300
MIN_PRICE_COVERAGE_PERCENT = 80
MIN_PRICED_PRODUCTS = ceil(PRODUCT_LIMIT * MIN_PRICE_COVERAGE_PERCENT / 100)
MAX_UNPRICED_PRODUCTS = PRODUCT_LIMIT - MIN_PRICED_PRODUCTS

# 标题本身已经包含设备级供电特征时，可直接判定为目标商品。
DIRECT_TARGET_PATTERNS = (
    "cordless blender",
    "rechargeable blender",
    "usb blender",
)

# 这些名称本身不足以证明设备真正便携，必须再有电池/充电/无绳等供电证据。
CONDITIONAL_TARGET_PATTERNS = (
    "portable blender",
    "travel blender",
    "personal blender",
    "mini blender",
    "single serve blender",
    "single-serve blender",
)

STRONG_PORTABILITY_SIGNALS = (
    "rechargeable",
    "rechargable",
    "rechargeabe",
    "usb rechargeable",
    "usb charging",
    "usb charge",
    "usb-c",
    "type-c",
    "rechargeable battery",
    "rechargeable batteries",
    "built-in battery",
    "built in battery",
    "battery powered",
    "battery-powered",
    "battery operated",
    "battery-operated",
    "cordless",
    "wireless",
    "magnetic charging",
    "charging port",
    "while charging",
    "power bank",
    "battery",
    "batteries",
)

NEGATIVE_PORTABILITY_PATTERNS = (
    "requires no battery",
    "no battery",
    "without battery",
    "no electricity required",
    "non-electric",
    "non electric",
    "hand-cranked",
    "hand cranked",
    "manual blender",
    "not a battery powered blender",
    "not battery powered",
    "corded appliance",
    "runs off 120v",
    "requires 120 vac",
)

# 无论标题是否含 portable blender，都应直接排除的商品。
HARD_EXCLUDE_TITLE_PATTERNS = (
    "replacement",
    "spare part",
    "carrying case",
    "storage case",
    "travel case",
    "protective case",
    "carrying bag",
    "storage bag",
    "accessories for",
    "parts for",
    "compatible with",
    "portable blender cup",
    "portable blender bottle",
    "blender bottles set",
    "take-along bottle",
    "take along bottle",
    "commuter lid",
    "milk frother",
    "frother",
    "whisk",
    "pot stirrer",
    "herb grinder",
    "spice grinder",
    "egg beater",
    "immersion blender",
    "hand-cranked",
    "hand cranked",
    "vegetable slicer",
)

# Amazon metadata 已明确标成这些类别时直接排除。
EXCLUDE_CATEGORY_PATTERNS = (
    "milk frothers",
    "blender replacement parts",
    "small appliance parts & accessories",
    "cocktail shakers",
    "food choppers",
    "choppers & mincers",
)


def to_searchable_text(value: Any) -> str:
    """把 metadata 中的值转换成统一可搜索文本。"""
    if value is None:
        return ""

    if isinstance(value, str):
        return value

    if isinstance(value, list):
        return " ".join(
            to_searchable_text(item)
            for item in value
        )

    if isinstance(value, dict):
        return " ".join(
            f"{key} {to_searchable_text(item)}"
            for key, item in value.items()
        )

    return str(value)


def is_target_product(item: dict) -> bool:
    """判断商品本身是否为便携搅拌机，而不是配件或其他小家电。"""
    title = to_searchable_text(item.get("title")).lower()
    categories = to_searchable_text(item.get("categories")).lower()

    if not title:
        return False

    if any(pattern in categories for pattern in EXCLUDE_CATEGORY_PATTERNS):
        return False

    if any(pattern in title for pattern in HARD_EXCLUDE_TITLE_PATTERNS):
        return False

    product_text = " ".join(
        [
            title,
            to_searchable_text(item.get("features")),
            to_searchable_text(item.get("description")),
        ]
    ).lower()

    if any(pattern in product_text for pattern in NEGATIVE_PORTABILITY_PATTERNS):
        return False

    if any(pattern in title for pattern in DIRECT_TARGET_PATTERNS):
        return True

    if not any(pattern in title for pattern in CONDITIONAL_TARGET_PATTERNS):
        return False

    return any(
        signal in product_text
        for signal in STRONG_PORTABILITY_SIGNALS
    )


def has_valid_price(value: Any) -> bool:
    """判断 Amazon metadata 的 price 是否可作为正数价格使用。"""
    if value is None or isinstance(value, bool):
        return False

    text = str(value).strip()
    if not text or text.casefold() in {"none", "null", "nan", "n/a", "na", "-"}:
        return False

    try:
        price = Decimal(text)
    except (InvalidOperation, ValueError):
        return False

    return price.is_finite() and price > 0


def can_finalize_sample(*, priced_count: int, total_count: int) -> bool:
    """只有总数和有价商品数都达到 V4 下限时才允许停止扫描。"""
    return (
        total_count >= PRODUCT_LIMIT
        and priced_count >= MIN_PRICED_PRODUCTS
    )


def select_final_products(
    priced_products: list[dict],
    unpriced_products: list[dict],
) -> list[dict]:
    """优先保留有价商品，并保证最终 300 条中至少 80% 有有效价格。"""
    total_candidates = len(priced_products) + len(unpriced_products)

    if total_candidates < PRODUCT_LIMIT:
        raise RuntimeError(
            "Unable to build portable blender dataset: "
            f"target_count={PRODUCT_LIMIT}, "
            f"total_candidates={total_candidates}."
        )

    if len(priced_products) < MIN_PRICED_PRODUCTS:
        raise RuntimeError(
            "Unable to build dataset with at least "
            f"{MIN_PRICE_COVERAGE_PERCENT}% valid price coverage: "
            f"target_count={PRODUCT_LIMIT}, "
            f"required_priced_count={MIN_PRICED_PRODUCTS}, "
            f"actual_priced_count={len(priced_products)}, "
            f"total_candidates={total_candidates}."
        )

    selected_priced = priced_products[:PRODUCT_LIMIT]
    remaining = PRODUCT_LIMIT - len(selected_priced)
    selected = selected_priced + unpriced_products[:remaining]

    if len(selected) != PRODUCT_LIMIT:
        raise RuntimeError(
            "Unable to assemble final portable blender dataset: "
            f"target_count={PRODUCT_LIMIT}, selected_count={len(selected)}."
        )

    selected_priced_count = sum(
        1 for item in selected if has_valid_price(item.get("price"))
    )
    if selected_priced_count < MIN_PRICED_PRODUCTS:
        raise RuntimeError(
            "Final dataset violates price coverage requirement: "
            f"required_priced_count={MIN_PRICED_PRODUCTS}, "
            f"actual_priced_count={selected_priced_count}."
        )

    return selected


def build_output_record(item: dict) -> dict:
    """保留市场情报后续需要的 Amazon 原始字段。"""
    return {
        "parent_asin": item.get("parent_asin"),
        "title": item.get("title"),
        "main_category": item.get("main_category"),
        "categories": item.get("categories"),
        "features": item.get("features"),
        "description": item.get("description"),
        "price": item.get("price"),
        "average_rating": item.get("average_rating"),
        "rating_number": item.get("rating_number"),
        "store": item.get("store"),
        "_source_dataset": DATASET_REPO,
        "_source_revision": META_REVISION,
        "_source_subset": "raw_meta_Home_and_Kitchen",
        "_platform": "amazon",
        "_market": "US",
    }


def main() -> None:
    from datasets import load_dataset

    print("=" * 70)
    print("Amazon portable blender product dataset builder v4")
    print("=" * 70)
    print(
        f"目标商品数={PRODUCT_LIMIT}, "
        f"最低价格覆盖率={MIN_PRICE_COVERAGE_PERCENT}%, "
        f"至少有价商品数={MIN_PRICED_PRODUCTS}"
    )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("\n[1] 使用 Home_and_Kitchen 商品 metadata...")

    dataset = load_dataset(
        "parquet",
        data_files={
            "train": META_FILES,
        },
        split="train",
        streaming=True,
    )

    print("\n[2] 开始筛选便携搅拌机商品...\n")

    priced_products: list[dict] = []
    unpriced_products: list[dict] = []
    seen_asins: set[str] = set()
    scanned = 0

    for item in dataset:
        scanned += 1

        if scanned % 10_000 == 0:
            total_candidates = len(priced_products) + len(unpriced_products)
            print(
                f"已扫描 {scanned:,} 条 metadata，"
                f"候选={total_candidates}，"
                f"有价={len(priced_products)}，"
                f"缺价={len(unpriced_products)}"
            )

        if not is_target_product(item):
            continue

        parent_asin = str(
            item.get("parent_asin") or ""
        ).strip()

        if not parent_asin or parent_asin in seen_asins:
            continue

        record = build_output_record(item)
        seen_asins.add(parent_asin)

        if has_valid_price(record.get("price")):
            priced_products.append(record)
            price_status = "priced"
        else:
            unpriced_products.append(record)
            price_status = "unpriced"

        total_candidates = len(priced_products) + len(unpriced_products)
        print(
            f"[{total_candidates}] "
            f"{parent_asin} | "
            f"{item.get('title')} | "
            f"price={item.get('price')} | "
            f"{price_status} | "
            f"priced={len(priced_products)}"
        )

        if can_finalize_sample(
            priced_count=len(priced_products),
            total_count=total_candidates,
        ):
            print(
                "\n已经满足商品数量和最低价格覆盖率，"
                "停止继续扫描。"
            )
            break

    matched_products = select_final_products(
        priced_products,
        unpriced_products,
    )

    final_priced_count = sum(
        1 for item in matched_products if has_valid_price(item.get("price"))
    )
    price_coverage_ratio = final_priced_count / len(matched_products)

    print("\n[3] 写入 JSONL 文件...")

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:
        for item in matched_products:
            file.write(
                json.dumps(
                    item,
                    ensure_ascii=False,
                )
                + "\n"
            )

    print("\n" + "=" * 70)
    print("完成")
    print("=" * 70)
    print(f"扫描 metadata：{scanned:,}")
    print(f"候选商品：{len(priced_products) + len(unpriced_products)}")
    print(f"保存商品：{len(matched_products)}")
    print(f"有效价格商品：{final_priced_count}")
    print(f"缺失价格商品：{len(matched_products) - final_priced_count}")
    print(f"价格覆盖率：{price_coverage_ratio:.2%}")
    print(f"保存文件：{OUTPUT_FILE}")


if __name__ == "__main__":
    main()