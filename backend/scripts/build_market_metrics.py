from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable


MONEY_QUANT = Decimal("0.01")
STAT_QUANT = Decimal("0.01")
RATIO_QUANT = Decimal("0.0001")
BRAND_COVERAGE_THRESHOLD = Decimal("0.80")

DEFAULT_DATASET_DIR = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "market_intelligence"
    / "amazon_us_portable_blender_v1"
)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Required dataset file not found: {path.name}")

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON in {path.name} at line {line_number}: {exc.msg}"
                ) from exc
            if not isinstance(value, dict):
                raise ValueError(
                    f"{path.name} line {line_number} must contain a JSON object"
                )
            rows.append(value)
    return rows


def optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.casefold() in {"none", "null", "n/a", "na"}:
        return None
    return text


def optional_decimal(value: Any) -> Decimal | None:
    text = optional_text(value)
    if text is None:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def optional_nonnegative_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def parse_amazon_timestamp(value: Any) -> datetime | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None

    # Amazon Reviews 2023 commonly stores timestamps in milliseconds.
    if timestamp > 10_000_000_000:
        timestamp /= 1000

    try:
        return datetime.fromtimestamp(timestamp, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def decimal_mean(values: list[Decimal]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values))


def decimal_median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal("2")


def format_decimal(value: Decimal, quantum: Decimal) -> str:
    return str(value.quantize(quantum, rounding=ROUND_HALF_UP))


