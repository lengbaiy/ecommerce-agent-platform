import json
from collections import defaultdict
from pathlib import Path

from datasets import load_dataset


# ============================================================
# 项目路径
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

PRODUCT_FILE = (
    BASE_DIR
    / "data"
    / "products"
    / "amazon_us_portable_coffee_v1.jsonl"
)

REVIEW_FILE = (
    BASE_DIR
    / "data"
    / "reviews"
    / "amazon_us_portable_coffee_v1.jsonl"
)


# ============================================================
# 数据源
# ============================================================

DATASET_REPO = "McAuley-Lab/Amazon-Reviews-2023"

REVIEW_REVISION = "e4458357e3499c762fb83a8c721fde557b7d0e8d"

REVIEW_FILES = [
    (
        "hf://datasets/"
        "McAuley-Lab/Amazon-Reviews-2023"
        f"@{REVIEW_REVISION}/"
        "raw_review_Appliances/"
        "full-00000-of-00002.parquet"
    ),
    (
        "hf://datasets/"
        "McAuley-Lab/Amazon-Reviews-2023"
        f"@{REVIEW_REVISION}/"
        "raw_review_Appliances/"
        "full-00001-of-00002.parquet"
    ),
]


# ============================================================
# 抽样配置
# ============================================================

REVIEWS_PER_PRODUCT = 30


def load_product_ids() -> set[str]:
    """
    从商品脚本输出中读取需要查找评论的 parent_asin。
    """

    if not PRODUCT_FILE.exists():
        raise FileNotFoundError(
            "\n商品数据文件不存在："
            f"\n{PRODUCT_FILE}"
            "\n"
            "\n请先运行："
            "\npython scripts/build_amazon_portable_coffee_dataset.py"
        )

    product_ids: set[str] = set()

    with PRODUCT_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        for line in file:
            line = line.strip()

            if not line:
                continue

            item = json.loads(line)

            product_id = str(
                item.get("parent_asin") or ""
            ).strip()

            if product_id:
                product_ids.add(product_id)

    if not product_ids:
        raise RuntimeError(
            "商品文件存在，但其中没有有效 parent_asin。"
        )

    return product_ids


def build_review_record(review: dict) -> dict:
    """
    只保留市场情报评论分析需要的字段。

    不保存 user_id，因为当前项目不需要用户身份。
    """

    return {
        "parent_asin": review.get("parent_asin"),
        "rating": review.get("rating"),
        "title": review.get("title"),
        "text": review.get("text"),
        "timestamp": review.get("timestamp"),
        "helpful_vote": review.get("helpful_vote"),
        "verified_purchase": review.get(
            "verified_purchase"
        ),

        # 来源信息
        "_source_dataset": DATASET_REPO,
        "_source_revision": REVIEW_REVISION,
        "_source_subset": "raw_review_Appliances",
        "_platform": "amazon",
        "_market": "US",
    }


def all_products_full(
    target_ids: set[str],
    counts: dict[str, int],
) -> bool:
    """
    判断所有目标商品是否都已经拿到足够评论。
    """

    return all(
        counts[product_id] >= REVIEWS_PER_PRODUCT
        for product_id in target_ids
    )


def main() -> None:
    print("=" * 70)
    print("Amazon portable coffee review dataset builder")
    print("=" * 70)

    # --------------------------------------------------------
    # 1. 读取目标商品
    # --------------------------------------------------------

    print("\n[1] 读取目标商品 ID...")

    target_ids = load_product_ids()

    print(f"目标商品数量：{len(target_ids)}")

    # --------------------------------------------------------
    # 2. 评论数据文件
    # --------------------------------------------------------

    print("\n[2] 使用固定版本的评论 Parquet 文件...")

    for file_path in REVIEW_FILES:
        print(f"  - {file_path}")

    # --------------------------------------------------------
    # 3. Streaming 加载
    # --------------------------------------------------------

    print("\n[3] 创建 streaming review dataset...")

    dataset = load_dataset(
        "parquet",
        data_files={
            "train": REVIEW_FILES,
        },
        split="train",
        streaming=True,
    )

    # --------------------------------------------------------
    # 4. 筛选评论
    # --------------------------------------------------------

    print("\n[4] 开始匹配评论...\n")

    counts: dict[str, int] = defaultdict(int)

    collected_reviews: list[dict] = []

    scanned = 0

    for review in dataset:
        scanned += 1

        if scanned % 100_000 == 0:
            print(
                f"已扫描 {scanned:,} 条评论，"
                f"已保存 {len(collected_reviews):,} 条"
            )

        product_id = str(
            review.get("parent_asin") or ""
        ).strip()

        # 不是目标商品
        if product_id not in target_ids:
            continue

        # 当前商品评论已经达到上限
        if counts[product_id] >= REVIEWS_PER_PRODUCT:
            continue

        record = build_review_record(review)

        collected_reviews.append(record)

        counts[product_id] += 1

        print(
            f"{product_id}: "
            f"{counts[product_id]:02d}/"
            f"{REVIEWS_PER_PRODUCT} "
            f"| rating={review.get('rating')}"
        )

        # 所有商品都达到评论数量后提前结束
        if all_products_full(target_ids, counts):
            print(
                "\n所有目标商品都已经获得足够评论，停止扫描。"
            )
            break

    # --------------------------------------------------------
    # 5. 保存评论
    # --------------------------------------------------------

    print("\n[5] 保存评论 JSONL...")

    REVIEW_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with REVIEW_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:
        for review in collected_reviews:
            file.write(
                json.dumps(
                    review,
                    ensure_ascii=False,
                )
                + "\n"
            )

    # --------------------------------------------------------
    # 6. 输出统计
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("完成")
    print("=" * 70)

    print(f"扫描评论：{scanned:,}")
    print(f"保存评论：{len(collected_reviews):,}")
    print(f"保存位置：{REVIEW_FILE}")

    print("\n每个商品获得的评论数量：")

    for product_id in sorted(target_ids):
        print(
            f"  {product_id}: "
            f"{counts[product_id]}"
        )

    missing_products = [
        product_id
        for product_id in target_ids
        if counts[product_id] == 0
    ]

    if missing_products:
        print(
            "\n以下商品在 Appliances 评论数据中"
            "没有找到评论："
        )

        for product_id in missing_products:
            print(f"  - {product_id}")


if __name__ == "__main__":
    main()