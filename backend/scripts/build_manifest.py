"""生成固定数据集的 manifest.json。

用法：
    python backend/scripts/build_manifest.py \
        --slug portable_blender \
        --category "portable blender" \
        --keyword "portable blender" \
        --alias "便携搅拌机" \
        --alias "便携式搅拌机"

参数：
    --slug       数据集标识，用于目录名和 dataset_id，如 portable_blender
    --category   manifest 中的商品类别，如 portable blender
    --keyword    manifest 中的主关键词
    --alias      商品别名，可重复传入
    --version    数据集目录版本，默认 v1
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

BASE_DIR = Path(__file__).resolve().parent.parent

SOURCE_DESCRIPTION = "McAuley-Lab/Amazon-Reviews-2023"
SOURCE_TYPE = "anonymized_snapshot"
LICENSE_OR_AUTHORIZATION = (
    "Development and demonstration use only; source dataset terms apply; "
    "production authorization is not established."
)




def infer_source_timestamp(reviews_path: Path) -> str:
    """从 reviews.jsonl 中取最新评论时间作为 source_timestamp。"""
    if not reviews_path.exists():
        raise FileNotFoundError(f"评论文件不存在：{reviews_path}")

    latest_timestamp_ms: int | None = None

    with reviews_path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                review = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"reviews.jsonl 第 {line_number} 行不是有效 JSON。"
                ) from exc

            value = review.get("timestamp")
            if value is None:
                continue

            try:
                timestamp = float(value)
            except (TypeError, ValueError):
                continue

            # Amazon Reviews 2023 的 timestamp 为 Unix 毫秒时间戳。
            timestamp_ms = int(timestamp)
            if latest_timestamp_ms is None or timestamp_ms > latest_timestamp_ms:
                latest_timestamp_ms = timestamp_ms

    if latest_timestamp_ms is None:
        raise ValueError("reviews.jsonl 中没有有效 timestamp。")

    source_time = datetime.fromtimestamp(
        latest_timestamp_ms / 1000,
        tz=timezone.utc,
    )
    return source_time.isoformat().replace("+00:00", "Z")


def semantic_dataset_version(version: str) -> str:
    """将 v1、v2 等目录版本转换为 1.0.0、2.0.0。"""
    if not version.startswith("v") or not version[1:].isdigit():
        raise ValueError("version 必须使用 v1、v2 这样的格式。")
    return f"{int(version[1:])}.0.0"


def build_dataset_dir(
    base_dir: Path,
    slug: str,
    version: str,
) -> Path:
    return base_dir / "data" / "market_intelligence" /f"amazon_us_{slug}_{version}"


def _normalize_aliases(values: Sequence[str]) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()

    for value in values:
        alias = value.strip()
        if alias and alias not in seen:
            aliases.append(alias)
            seen.add(alias)

    return aliases


def write_manifest(
    *,
    dataset_dir: Path,
    version: str,
    category: str,
    keyword: str,
    aliases: Sequence[str],
    generated_at: str | None = None,
) -> Path:
    """按固定 manifest schema 写入 manifest.json。"""
    category = category.strip()
    keyword = keyword.strip()

    if not category:
        raise ValueError("category 不能为空。")
    if not keyword:
        raise ValueError("keyword 不能为空。")

    dataset_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = dataset_dir / "manifest.json"

    if generated_at is None:
        generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    source_timestamp = infer_source_timestamp(dataset_dir / "reviews.jsonl")

    manifest = {
        "dataset_id": dataset_dir.name,
        "dataset_version": semantic_dataset_version(version),
        "schema_version": "1.0",
        "platform": "amazon",
        "market": "US",
        "category": category,
        "keyword": keyword,
        "aliases": _normalize_aliases(aliases),
        "source_type": SOURCE_TYPE,
        "source_description": SOURCE_DESCRIPTION,
        "generated_at": generated_at,
        "source_timestamp": source_timestamp,
        "license_or_authorization": LICENSE_OR_AUTHORIZATION,
        "checksums": {
            "products.jsonl": "",
            "reviews.jsonl": "",
            "market_metrics.json": "",
            "profit_inputs.json": "",
        },
    }

    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="生成 Amazon US 固定数据集 manifest.json。"
    )
    parser.add_argument("--slug", required=True, help="数据集标识，如 portable_blender")
    parser.add_argument("--category", required=True, help="商品类别，如 portable blender")
    parser.add_argument("--keyword", required=True, help="主关键词，如 portable blender")
    parser.add_argument(
        "--alias",
        action="append",
        default=[],
        help="商品别名，可重复传入",
    )
    parser.add_argument("--version", default="v1", help="数据集目录版本，默认 v1")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        dataset_dir = build_dataset_dir(BASE_DIR, args.slug.strip(), args.version.strip())
        manifest_path = write_manifest(
            dataset_dir=dataset_dir,
            version=args.version.strip(),
            category=args.category,
            keyword=args.keyword,
            aliases=args.alias,
        )
    except ValueError as exc:
        parser.error(str(exc))

    print(f"manifest generated: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())