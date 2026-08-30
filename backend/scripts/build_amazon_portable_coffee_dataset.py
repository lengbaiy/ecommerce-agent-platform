import json
from pathlib import Path
from typing import Any

from datasets import load_dataset


# ============================================================
# 项目路径
# ============================================================

# 当前脚本：
# backend/scripts/build_amazon_portable_coffee_dataset.py
#
# parent.parent -> backend/
BASE_DIR = Path(__file__).resolve().parent.parent

OUTPUT_FILE = (
    BASE_DIR
    / "data"
    / "products"
    / "amazon_us_portable_coffee_v1.jsonl"
)


# ============================================================
# 数据源
# ============================================================

DATASET_REPO = "McAuley-Lab/Amazon-Reviews-2023"

# 固定到明确 revision，避免 main 分支以后变化
META_REVISION = "3c9f864b83420edc8a9d8e5dc19c14c46eaf6c3b"

META_FILES = [
    (
        "hf://datasets/"
        "McAuley-Lab/Amazon-Reviews-2023"
        f"@{META_REVISION}/"
        "raw_meta_Appliances/"
        "full-00000-of-00001.parquet"
    )
]


# ============================================================
# 筛选配置
# ============================================================

PRODUCT_LIMIT = 30

KEYWORDS = (
    "portable coffee maker",
    "portable espresso maker",
    "portable espresso machine",
    "travel coffee maker",
    "travel espresso maker",
    "portable coffee machine",
    "portable coffee brewer",
)


def to_searchable_text(value: Any) -> str:
    """
    把 metadata 中可能出现的字符串、列表、字典等
    转换成统一可搜索文本。
    """

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
    """
    判断商品是否与便携咖啡机相关。
    """

    searchable_text = " ".join(
        [
            to_searchable_text(item.get("title")),
            to_searchable_text(item.get("features")),
            to_searchable_text(item.get("description")),
            to_searchable_text(item.get("categories")),
        ]
    ).lower()

    return any(
        keyword in searchable_text
        for keyword in KEYWORDS
    )


def build_output_record(item: dict) -> dict:
    """
    保留市场情报后续真正需要的字段。

    注意：
    这里保存的仍然是 Amazon fixed dataset 原始字段，
    不是最终 NormalizedProduct。

    后续 FixedDatasetAdapter 再做字段转换。
    """

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

        # 来源信息
        "_source_dataset": DATASET_REPO,
        "_source_revision": META_REVISION,
        "_source_subset": "raw_meta_Appliances",
        "_platform": "amazon",
        "_market": "US",
    }


def main() -> None:
    print("=" * 70)
    print("Amazon portable coffee product dataset builder")
    print("=" * 70)

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # 1. 数据文件
    # --------------------------------------------------------

    print("\n[1] 使用固定版本的商品 metadata Parquet 文件...")

    for file_path in META_FILES:
        print(f"  - {file_path}")

    # --------------------------------------------------------
    # 2. Streaming 加载
    # --------------------------------------------------------

    print("\n[2] 创建 streaming dataset...")

    dataset = load_dataset(
        "parquet",
        data_files={
            "train": META_FILES,
        },
        split="train",
        streaming=True,
    )

    # --------------------------------------------------------
    # 3. 筛选商品
    # --------------------------------------------------------

    print("\n[3] 开始筛选便携咖啡机商品...\n")

    matched_products: list[dict] = []
    seen_asins: set[str] = set()

    scanned = 0

    for item in dataset:
        scanned += 1

        if scanned % 10_000 == 0:
            print(
                f"已扫描 {scanned:,} 条 metadata，"
                f"当前匹配 {len(matched_products)} 条"
            )

        if not is_target_product(item):
            continue

        parent_asin = str(
            item.get("parent_asin") or ""
        ).strip()

        if not parent_asin:
            continue

        if parent_asin in seen_asins:
            continue

        record = build_output_record(item)

        matched_products.append(record)
        seen_asins.add(parent_asin)

        print(
            f"[{len(matched_products):02d}/{PRODUCT_LIMIT}] "
            f"{parent_asin} | "
            f"{item.get('title')} | "
            f"price={item.get('price')} | "
            f"rating={item.get('average_rating')}"
        )

        if len(matched_products) >= PRODUCT_LIMIT:
            print("\n已经达到目标商品数量，停止继续扫描。")
            break

    # --------------------------------------------------------
    # 4. 保存 JSONL
    # --------------------------------------------------------

    print("\n[4] 写入 JSONL 文件...")

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

    # --------------------------------------------------------
    # 5. 输出统计
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("完成")
    print("=" * 70)

    print(f"扫描 metadata：{scanned:,}")
    print(f"匹配商品：{len(matched_products)}")
    print(f"保存文件：{OUTPUT_FILE}")

    if not matched_products:
        print(
            "\n警告：没有找到匹配商品。"
            "\n可以考虑："
            "\n1. 扩大关键词"
            "\n2. 改用 Home_and_Kitchen 类目"
        )


if __name__ == "__main__":
    main()