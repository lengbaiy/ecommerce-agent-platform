from collections import Counter, defaultdict
from decimal import Decimal

from pydantic import Field

from app.llm.contracts import LLMMessage, StructuredLLMClient
from app.modules.market_intelligence.schemas.adapter import EvidenceReference
from app.modules.market_intelligence.schemas.analysis import ReviewInsight, ReviewTheme
from app.modules.market_intelligence.schemas.common import (
    AnalysisScope,
    DataStatus,
    MarketIntelligenceModel,
    MetricStatus,
    NonEmptyStr,
    Sentiment,
)
from app.modules.market_intelligence.schemas.facts import NormalizedReview
from app.prompts.market_intelligence import build_review_analysis_prompt
from app.tools.support.review_analyzer import (
    ReviewAnalysisProgress,
    ReviewProgressCallback,
)


class ReviewSemanticExtraction(MarketIntelligenceModel):
    review_id: NonEmptyStr
    sentiment: Sentiment
    themes: list[NonEmptyStr] = Field(default_factory=list)
    pain_points: list[NonEmptyStr] = Field(default_factory=list)
    unmet_needs: list[NonEmptyStr] = Field(default_factory=list)


class ReviewSemanticExtractionBatch(MarketIntelligenceModel):
    reviews: list[ReviewSemanticExtraction] = Field(min_length=1)


class ReviewAnalysisError(RuntimeError):
    pass


