from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from app.modules.market_intelligence.schemas import (
    AnalysisScope,
    DataSourceMode,
    EvidenceReference,
    EvidenceType,
    MarketMetric,
    MetricStatus,
    NormalizedProduct,
    SalesValueType,
)


MONEY_QUANT = Decimal("0.01")
RATIO_QUANT = Decimal("0.0001")
PRICE_BIN_COUNT = 4
METHODOLOGY_VERSION = "sample-market-v1"
AGGREGATE_MISSING_REASON = "AGGREGATE_MARKET_DATA_MISSING"


class MarketSampleMetricsError(ValueError):
    """商品样本无法按声明口径计算时返回的参数错误。"""


@dataclass(frozen=True)
class MarketSampleMetricsResult:
    metrics: list[MarketMetric]
    evidence_refs: list[EvidenceReference]
    warnings: list[str]
    source_collection_run_ids: list[str]


def build_market_sample_metrics(
    *,
    platform: str,
    market: str,
    category: str,
    keyword: str,
    data_source_mode: DataSourceMode,
    requested_start_time: datetime | None,
    requested_end_time: datetime | None,
    products: list[NormalizedProduct],
    evidence_refs: list[EvidenceReference],
) -> MarketSampleMetricsResult:
    """从 ProductSearchTool 商品样本生成明确标注的样本指标。"""

    _validate_products(products, platform, market, data_source_mode)

    if not products:
        scope = AnalysisScope(
            market=market,
            platforms=[_selector(platform)],
            category=category,
            keyword=keyword,
            start_time=requested_start_time,
            end_time=requested_end_time,
            requested_product_count=0,
            actual_product_count=0,
            actual_review_count=0,
            data_source_mode=data_source_mode,
        )
        return MarketSampleMetricsResult(
            metrics=(
                _unavailable_full_market_metrics(scope, []) + _unavailable_sample_metrics(scope)
            ),
            evidence_refs=[],
            warnings=[
                "未提供商品样本，市场指标和样本指标均不可用。"
            ],
            source_collection_run_ids=[],
        )

    used_evidence_refs = _product_evidence_refs(products, evidence_refs)
    evidence_ids = [evidence.evidence_id for evidence in used_evidence_refs]
    source_timestamps = [product.source_timestamp for product in products]

    try:
        scope_start_time = min(source_timestamps)
        scope_end_time = max(source_timestamps)
    except TypeError as exc:
        raise MarketSampleMetricsError(
            "product source_timestamp values must use compatible timezones"
        ) from exc

    scope = AnalysisScope(
        market=market,
        platforms=[_selector(platform)],
        category=category,
        keyword=keyword,
        start_time=scope_start_time,
        end_time=scope_end_time,
        requested_product_count=len(products),
        actual_product_count=len(products),
        actual_review_count=0,
        data_source_mode=data_source_mode,
    )
    source_timestamp = scope_end_time

    metrics = _unavailable_full_market_metrics(scope, evidence_ids)
    metrics.extend(_sample_metrics(products, scope, evidence_ids, source_timestamp))

    return MarketSampleMetricsResult(
        metrics=metrics,
        evidence_refs=used_evidence_refs,
        warnings=[
            "缺少全市场汇总数据，当前指标仅描述已提供的商品样本。"
        ],
        source_collection_run_ids=sorted({product.collection_run_id for product in products}),
    )


def _validate_products(
    products: list[NormalizedProduct], platform: str, market: str,
    data_source_mode: DataSourceMode,
) -> None:
    product_ids = [product.product_id for product in products]
    if len(product_ids) != len(set(product_ids)):
        raise MarketSampleMetricsError("products must not contain duplicate product_id")

    expected_platform = _selector(platform)
    expected_market = _selector(market)
    for product in products:
        if _selector(product.platform) != expected_platform:
            raise MarketSampleMetricsError(
                f"product {product.product_id} does not match platform {platform}"
            )
        if _selector(product.market) != expected_market:
            raise MarketSampleMetricsError(
                f"product {product.product_id} does not match market {market}"
            )
        if product.source_type is not data_source_mode:
            raise MarketSampleMetricsError(
                f"product {product.product_id} does not match data_source_mode "
                f"{data_source_mode.value}"
            )


