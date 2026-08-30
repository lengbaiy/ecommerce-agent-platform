from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from pathlib import Path


# ============================================================
# 项目路径
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

DATASET_DIR = (
    BASE_DIR
    / "data"
    / "market_intelligence"
    / "amazon_us_portable_blender_v1"
)

PRODUCT_FILE = DATASET_DIR / "products.jsonl"
REVIEW_FILE = DATASET_DIR / "reviews.jsonl"


# ============================================================
# 数据源
# ============================================================

DATASET_REPO = "McAuley-Lab/Amazon-Reviews-2023"

# 与便携咖啡机评论脚本保持相同的固定 review revision。
REVIEW_REVISION = "e4458357e3499c762fb83a8c721fde557b7d0e8d"

REVIEW_SUBSET = "raw_review_Home_and_Kitchen"


# ============================================================
# 抽样配置
# ============================================================

REVIEWS_PER_PRODUCT = 30


def load_product_ids(product_file: Path = PRODUCT_FILE) -> set[str]:
    """从 V4 products.jsonl 中读取目标商品 parent_asin。"""
    if not product_file.exists():
        raise FileNotFoundError(
            "\n商品数据文件不存在："
            f"\n{product_file}"
            "\n"
            "\n请先运行便携搅拌机 V4 商品构建脚本。"
        )

    product_ids: set[str] = set()

    with product_file.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"商品 JSONL 第 {line_number} 行不是合法 JSON：{product_file}"
                ) from exc

            product_id = str(item.get("parent_asin") or "").strip()
            if product_id:
                product_ids.add(product_id)

    if not product_ids:
        raise RuntimeError(
            f"商品文件存在，但其中没有有效 parent_asin：{product_file}"
        )

    return product_ids


def build_review_record(review: dict) -> dict:
    """
    只保留市场情报评论分析需要的 Amazon 原始评论字段。

    不保存 user_id，因为当前项目不需要用户身份。
    """
    return {
        "parent_asin": review.get("parent_asin"),
        "rating": review.get("rating"),
        "title": review.get("title"),
        "text": review.get("text"),
        "timestamp": review.get("timestamp"),
        "helpful_vote": review.get("helpful_vote"),
        "verified_purchase": review.get("verified_purchase"),
        "_source_dataset": DATASET_REPO,
        "_source_revision": REVIEW_REVISION,
        "_source_subset": REVIEW_SUBSET,
        "_platform": "amazon",
        "_market": "US",
    }


def all_products_full(
    target_ids: set[str],
    counts: dict[str, int],
    *,
    reviews_per_product: int = REVIEWS_PER_PRODUCT,
) -> bool:
    """判断所有目标商品是否都已经达到每商品评论上限。"""
    return all(
        counts.get(product_id, 0) >= reviews_per_product
        for product_id in target_ids
    )


def collect_reviews(
    dataset: Iterable[dict],
    *,
    target_ids: set[str],
    reviews_per_product: int = REVIEWS_PER_PRODUCT,
) -> tuple[list[dict], dict[str, int], int]:
    """
    从 review 流中收集目标商品评论。

    按源数据扫描顺序保留，每个商品最多 reviews_per_product 条；
    所有目标商品都达到上限后提前停止。
    """
    if reviews_per_product <= 0:
        raise ValueError("reviews_per_product must be greater than 0")

    counts: dict[str, int] = {
        product_id: 0
        for product_id in target_ids
    }
    collected_reviews: list[dict] = []
    scanned = 0

    for review in dataset:
        scanned += 1

        if scanned % 100_000 == 0:
            print(
                f"已扫描 {scanned:,} 条评论，"
                f"已保存 {len(collected_reviews):,} 条"
            )

        product_id = str(review.get("parent_asin") or "").strip()

        if product_id not in target_ids:
            continue

        if counts[product_id] >= reviews_per_product:
            continue

        collected_reviews.append(build_review_record(review))
        counts[product_id] += 1

        print(
            f"{product_id}: "
            f"{counts[product_id]:02d}/"
            f"{reviews_per_product} "
            f"| rating={review.get('rating')}"
        )

        if all_products_full(
            target_ids,
            counts,
            reviews_per_product=reviews_per_product,
        ):
            print(
                "\n所有目标商品都已经获得足够评论，停止扫描。"
            )
            break

    return collected_reviews, counts, scanned