class LLMReviewAnalyzer:
    """Extract review semantics with an LLM and aggregate them deterministically."""

    def __init__(
        self,
        *,
        client: StructuredLLMClient,
        batch_size: int,
        max_content_chars: int,
        output_language: str,
        max_reviews: int = 60,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        if max_reviews < 1:
            raise ValueError("max_reviews must be positive")
        if max_content_chars < 1:
            raise ValueError("max_content_chars must be positive")
        if not output_language.strip():
            raise ValueError("output_language is required")

        self.client = client
        self.batch_size = batch_size
        self.max_reviews = max_reviews
        self.max_content_chars = max_content_chars
        self.output_language = output_language.strip()

    def analyze(
        self,
        *,
        reviews: list[NormalizedReview],
        evidence_refs: list[EvidenceReference],
        sample_scope: AnalysisScope,
        progress_callback: ReviewProgressCallback | None = None,
    ) -> ReviewInsight:
        if not reviews:
            return ReviewInsight(
                status=MetricStatus.UNAVAILABLE,
                sample_scope=sample_scope,
            )

        analyzed_reviews = self._select_reviews(reviews)
        evidence_by_review = {
            evidence.review_id: evidence.evidence_id
            for evidence in evidence_refs
            if evidence.review_id is not None
        }
        missing_evidence = {
            review.review_id for review in analyzed_reviews
        } - evidence_by_review.keys()
        if missing_evidence:
            raise ReviewAnalysisError(
                "Every analyzed review must have an evidence reference."
            )

        extractions_by_review: dict[str, ReviewSemanticExtraction] = {}
        total_batches = (
            len(analyzed_reviews) + self.batch_size - 1
        ) // self.batch_size
        for batch_index, offset in enumerate(
            range(0, len(analyzed_reviews), self.batch_size),
            start=1,
        ):
            batch = analyzed_reviews[offset : offset + self.batch_size]
            extraction_batch = self._extract_batch(batch)
            self._validate_extraction_batch(
                reviews=batch,
                extraction_batch=extraction_batch,
            )
            extractions_by_review.update(
                {
                    extraction.review_id: extraction
                    for extraction in extraction_batch.reviews
                }
            )
            if progress_callback is not None:
                progress_callback(
                    ReviewAnalysisProgress(
                        completed_batches=batch_index,
                        total_batches=total_batches,
                        analyzed_reviews=min(
                            offset + len(batch), len(analyzed_reviews)
                        ),
                        selected_reviews=len(analyzed_reviews),
                        collected_reviews=len(reviews),
                    )
                )

        sentiment_distribution = self._sentiment_distribution(
            reviews=reviews,
            extractions_by_review=extractions_by_review,
        )
        themes = self._build_topic_groups(
            reviews=analyzed_reviews,
            labels_by_review={
                review_id: extraction.themes
                for review_id, extraction in extractions_by_review.items()
            },
            evidence_by_review=evidence_by_review,
            summary_verb="appears",
        )
        pain_points = self._build_topic_groups(
            reviews=analyzed_reviews,
            labels_by_review={
                review_id: extraction.pain_points
                for review_id, extraction in extractions_by_review.items()
            },
            evidence_by_review=evidence_by_review,
            summary_verb="is reported",
        )
        unmet_needs = self._build_topic_groups(
            reviews=analyzed_reviews,
            labels_by_review={
                review_id: extraction.unmet_needs
                for review_id, extraction in extractions_by_review.items()
            },
            evidence_by_review=evidence_by_review,
            summary_verb="is requested",
        )

        return ReviewInsight(
            status=self._status(reviews, analyzed_reviews),
            sample_scope=sample_scope,
            sentiment_distribution=sentiment_distribution,
            themes=themes,
            pain_points=pain_points,
            unmet_needs=unmet_needs,
            representative_review_ids=[
                review.review_id
                for review in self._sorted_reviews(analyzed_reviews)[:5]
            ],
            evidence_ids=[
                evidence_by_review[review.review_id]
                for review in analyzed_reviews
            ],
        )

    def _select_reviews(
        self,
        reviews: list[NormalizedReview],
    ) -> list[NormalizedReview]:
        if len(reviews) <= self.max_reviews:
            return list(reviews)

        # 商品间轮询取样，商品内优先保留 helpful_count 较高的评论。
        reviews_by_product: dict[str, list[NormalizedReview]] = defaultdict(list)
        for review in reviews:
            reviews_by_product[review.product_id].append(review)
        for product_reviews in reviews_by_product.values():
            product_reviews.sort(
                key=lambda review: (
                    -(review.helpful_count or 0),
                    review.review_id,
                )
            )

        selected: list[NormalizedReview] = []
        product_ids = sorted(reviews_by_product)
        round_index = 0
        while len(selected) < self.max_reviews:
            added = False
            for product_id in product_ids:
                product_reviews = reviews_by_product[product_id]
                if round_index >= len(product_reviews):
                    continue
                selected.append(product_reviews[round_index])
                added = True
                if len(selected) == self.max_reviews:
                    return selected
            if not added:
                break
            round_index += 1
        return selected

    def _extract_batch(
        self,
        reviews: list[NormalizedReview],
    ) -> ReviewSemanticExtractionBatch:
        payload = [
            {
                "review_id": review.review_id,
                "product_id": review.product_id,
                "content": review.content[: self.max_content_chars],
                "rating": str(review.rating) if review.rating is not None else None,
                "verified_purchase": review.verified_purchase,
                "helpful_count": review.helpful_count,
            }
            for review in reviews
        ]
        system_prompt, user_prompt = build_review_analysis_prompt(
            payload,
            output_language=self.output_language,
        )
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt),
        ]

        return self.client.generate_structured(
            messages=messages,
            response_model=ReviewSemanticExtractionBatch,
        )

    @staticmethod
    def _validate_extraction_batch(
        *,
        reviews: list[NormalizedReview],
        extraction_batch: ReviewSemanticExtractionBatch,
    ) -> None:
        expected_ids = {review.review_id for review in reviews}
        actual_ids = [
            extraction.review_id
            for extraction in extraction_batch.reviews
        ]
        if len(actual_ids) != len(set(actual_ids)):
            raise ReviewAnalysisError(
                "LLM review extraction contains duplicate review_id values."
            )
        if set(actual_ids) != expected_ids:
            raise ReviewAnalysisError(
                "LLM review extraction does not match the requested review IDs."
            )

    @staticmethod
    def _sentiment_distribution(
        *,
        reviews: list[NormalizedReview],
        extractions_by_review: dict[str, ReviewSemanticExtraction],
    ) -> dict[str, Decimal | int]:
        counts = Counter(
            extraction.sentiment.value
            for extraction in extractions_by_review.values()
        )
        total_count = len(reviews)
        analyzed_count = len(extractions_by_review)
        result: dict[str, Decimal | int] = {
            "total_count": total_count,
            "analyzed_count": analyzed_count,
            "coverage_ratio": (
                Decimal(analyzed_count) / Decimal(total_count)
            ),
        }

        for sentiment in Sentiment:
            count = counts[sentiment.value]
            result[f"{sentiment.value}_count"] = count
            result[f"{sentiment.value}_ratio"] = (
                Decimal(count) / Decimal(analyzed_count)
            )

        return result

    def _build_topic_groups(
        self,
        *,
        reviews: list[NormalizedReview],
        labels_by_review: dict[str, list[str]],
        evidence_by_review: dict[str, str],
        summary_verb: str,
    ) -> list[ReviewTheme]:
        reviews_by_id = {
            review.review_id: review
            for review in reviews
        }
        label_reviews: dict[str, list[NormalizedReview]] = defaultdict(list)
        display_labels: dict[str, str] = {}

        for review_id, labels in labels_by_review.items():
            seen_keys: set[str] = set()
            for label in labels:
                key = label.casefold()
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                display_labels.setdefault(key, label)
                label_reviews[key].append(reviews_by_id[review_id])

        total_reviews = len(reviews)
        result: list[ReviewTheme] = []

        for key, matched_reviews in label_reviews.items():
            representative_reviews = self._sorted_reviews(matched_reviews)[:3]
            label = display_labels[key]
            mention_count = len(matched_reviews)
            result.append(
                ReviewTheme(
                    theme=label,
                    mention_count=mention_count,
                    mention_ratio=(
                        Decimal(mention_count) / Decimal(total_reviews)
                    ),
                    summary=self._summary(
                        label,
                        summary_verb,
                        mention_count,
                        total_reviews,
                    ),
                    representative_review_ids=[
                        review.review_id
                        for review in representative_reviews
                    ],
                    evidence_ids=[
                        evidence_by_review[review.review_id]
                        for review in representative_reviews
                    ],
                )
            )

        result.sort(
            key=lambda item: (
                -item.mention_count,
                item.theme.casefold(),
            )
        )
        return result

    @staticmethod
    def _summary(
        label: str,
        summary_verb: str,
        mention_count: int,
        total_reviews: int,
    ) -> str:
        if summary_verb == "is reported":
            return f"{total_reviews} 条评论中有 {mention_count} 条提到“{label}”问题。"
        if summary_verb == "is requested":
            return f"{total_reviews} 条评论中有 {mention_count} 条表达了“{label}”需求。"
        return f"“{label}”在 {total_reviews} 条评论中出现 {mention_count} 次。"

    @staticmethod
    def _sorted_reviews(
        reviews: list[NormalizedReview],
    ) -> list[NormalizedReview]:
        return sorted(
            reviews,
            key=lambda review: (
                -(review.helpful_count or 0),
                review.review_id,
            ),
        )

    @staticmethod
    def _status(
        reviews: list[NormalizedReview],
        analyzed_reviews: list[NormalizedReview],
    ) -> MetricStatus:
        if len(analyzed_reviews) < len(reviews):
            return MetricStatus.PARTIAL
        if any(
            review.data_status is DataStatus.STALE
            for review in analyzed_reviews
        ):
            return MetricStatus.STALE
        return MetricStatus.AVAILABLE
