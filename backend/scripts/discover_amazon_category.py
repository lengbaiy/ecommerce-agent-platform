from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from typing import Any, Iterable, Sequence


DATASET_REPO = "McAuley-Lab/Amazon-Reviews-2023"
META_REVISION = "3c9f864b83420edc8a9d8e5dc19c14c46eaf6c3b"
DEFAULT_SCAN_LIMIT = 100_000
DEFAULT_MATCH_LIMIT = 30
DEFAULT_EXAMPLE_LIMIT = 5
DEFAULT_TOP = 10

_META_PARQUET_PATTERN = re.compile(
    r"^raw_meta_(?P<category>[^/]+)/.+\.parquet$"
)


@dataclass(frozen=True)
class CategoryScanResult:
    category: str
    scanned: int
    matches: int
    examples: list[str]
    match_cap_reached: bool = False
    scan_limit_reached: bool = False

    @property
    def hit_rate(self) -> float:
        if self.scanned == 0:
            return 0.0
        return self.matches / self.scanned


def to_searchable_text(value: Any) -> str:
    """把 metadata 中的嵌套值转换为可搜索文本。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple, set)):
        return " ".join(to_searchable_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(
            f"{key} {to_searchable_text(item)}"
            for key, item in value.items()
        )
    return str(value)


def build_searchable_text(item: dict[str, Any]) -> str:
    """沿用商品构建脚本的字段：title/features/description/categories。"""
    fields = (
        item.get("title"),
        item.get("features"),
        item.get("description"),
        item.get("categories"),
    )
    return " ".join(to_searchable_text(value) for value in fields).lower()


def normalize_keywords(keywords: Sequence[str]) -> list[str]:
    normalized = [keyword.strip().lower() for keyword in keywords if keyword.strip()]
    if not normalized:
        raise ValueError("至少需要一个非空商品关键词。")
    return normalized


def item_matches_keywords(item: dict[str, Any], keywords: Sequence[str]) -> bool:
    searchable_text = build_searchable_text(item)
    normalized_keywords = normalize_keywords(keywords)
    return any(keyword in searchable_text for keyword in normalized_keywords)


def discover_meta_categories(repo_files: Iterable[str]) -> dict[str, list[str]]:
    """从仓库文件列表中自动发现 raw_meta_* Parquet 子集。"""
    categories: dict[str, list[str]] = {}

    for file_path in repo_files:
        match = _META_PARQUET_PATTERN.match(file_path)
        if match is None:
            continue

        category = match.group("category")
        categories.setdefault(category, []).append(file_path)

    return {
        category: sorted(paths)
        for category, paths in sorted(categories.items())
    }


def scan_items(
    *,
    category: str,
    items: Iterable[dict[str, Any]],
    keywords: Sequence[str],
    scan_limit: int,
    match_limit: int,
    example_limit: int,
) -> CategoryScanResult:
    """扫描一个类目的商品流，返回候选匹配统计。"""
    normalized_keywords = normalize_keywords(keywords)
    scanned = 0
    matches = 0
    examples: list[str] = []
    match_cap_reached = False
    scan_limit_reached = False

    for item in items:
        if scanned >= scan_limit:
            scan_limit_reached = True
            break

        scanned += 1

        searchable_text = build_searchable_text(item)
        if not any(keyword in searchable_text for keyword in normalized_keywords):
            continue

        matches += 1

        title = str(item.get("title") or "").strip()
        if title and len(examples) < example_limit:
            examples.append(title)

        if matches >= match_limit:
            match_cap_reached = True
            break

    return CategoryScanResult(
        category=category,
        scanned=scanned,
        matches=matches,
        examples=examples,
        match_cap_reached=match_cap_reached,
        scan_limit_reached=scan_limit_reached,
    )


def rank_results(results: Iterable[CategoryScanResult]) -> list[CategoryScanResult]:
    """优先匹配数量，其次匹配率；只保留有匹配的类目。"""
    matched = [result for result in results if result.matches > 0]
    return sorted(
        matched,
        key=lambda result: (result.matches, result.hit_rate),
        reverse=True,
    )


def list_repository_files(repo_id: str, revision: str) -> list[str]:
    try:
        from huggingface_hub import HfApi
    except ImportError as exc:
        raise RuntimeError(
            "缺少 huggingface_hub。请先安装项目依赖后再运行脚本。"
        ) from exc

    api = HfApi()
    return api.list_repo_files(
        repo_id=repo_id,
        repo_type="dataset",
        revision=revision,
    )


def build_hf_urls(
    repo_id: str,
    revision: str,
    parquet_files: Sequence[str],
) -> list[str]:
    return [
        f"hf://datasets/{repo_id}@{revision}/{file_path}"
        for file_path in parquet_files
    ]


def load_category_dataset(
    repo_id: str,
    revision: str,
    parquet_files: Sequence[str],
):
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError(
            "缺少 datasets。请先安装项目依赖后再运行脚本。"
        ) from exc

    urls = build_hf_urls(repo_id, revision, parquet_files)
    return load_dataset(
        "parquet",
        data_files={"train": urls},
        split="train",
        streaming=True,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "在 Amazon Reviews 2023 的 raw_meta_* 子集中搜索商品关键词，"
            "帮助确定最合适的 Amazon 数据类别。"
        )
    )
    parser.add_argument(
        "keywords",
        nargs="+",
        help=(
            "一个或多个商品关键词。包含空格的短语请加引号，例如 "
            '"portable blender" "personal blender"。'
        ),
    )
    parser.add_argument(
        "--scan-limit",
        type=int,
        default=DEFAULT_SCAN_LIMIT,
        help=f"每个类目最多扫描多少条 metadata，默认 {DEFAULT_SCAN_LIMIT:,}。",
    )
    parser.add_argument(
        "--match-limit",
        type=int,
        default=DEFAULT_MATCH_LIMIT,
        help=f"每个类目匹配到多少条后提前停止，默认 {DEFAULT_MATCH_LIMIT}。",
    )
    parser.add_argument(
        "--examples",
        type=int,
        default=DEFAULT_EXAMPLE_LIMIT,
        help=f"每个候选类目最多展示多少个标题样例，默认 {DEFAULT_EXAMPLE_LIMIT}。",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=DEFAULT_TOP,
        help=f"最终最多展示多少个候选类目，默认 {DEFAULT_TOP}。",
    )
    return parser.parse_args()


def validate_positive_args(args: argparse.Namespace) -> None:
    for name in ("scan_limit", "match_limit", "examples", "top"):
        value = getattr(args, name)
        if value <= 0:
            option = name.replace("_", "-")
            raise ValueError(f"--{option} 必须大于 0。")


def format_match_count(result: CategoryScanResult) -> str:
    if result.match_cap_reached:
        return f">={result.matches}"
    return str(result.matches)


def main() -> None:
    args = parse_args()
    validate_positive_args(args)
    keywords = normalize_keywords(args.keywords)

    print("=" * 72)
    print("Amazon Reviews 2023 category discovery")
    print("=" * 72)
    print(f"关键词：{', '.join(keywords)}")
    print(f"固定 revision：{META_REVISION}")
    print(f"每类最多扫描：{args.scan_limit:,}")
    print(f"每类匹配上限：{args.match_limit}")

    print("\n[1] 获取 Amazon Reviews 2023 文件列表...")
    repo_files = list_repository_files(DATASET_REPO, META_REVISION)
    categories = discover_meta_categories(repo_files)

    if not categories:
        raise RuntimeError("没有发现任何 raw_meta_* Parquet 数据子集。")

    print(f"发现 {len(categories)} 个 metadata 类目。")

    print("\n[2] 逐类目扫描关键词...")
    results: list[CategoryScanResult] = []

    for index, (category, parquet_files) in enumerate(categories.items(), start=1):
        print(
            f"\n[{index:02d}/{len(categories):02d}] {category} "
            f"({len(parquet_files)} parquet file(s))"
        )

        try:
            dataset = load_category_dataset(
                DATASET_REPO,
                META_REVISION,
                parquet_files,
            )
            result = scan_items(
                category=category,
                items=dataset,
                keywords=keywords,
                scan_limit=args.scan_limit,
                match_limit=args.match_limit,
                example_limit=args.examples,
            )
        except Exception as exc:  # 保持其他类目可继续扫描
            print(f"  扫描失败：{exc}")
            continue

        results.append(result)
        print(
            f"  scanned={result.scanned:,} "
            f"matches={format_match_count(result)} "
            f"hit_rate={result.hit_rate:.4%}"
        )

        for title in result.examples:
            print(f"    - {title}")

    ranked = rank_results(results)

    print("\n" + "=" * 72)
    print("候选类目")
    print("=" * 72)

    if not ranked:
        print("没有发现匹配商品。")
        print("可以尝试：")
        print("1. 使用更常见的英文商品关键词；")
        print("2. 增加同义词；")
        print("3. 提高 --scan-limit。")
        return

    for rank, result in enumerate(ranked[: args.top], start=1):
        match_label = format_match_count(result)
        print(
            f"\n{rank}. {result.category}"
            f"\n   matches: {match_label}"
            f"\n   scanned: {result.scanned:,}"
            f"\n   hit_rate: {result.hit_rate:.4%}"
        )
        if result.match_cap_reached:
            print("   note: 达到匹配上限，matches 是下界而不是完整数量。")
        elif result.scan_limit_reached:
            print("   note: 达到扫描上限，matches 不是完整类目统计。")

        if result.examples:
            print("   examples:")
            for title in result.examples:
                print(f"   - {title}")

    print(
        "\n说明：排名用于发现候选类目，不代表语义上自动判定正确。"
        "请结合 examples 确认匹配商品是否确实属于目标商品。"
    )


if __name__ == "__main__":
    main()