def format_ratio(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return format_decimal(Decimal("0"), RATIO_QUANT)
    return format_decimal(
        Decimal(numerator) / Decimal(denominator),
        RATIO_QUANT,
    )


def coverage_status(observed_count: int, total_count: int) -> str:
    if observed_count == 0:
        return "unavailable"
    if observed_count < total_count:
        return "partial"
    return "available"


def build_decimal_distribution(
    *,
    metric_code: str,
    values: list[Decimal],
    total_product_count: int,
    unit: str,
    quantum: Decimal,
    methodology: str,
) -> dict[str, Any]:
    status = coverage_status(len(values), total_product_count)
    if not values:
        value: dict[str, Any] = {
            "observed_count": 0,
            "total_product_count": total_product_count,
            "coverage_ratio": format_ratio(0, total_product_count),
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
        }
    else:
        value = {
            "observed_count": len(values),
            "total_product_count": total_product_count,
            "coverage_ratio": format_ratio(len(values), total_product_count),
            "min": format_decimal(min(values), quantum),
            "max": format_decimal(max(values), quantum),
            "mean": format_decimal(decimal_mean(values), quantum),
            "median": format_decimal(decimal_median(values), quantum),
        }

    return {
        "metric_code": metric_code,
        "value": value,
        "unit": unit,
        "status": status,
        "methodology": methodology,
        "source_timestamp": None,
    }


def build_review_count_distribution(
    review_counts: list[int],
    total_product_count: int,
) -> dict[str, Any]:
    status = coverage_status(len(review_counts), total_product_count)
    decimal_values = [Decimal(value) for value in review_counts]

    value: dict[str, Any] = {
        "observed_count": len(review_counts),
        "total_product_count": total_product_count,
        "coverage_ratio": format_ratio(len(review_counts), total_product_count),
        "min": min(review_counts) if review_counts else None,
        "max": max(review_counts) if review_counts else None,
        "mean": (
            format_decimal(decimal_mean(decimal_values), STAT_QUANT)
            if decimal_values
            else None
        ),
        "median": (
            format_decimal(decimal_median(decimal_values), STAT_QUANT)
            if decimal_values
            else None
        ),
    }

    return {
        "metric_code": "sample_review_count_distribution",
        "value": value,
        "unit": "count",
        "status": status,
        "methodology": (
            "Distribution of rating_number values in the filtered Amazon product "
            "sample. Rating/review counts are sample metadata and are not sales volume."
        ),
        "source_timestamp": None,
    }


def build_review_activity(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    timestamps = [
        parsed
        for review in reviews
        if (parsed := parse_amazon_timestamp(review.get("timestamp"))) is not None
    ]
    total_count = len(reviews)
    dated_count = len(timestamps)

    if dated_count == 0:
        status = "unavailable"
    elif dated_count < total_count:
        status = "partial"
    else:
        status = "available"

    reviews_by_year = Counter(timestamp.year for timestamp in timestamps)
    value = {
        "total_review_count": total_count,
        "dated_review_count": dated_count,
        "timestamp_coverage_ratio": format_ratio(dated_count, total_count),
        "start_date": min(timestamps).date().isoformat() if timestamps else None,
        "end_date": max(timestamps).date().isoformat() if timestamps else None,
        "reviews_by_year": {
            str(year): reviews_by_year[year]
            for year in sorted(reviews_by_year)
        },
    }

    return {
        "metric_code": "sample_review_activity",
        "value": value,
        "unit": "count",
        "status": status,
        "methodology": (
            "Review activity calculated from timestamps in the filtered review sample. "
            "It describes review activity only and must not be interpreted as market "
            "sales growth."
        ),
        "source_timestamp": None,
    }


def build_brand_concentration(products: list[dict[str, Any]]) -> dict[str, Any]:
    brands = [
        brand
        for product in products
        if (brand := optional_text(product.get("brand"))) is not None
    ]
    total_count = len(products)
    branded_count = len(brands)
    coverage = (
        Decimal(branded_count) / Decimal(total_count)
        if total_count
        else Decimal("0")
    )

    counts = Counter(brands)
    ordered = sorted(
        counts.items(),
        key=lambda item: (-item[1], item[0].casefold(), item[0]),
    )

    top_brands = [
        {
            "brand": brand,
            "product_count": count,
            "share_within_branded_sample": format_ratio(count, branded_count),
        }
        for brand, count in ordered[:10]
    ]

    top1_count = sum(count for _, count in ordered[:1])
    top3_count = sum(count for _, count in ordered[:3])

    if branded_count == 0:
        status = "unavailable"
    elif coverage < BRAND_COVERAGE_THRESHOLD:
        status = "partial"
    else:
        status = "available"

    return {
        "metric_code": "sample_brand_concentration",
        "value": {
            "total_product_count": total_count,
            "branded_product_count": branded_count,
            "brand_coverage_ratio": format_decimal(coverage, RATIO_QUANT),
            "distinct_brand_count": len(counts),
            "top1_share": format_ratio(top1_count, branded_count),
            "top3_share": format_ratio(top3_count, branded_count),
            "top_brands": top_brands,
        },
        "unit": "ratio",
        "status": status,
        "methodology": (
            "Brand concentration calculated only from products with a non-empty brand "
            "field; store/shop_name is never used as a brand fallback. Shares use the "
            "branded subset as denominator. The metric is partial when brand coverage "
            f"is below {BRAND_COVERAGE_THRESHOLD:.0%}."
        ),
        "source_timestamp": None,
    }


def unavailable_market_metrics() -> list[dict[str, Any]]:
    return [
        {
            "metric_code": "market_size",
            "value": None,
            "unit": "USD",
            "status": "unavailable",
            "methodology": (
                "Amazon Reviews 2023 does not provide market-wide market size data."
            ),
            "source_timestamp": None,
        },
        {
            "metric_code": "gmv",
            "value": None,
            "unit": "USD",
            "status": "unavailable",
            "methodology": (
                "Amazon Reviews 2023 does not provide market-wide GMV data."
            ),
            "source_timestamp": None,
        },
        {
            "metric_code": "growth",
            "value": None,
            "unit": "percent",
            "status": "unavailable",
            "methodology": (
                "Amazon Reviews 2023 does not provide market-wide sales growth data."
            ),
            "source_timestamp": None,
        },
    ]


def build_market_metrics(dataset_dir: str | Path) -> list[dict[str, Any]]:
    dataset_path = Path(dataset_dir).resolve()
    products = load_jsonl(dataset_path / "products.jsonl")
    reviews = load_jsonl(dataset_path / "reviews.jsonl")

    if not products:
        raise ValueError("products.jsonl must contain at least one product")

    prices = [
        value
        for product in products
        if (value := optional_decimal(product.get("price"))) is not None
        and value >= 0
    ]
    ratings = [
        value
        for product in products
        if (value := optional_decimal(product.get("average_rating"))) is not None
        and value >= 0
    ]
    review_counts = [
        value
        for product in products
        if (value := optional_nonnegative_int(product.get("rating_number"))) is not None
    ]

    metrics = unavailable_market_metrics()
    metrics.extend(
        [
            {
                "metric_code": "sample_product_count",
                "value": len(products),
                "unit": "count",
                "status": "available",
                "methodology": (
                    "Number of products in the filtered Amazon Reviews 2023 product sample."
                ),
                "source_timestamp": None,
            },
            build_decimal_distribution(
                metric_code="sample_price_distribution",
                values=prices,
                total_product_count=len(products),
                unit="USD",
                quantum=MONEY_QUANT,
                methodology=(
                    "Price distribution calculated from non-missing price values in the "
                    "filtered Amazon product sample. It is a sample statistic, not a "
                    "market-wide price distribution."
                ),
            ),
            build_decimal_distribution(
                metric_code="sample_rating_distribution",
                values=ratings,
                total_product_count=len(products),
                unit="rating",
                quantum=STAT_QUANT,
                methodology=(
                    "Rating distribution calculated from non-missing average_rating values "
                    "in the filtered Amazon product sample."
                ),
            ),
            build_review_count_distribution(
                review_counts=review_counts,
                total_product_count=len(products),
            ),
            build_review_activity(reviews),
            build_brand_concentration(products),
        ]
    )
    return metrics


def write_market_metrics(dataset_dir: str | Path, output: str | Path | None = None) -> Path:
    dataset_path = Path(dataset_dir).resolve()
    output_path = Path(output).resolve() if output else dataset_path / "market_metrics.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    metrics = build_market_metrics(dataset_path)
    output_path.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build sample-scoped market metrics from Amazon products.jsonl and reviews.jsonl."
        )
    )
    parser.add_argument(
        "--dataset-dir",
        default=str(DEFAULT_DATASET_DIR),
        help="Dataset directory containing products.jsonl and reviews.jsonl.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON path. Defaults to <dataset-dir>/market_metrics.json.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_path = write_market_metrics(args.dataset_dir, args.output)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