def _product_evidence_refs(
    products: list[NormalizedProduct], evidence_refs: list[EvidenceReference]
) -> list[EvidenceReference]:
    product_ids = {product.product_id for product in products}
    evidence_by_product = {product_id: [] for product_id in product_ids}

    for evidence in evidence_refs:
        if (
            evidence.evidence_type is EvidenceType.PRODUCT
            and evidence.product_id in evidence_by_product
        ):
            evidence_by_product[evidence.product_id].append(evidence)

    missing_product_ids = sorted(
        product_id for product_id, matches in evidence_by_product.items() if not matches
    )
    if missing_product_ids:
        missing = ", ".join(missing_product_ids)
        raise MarketSampleMetricsError(f"product evidence is required for product_id: {missing}")

    used_evidence_ids: set[str] = set()
    used_evidence_refs: list[EvidenceReference] = []
    for evidence in evidence_refs:
        if (
            evidence.evidence_type is EvidenceType.PRODUCT
            and evidence.product_id in product_ids
            and evidence.evidence_id not in used_evidence_ids
        ):
            used_evidence_ids.add(evidence.evidence_id)
            used_evidence_refs.append(evidence)

    return used_evidence_refs


def _unavailable_full_market_metrics(
    scope: AnalysisScope, evidence_ids: list[str]
) -> list[MarketMetric]:
    definitions = (
        ("market_size", None),
        ("gmv", None),
        ("growth", "ratio"),
        ("price_distribution", None),
        ("brand_concentration", "ratio"),
        ("product_concentration", "ratio"),
    )
    methodology = (
        f"{AGGREGATE_MISSING_REASON}：商品样本无法推导全市场指标。"
        f"方法版本={METHODOLOGY_VERSION}。"
    )
    return [
        MarketMetric(
            metric_code=metric_code,
            value=None,
            unit=unit,
            status=MetricStatus.UNAVAILABLE,
            reason_code=AGGREGATE_MISSING_REASON,
            scope=scope,
            methodology=methodology,
            evidence_ids=evidence_ids,
            source_timestamp=scope.end_time,
        )
        for metric_code, unit in definitions
    ]


def _unavailable_sample_metrics(scope: AnalysisScope) -> list[MarketMetric]:
    definitions = (
        ("sample_product_count", "count"),
        ("sample_min_price", None),
        ("sample_max_price", None),
        ("sample_median_price", None),
        ("sample_price_distribution", None),
        ("sample_sales_display_distribution", "count"),
        ("sample_shop_concentration", "ratio"),
        ("sample_product_concentration", "ratio"),
    )
    methodology = (
        "未提供商品样本，因此该样本指标不可用。"
        f"方法版本={METHODOLOGY_VERSION}。"
    )
    return [
        MarketMetric(
            metric_code=metric_code,
            value=None,
            unit=unit,
            status=MetricStatus.UNAVAILABLE,
            scope=scope,
            methodology=methodology,
            evidence_ids=[],
            source_timestamp=None,
        )
        for metric_code, unit in definitions
    ]


def _sample_metrics(
    products: list[NormalizedProduct], scope: AnalysisScope,
    evidence_ids: list[str], source_timestamp: datetime,
) -> list[MarketMetric]:
    metrics = [
        MarketMetric(
            metric_code="sample_product_count",
            value=len(products),
            unit="count",
            status=MetricStatus.AVAILABLE,
            scope=scope,
            methodology=(
                "统计商品样本中去重后的商品数量。"
                f"方法版本={METHODOLOGY_VERSION}。"
            ),
            evidence_ids=evidence_ids,
            source_timestamp=source_timestamp,
        )
    ]
    metrics.extend(_price_metrics(products, scope, evidence_ids, source_timestamp))
    metrics.append(_sales_display_distribution(products, scope, evidence_ids, source_timestamp))
    metrics.append(_shop_concentration(products, scope, evidence_ids, source_timestamp))
    metrics.append(_product_concentration(products, scope, evidence_ids, source_timestamp))
    return metrics


