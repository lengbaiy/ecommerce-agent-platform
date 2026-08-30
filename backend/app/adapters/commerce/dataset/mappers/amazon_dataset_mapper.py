from datetime import UTC, datetime
from typing import Any, Mapping
from uuid import NAMESPACE_URL, uuid5

from app.adapters.commerce.dataset.mappers.dataset_mapper_base import (
    PlatformDatasetMapper,
    ProductMappingContext,
    ReviewMappingContext,
)

from app.modules.market_intelligence.schemas import (
    NormalizedProduct,
    NormalizedReview,
    ProductSort,
)


class AmazonDatasetMapper(PlatformDatasetMapper):
    platform = "amazon"
    supported_sorts = frozenset(
        {
            ProductSort.DEFAULT,
            ProductSort.PRICE_ASC,
            ProductSort.PRICE_DESC,
        }
    )

    def map_product(
        self,
        raw: Mapping[str, Any],
        context: ProductMappingContext,
    ) -> NormalizedProduct:
        self.validate_record_scope(raw, context)
        product_id = self.required_text(raw.get("parent_asin"), "parent_asin")
        title = self.required_text(raw.get("title"), "title")
        price = self.decimal_value(raw.get("price"), "price", required=True)

        assert price is not None
        categories = raw.get("categories")
        category = (
            self.optional_text(categories[-1])
            if isinstance(categories, list)  and categories
            else self.optional_text(raw.get("main_category"))
        )
        rating = self.decimal_value(raw.get("average_rating"), "average_rating")
        review_count = self.integer_value(raw.get("rating_number"), "rating_number")
        source_ref = self.source_ref(raw, context, product_id)
        return self.build_product(
            context=context,
            source_ref=source_ref,
            product_id=product_id,
            title=title,
            brand=self.optional_text(raw.get("brand")),
            category=category,
            price=price,
            currency=self.optional_text(raw.get("currency")) or "USD",
            shop_name=self.optional_text(raw.get("store")),
            rating=rating,
            review_count=review_count,
            source_url=self.optional_text(raw.get("url")),
        )

    def map_review(
        self,
        raw: Mapping[str, Any],
        context: ReviewMappingContext,
    ) -> NormalizedReview:
        self.validate_record_scope(raw, context)

        product_id = self.required_text(self.first_value(raw, "parent_asin", "asin"), "parent_asin")
        content = self.required_text(self.first_value(raw, "text", "content"), "text")
        rating = self.decimal_value(raw.get("rating"), "rating")
        helpful_count = self.integer_value(self.first_value(raw, "helpful_vote", "helpful_count"), "helpful_vote")
        verified_purchase = self._boolean_value(raw.get("verified_purchase"), "verified_purchase")
        review_time = self._review_time(raw.get("timestamp"))
        review_id = self._review_id(raw=raw, product_id=product_id, content=content)
        source_ref = self.review_source_ref(raw, context, review_id)

        return self.build_review(
            context=context,
            source_ref=source_ref,
            review_id=review_id,
            product_id=product_id,
            content=content,
            rating=rating,
            review_time=review_time,
            verified_purchase=verified_purchase,
            helpful_count=helpful_count,
        )

    def _review_id(
        self,
        *,
        raw: Mapping[str, Any],
        product_id: str,
        content: str,
    ) -> str:
        existing_id = self.optional_text(self.first_value(raw, "review_id", "id",))
        if existing_id is not None:
            return existing_id

        user_id = self.optional_text(raw.get("user_id")) or ""
        timestamp =  self.optional_text(raw.get("timestamp")) or ""
        review_key = (
            f"amazon-review:"
            f"{product_id}:"
            f"{user_id}:"
            f"{timestamp}:"
            f"{content}"
        )
        return str(uuid5(NAMESPACE_URL, review_key))

    @staticmethod
    def _review_time(
        value: Any,
    ) -> datetime | None:
        if value is None:
            return None

        try:
            timestamp = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "timestamp must be an integer"
            ) from exc

        # Amazon Reviews 2023 常见 timestamp 为毫秒
        if timestamp > 10_000_000_000:
            timestamp /= 1000

        return datetime.fromtimestamp(timestamp, tz=UTC)

    @classmethod
    def _boolean_value(
        cls,
        value: Any,
        field_name: str,
    ) -> bool | None:
        if value is None:
            return None

        if isinstance(value, bool):
            return value

        text = cls.optional_text(value)
        if text is None:
            return None

        normalized = text.casefold()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False

        raise ValueError(f"{field_name} must be boolean")