def build_review_parquet_urls(
    repo_files: Sequence[str],
) -> list[str]:
    """
    从固定 revision 的仓库文件清单中定位 Home_and_Kitchen review shards。

    不写死 shard 数量，避免源子集 shard 数变化时漏读文件。
    """
    prefix = f"{REVIEW_SUBSET}/"

    shard_paths = sorted(
        path
        for path in repo_files
        if path.startswith(prefix)
        and path.endswith(".parquet")
    )

    if not shard_paths:
        raise RuntimeError(
            "没有在固定 revision 中找到评论 Parquet："
            f"{REVIEW_SUBSET}"
        )

    return [
        (
            "hf://datasets/"
            f"{DATASET_REPO}"
            f"@{REVIEW_REVISION}/"
            f"{path}"
        )
        for path in shard_paths
    ]


def resolve_review_files() -> list[str]:
    """通过 Hugging Face Hub 文件清单解析 review shard URL。"""
    from huggingface_hub import list_repo_files

    repo_files = list_repo_files(
        repo_id=DATASET_REPO,
        repo_type="dataset",
        revision=REVIEW_REVISION,
    )
    return build_review_parquet_urls(repo_files)


def write_reviews(
    reviews: Iterable[dict],
    output_file: Path = REVIEW_FILE,
) -> int:
    """把评论记录写入 JSONL，返回写入数量。"""
    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    count = 0
    with output_file.open("w", encoding="utf-8") as file:
        for review in reviews:
            file.write(
                json.dumps(
                    review,
                    ensure_ascii=False,
                )
                + "\n"
            )
            count += 1

    return count


def main() -> None:
    from datasets import load_dataset

    print("=" * 70)
    print("Amazon portable blender review dataset builder")
    print("=" * 70)

    # --------------------------------------------------------
    # 1. 读取 V4 商品 ID
    # --------------------------------------------------------

    print("\n[1] 读取目标商品 ID...")

    target_ids = load_product_ids()

    print(f"目标商品数量：{len(target_ids)}")
    print(f"每商品最大评论数：{REVIEWS_PER_PRODUCT}")

    # --------------------------------------------------------
    # 2. 定位固定 revision 的评论 Parquet
    # --------------------------------------------------------

    print("\n[2] 定位 Home_and_Kitchen 评论 Parquet...")

    review_files = resolve_review_files()

    for file_path in review_files:
        print(f"  - {file_path}")

    # --------------------------------------------------------
    # 3. Streaming 加载
    # --------------------------------------------------------

    print("\n[3] 创建 streaming review dataset...")

    dataset = load_dataset(
        "parquet",
        data_files={
            "train": review_files,
        },
        split="train",
        streaming=True,
    )

    # --------------------------------------------------------
    # 4. 筛选评论
    # --------------------------------------------------------

    print("\n[4] 开始匹配评论...\n")

    collected_reviews, counts, scanned = collect_reviews(
        dataset,
        target_ids=target_ids,
        reviews_per_product=REVIEWS_PER_PRODUCT,
    )

    # --------------------------------------------------------
    # 5. 保存评论
    # --------------------------------------------------------

    print("\n[5] 保存评论 JSONL...")

    saved_count = write_reviews(
        collected_reviews,
        REVIEW_FILE,
    )

    # --------------------------------------------------------
    # 6. 输出统计
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("完成")
    print("=" * 70)
    print(f"扫描评论：{scanned:,}")
    print(f"保存评论：{saved_count:,}")
    print(f"保存位置：{REVIEW_FILE}")

    print("\n每个商品获得的评论数量：")
    for product_id in sorted(target_ids):
        print(
            f"  {product_id}: "
            f"{counts[product_id]}"
        )

    missing_products = [
        product_id
        for product_id in sorted(target_ids)
        if counts[product_id] == 0
    ]

    if missing_products:
        print(
            "\n以下商品在 Home_and_Kitchen 评论数据中"
            "没有找到评论："
        )
        for product_id in missing_products:
            print(f"  - {product_id}")

    underfilled_products = [
        product_id
        for product_id in sorted(target_ids)
        if 0 < counts[product_id] < REVIEWS_PER_PRODUCT
    ]

    if underfilled_products:
        print(
            "\n以下商品有评论，但不足每商品 "
            f"{REVIEWS_PER_PRODUCT} 条："
        )
        for product_id in underfilled_products:
            print(
                f"  - {product_id}: "
                f"{counts[product_id]}"
            )


if __name__ == "__main__":
    main()