def _price_metrics(
    products: list[NormalizedProduct], scope: AnalysisScope,
    evidence_ids: list[str], source_timestamp: datetime,
) -> list[MarketMetric]:
    currencies = sorted({product.currency for product in products})
    metric_codes = (
        "sample_min_price",
        "sample_max_price",
        "sample_median_price",
        "sample_price_distribution",
    )

    if len(currencies) != 1:
        methodology = (
            "PRICE_CURRENCY_CONFLICT：不同币种的价格未合并计算。"
            f"币种={','.join(currencies)}；方法版本={METHODOLOGY_VERSION}。"
        )
        return [
            MarketMetric(
                metric_code=metric_code,
                value=None,
                unit=None,
                status=MetricStatus.CONFLICT,
                scope=scope,
                methodology=methodology,
                evidence_ids=evidence_ids,
                source_timestamp=source_timestamp,
            )
            for metric_code in metric_codes
        ]

    currency = currencies[0]
    prices = sorted(product.price for product in products)
    median = _median(prices)
    common_methodology = (
        "基于商品样本价格使用 Decimal 精确计算。"
        f"方法版本={METHODOLOGY_VERSION}。"
    )
    distribution = {
        "observed_count": len(prices),
        "currency": currency,
        "binning_algorithm": "four_equal_width_bins",
        "bins": _price_bins(prices),
    }

    return [
        MarketMetric(
            metric_code="sample_min_price",
            value=min(prices).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP),
            unit=currency,
            status=MetricStatus.AVAILABLE,
            scope=scope,
            methodology=common_methodology,
            evidence_ids=evidence_ids,
            source_timestamp=source_timestamp,
        ),
        MarketMetric(
            metric_code="sample_max_price",
            value=max(prices).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP),
            unit=currency,
            status=MetricStatus.AVAILABLE,
            scope=scope,
            methodology=common_methodology,
            evidence_ids=evidence_ids,
            source_timestamp=source_timestamp,
        ),
        MarketMetric(
            metric_code="sample_median_price",
            value=median.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP),
            unit=currency,
            status=MetricStatus.AVAILABLE,
            scope=scope,
            methodology=(
                "对样本价格排序后计算中位数；样本数为偶数时取中间两项平均值。"
                f"方法版本={METHODOLOGY_VERSION}。"
            ),
            evidence_ids=evidence_ids,
            source_timestamp=source_timestamp,
        ),
        MarketMetric(
            metric_code="sample_price_distribution",
            value=distribution,
            unit=currency,
            status=MetricStatus.AVAILABLE,
            scope=scope,
            methodology=(
                "在样本最低价与最高价之间划分四个等宽区间；前三个区间不含上界，"
                "最后一个区间包含上界。"
                f"方法版本={METHODOLOGY_VERSION}。"
            ),
            evidence_ids=evidence_ids,
            source_timestamp=source_timestamp,
        ),
    ]


def _price_bins(prices: list[Decimal]) -> list[dict[str, object]]:
    minimum = min(prices)
    maximum = max(prices)
    if minimum == maximum:
        return [
            {
                "lower": _decimal_text(minimum),
                "upper": _decimal_text(maximum),
                "upper_inclusive": True,
                "count": len(prices),
            }
        ]

    width = (maximum - minimum) / Decimal(PRICE_BIN_COUNT)
    counts = [0] * PRICE_BIN_COUNT
    for price in prices:
        index = int((price - minimum) / width)
        counts[min(index, PRICE_BIN_COUNT - 1)] += 1

    bins: list[dict[str, object]] = []
    for index, count in enumerate(counts):
        lower = minimum + width * Decimal(index)
        upper = (
            maximum
            if index == PRICE_BIN_COUNT - 1
            else minimum + width * Decimal(index + 1)
        )
        bins.append(
            {
                "lower": _decimal_text(lower, Decimal("0.0001")),
                "upper": _decimal_text(upper, Decimal("0.0001")),
                "upper_inclusive": index == PRICE_BIN_COUNT - 1,
                "count": count,
            }
        )
    return bins


def _sales_display_distribution(
    products: list[NormalizedProduct], scope: AnalysisScope,
    evidence_ids: list[str], source_timestamp: datetime,
) -> MarketMetric:
    counts = Counter((p.sales_value_type.value, p.sales_display) for p in products)
    rows = [
        {
            "sales_value_type": sales_value_type,
            "sales_display": sales_display,
            "product_count": count,
        }
        for (sales_value_type, sales_display), count in sorted(
            counts.items(),
            key=lambda item: (item[0][0], item[0][1] or ""),
        )
    ]
    return MarketMetric(
        metric_code="sample_sales_display_distribution",
        value=rows,
        unit="count",
        status=MetricStatus.AVAILABLE,
        scope=scope,
        methodology=(
            "按 sales_value_type 统计原始销量展示文本，不将展示值换算为精确销量。"
            f"方法版本={METHODOLOGY_VERSION}。"
        ),
        evidence_ids=evidence_ids,
        source_timestamp=source_timestamp,
    )


