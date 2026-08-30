from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping
from uuid import NAMESPACE_URL, uuid5

from app.modules.market_intelligence.schemas import (
    DataSourceMode,
    DataStatus,
    DatasetManifest,
    NormalizedProduct,
    NormalizedReview,
    ProductSort,
    SalesValueType,
)


@dataclass(frozen=True)
class ProductMappingContext:
    collection_run_id: str
    manifest: DatasetManifest
    source_timestamp: datetime
    data_status: DataStatus
    source_snapshot_ref: str


@dataclass(frozen=True)
class ReviewMappingContext:
    collection_run_id: str
    manifest: DatasetManifest
    source_timestamp: datetime
    data_status: DataStatus
    source_snapshot_ref: str


class PlatformDatasetMapper(ABC):
    platform: str
    supported_sorts: frozenset[ProductSort] = frozenset({ProductSort.DEFAULT})

    @abstractmethod
    def map_product(
        self,
        raw: Mapping[str, Any],
        context: ProductMappingContext,
    ) -> NormalizedProduct:
        """Convert one platform record to the public product schema."""

    @abstractmethod
    def map_review(
        self,
        raw: Mapping[str, Any],
        context: ReviewMappingContext,
    ) -> NormalizedReview:
        """Convert one platform review record to the public review schema."""

    def supports_sort(self, sort_by: ProductSort) -> bool:
        return sort_by in self.supported_sorts

    def validate_record_scope(
        self,
        raw: Mapping[str, Any],
        context: ProductMappingContext | ReviewMappingContext,
    ) -> None:
        raw_platform = self.optional_text(raw.get("_platform"))
        if (
            raw_platform is not None
            and raw_platform.casefold() != self.platform.casefold()
        ):
            raise ValueError("record platform does not match mapper platform")

        raw_market = self.optional_text(raw.get("_market"))
        if (
            raw_market is not None
            and raw_market.casefold() != context.manifest.market.casefold()
        ):
            raise ValueError("record market does not match dataset manifest")

    def source_ref(
        self,
        raw: Mapping[str, Any],
        context: ProductMappingContext,
        product_id: str,
    ) -> str:
        dataset = self.optional_text(raw.get("_source_dataset"))
        revision = self.optional_text(raw.get("_source_revision"))
        subset = self.optional_text(raw.get("_source_subset"))
        dataset = dataset or context.manifest.dataset_id
        revision = revision or context.manifest.dataset_version
        subset = subset or "products"
        return f"{dataset}@{revision}:{subset}:{self.platform}:{product_id}"

    def review_source_ref(
        self,
        raw: Mapping[str, Any],
        context: ReviewMappingContext,
        review_id: str,
    ) -> str:
        dataset = self.optional_text(raw.get("_source_dataset"))
        revision = self.optional_text(raw.get("_source_revision"))
        subset = self.optional_text(raw.get("_source_subset"))

        dataset = dataset or context.manifest.dataset_id
        revision = revision or context.manifest.dataset_version
        subset = subset or "reviews"

        return (
            f"{dataset}@{revision}:"
            f"{subset}:{self.platform}:{review_id}"
        )

    def build_product(
        self,
        *,
        context: ProductMappingContext,
        source_ref: str,
        product_id: str,
        title: str,
        price: Decimal,
        currency: str,
        brand: str | None = None,
        category: str | None = None,
        sales_display: str | None = None,
        sales_value: int | None = None,
        sales_value_type: SalesValueType = SalesValueType.UNKNOWN,
        shop_name: str | None = None,
        rating: Decimal | None = None,
        review_count: int | None = None,
        source_url: str | None = None,
    ) -> NormalizedProduct:
        
        snapshot_key = f"{context.collection_run_id}:{source_ref}"
        snapshot_id = str(uuid5(NAMESPACE_URL, snapshot_key))

        return NormalizedProduct(
            snapshot_id=snapshot_id,
            collection_run_id=context.collection_run_id,
            platform=self.platform,
            market=context.manifest.market.upper(),
            product_id=product_id,
            title=title,
            brand=brand,
            category=category,
            price=price,
            currency=currency,
            sales_display=sales_display,
            sales_value=sales_value,
            sales_value_type=sales_value_type,
            shop_name=shop_name,
            rating=rating,
            review_count=review_count,
            source_ref=source_ref,
            source_url=source_url,
            source_snapshot_ref=context.source_snapshot_ref,
            source_timestamp=context.source_timestamp,
            source_type=DataSourceMode.FIXED_DATASET,
            data_status=context.data_status,
        )

    def build_review(
        self,
        *,
        context: ReviewMappingContext,
        source_ref: str,
        review_id: str,
        product_id: str,
        content: str,
        rating: Decimal | None = None,
        review_time: datetime | None = None,
        verified_purchase: bool | None = None,
        helpful_count: int | None = None,
    ) -> NormalizedReview:
        return NormalizedReview(
            review_id=review_id,
            collection_run_id=context.collection_run_id,
            platform=self.platform,
            market=context.manifest.market.upper(),
            product_id=product_id,
            content=content,
            rating=rating,
            review_time=review_time,
            verified_purchase=verified_purchase,
            helpful_count=helpful_count,

            # 这里不做评论分析
            sentiment=None,
            themes=[],

            source_ref=source_ref,
            source_snapshot_ref=context.source_snapshot_ref,
            source_timestamp=context.source_timestamp,
            data_status=context.data_status,
        )

    @classmethod
    def first_value(cls, raw: Mapping[str, Any], *field_names: str) -> Any:
        for field_name in field_names:
            value = raw.get(field_name)
            if (
                value is not None
                and cls.optional_text(value) is not None
            ):
                return value
        return None

    @classmethod
    def required_text(cls, value: Any, field_name: str) -> str:
        text = cls.optional_text(value)
        if text is None:
            raise ValueError(f"{field_name} is required")
        return text

    @staticmethod
    def optional_text(value: Any) -> str | None:
        if value is None:
            return None

        text = str(value).strip()
        return text or None

    @classmethod
    def decimal_value(
        cls,
        value: Any,
        field_name: str,
        *,
        required: bool = False,
    ) -> Decimal | None:
        text = cls.optional_text(value)

        if (
            text is None
            or text.casefold() in {"none", "null", "n/a"}
        ):
            if required:
                raise ValueError(f"{field_name} is required")
            return None

        try:
            return Decimal(text.replace(",", ""))
        except InvalidOperation as exc:
            raise ValueError(f"{field_name} must be numeric") from exc

    @classmethod
    def integer_value(cls, value: Any, field_name: str) -> int | None:
        number = cls.decimal_value(value, field_name)
        if number is None:
            return None
        if number != number.to_integral_value():
            raise ValueError(f"{field_name} must be an integer")
        return int(number)