def _shop_concentration(
    products: list[NormalizedProduct], scope: AnalysisScope,
    evidence_ids: list[str], source_timestamp: datetime,
) -> MarketMetric:
    shops = [product.shop_name for product in products if product.shop_name]
    methodology = (
        "店铺集中度按样本内商品数量计算，占比以店铺名称有效的商品数为分母。"
        f"方法版本={METHODOLOGY_VERSION}。"
    )
    if not shops:
        return MarketMetric(
            metric_code="sample_shop_concentration",
            value=None,
            unit="ratio",
            status=MetricStatus.UNAVAILABLE,
            scope=scope,
            methodology=methodology,
            evidence_ids=evidence_ids,
            source_timestamp=source_timestamp,
        )

    counts = Counter(shops)
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold(), item[0]))
    observed_count = len(shops)
    status = MetricStatus.AVAILABLE if observed_count == len(products) else MetricStatus.PARTIAL
    return MarketMetric(
        metric_code="sample_shop_concentration",
        value={
            "observed_product_count": observed_count,
            "total_product_count": len(products),
            "coverage_ratio": _ratio_text(observed_count, len(products)),
            "distinct_shop_count": len(ordered),
            "top1_share": _ratio_text(
                sum(count for _, count in ordered[:1]),
                observed_count,
            ),
            "top3_share": _ratio_text(
                sum(count for _, count in ordered[:3]),
                observed_count,
            ),
            "top_shops": [
                {
                    "shop_name": shop_name,
                    "product_count": count,
                    "share": _ratio_text(count, observed_count),
                }
                for shop_name, count in ordered[:10]
            ],
        },
        unit="ratio",
        status=status,
        scope=scope,
        methodology=methodology,
        evidence_ids=evidence_ids,
        source_timestamp=source_timestamp,
    )


def _product_concentration(
    products: list[NormalizedProduct], scope: AnalysisScope,
    evidence_ids: list[str], source_timestamp: datetime,
) -> MarketMetric:
    exact_sales = [
        product for product in products
        if product.sales_value_type is SalesValueType.EXACT and product.sales_value is not None
    ]
    methodology = (
        "商品集中度仅使用精确销量记录计算，下限值、区间值和未知值不计入总量。"
        f"方法版本={METHODOLOGY_VERSION}。"
    )
    total_exact_sales = sum((product.sales_value or 0) for product in exact_sales)
    if not exact_sales or total_exact_sales <= 0:
        return MarketMetric(
            metric_code="sample_product_concentration",
            value=None,
            unit="ratio",
            status=MetricStatus.UNAVAILABLE,
            scope=scope,
            methodology=methodology,
            evidence_ids=evidence_ids,
            source_timestamp=source_timestamp,
        )

    ordered = sorted(
        exact_sales, key=lambda product: (-(product.sales_value or 0), product.product_id)
    )
    status = MetricStatus.AVAILABLE if len(exact_sales) == len(products) else MetricStatus.PARTIAL
    return MarketMetric(
        metric_code="sample_product_concentration",
        value={
            "exact_sales_product_count": len(exact_sales),
            "total_product_count": len(products),
            "exact_sales_coverage_ratio": _ratio_text(len(exact_sales), len(products)),
            "exact_sales_total": total_exact_sales,
            "top1_share": _ratio_text(
                sum((product.sales_value or 0) for product in ordered[:1]),
                total_exact_sales,
            ),
            "top3_share": _ratio_text(
                sum((product.sales_value or 0) for product in ordered[:3]),
                total_exact_sales,
            ),
            "top_products": [
                {
                    "product_id": product.product_id,
                    "sales_value": product.sales_value,
                    "share": _ratio_text(product.sales_value or 0, total_exact_sales),
                }
                for product in ordered[:10]
            ],
        },
        unit="ratio",
        status=status,
        scope=scope,
        methodology=methodology,
        evidence_ids=evidence_ids,
        source_timestamp=source_timestamp,
    )


def _median(values: list[Decimal]) -> Decimal:
    midpoint = len(values) // 2
    if len(values) % 2:
        return values[midpoint]
    return (values[midpoint - 1] + values[midpoint]) / Decimal("2")


def _ratio_text(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return _decimal_text(Decimal("0"), RATIO_QUANT)
    return _decimal_text(Decimal(numerator) / Decimal(denominator), RATIO_QUANT)


def _decimal_text(value: Decimal, quantum: Decimal = MONEY_QUANT) -> str:
    return str(value.quantize(quantum, rounding=ROUND_HALF_UP))


def _selector(value: str) -> str:
    return " ".join(value.casefold().split())
