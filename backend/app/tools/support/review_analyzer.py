from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from app.modules.market_intelligence.schemas.analysis import (
    ReviewInsight,
    ReviewTheme,
)
from app.modules.market_intelligence.schemas.adapter import (
    EvidenceReference,
)
from app.modules.market_intelligence.schemas.common import (
    AnalysisScope,
    DataStatus,
    MetricStatus,
    Sentiment,
)
from app.modules.market_intelligence.schemas.facts import (
    NormalizedReview,
)


@dataclass(frozen=True)
class ReviewAnalysisProgress:
    completed_batches: int
    total_batches: int
    analyzed_reviews: int
    selected_reviews: int
    collected_reviews: int


ReviewProgressCallback = Callable[[ReviewAnalysisProgress], None]


class ReviewAnalyzer(Protocol):
    def analyze(
        self,
        *,
        reviews: list[NormalizedReview],
        evidence_refs: list[EvidenceReference],
        sample_scope: AnalysisScope,
        progress_callback: ReviewProgressCallback | None = None,
    ) -> ReviewInsight:
        ...


class PrecomputedReviewAnalyzer:
    """
    聚合 NormalizedReview 中已经存在的分析标签。

    当前版本不从评论文本自行推断主题、痛点或未满足需求。
    """

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

        evidence_by_review = {
            evidence.review_id: evidence.evidence_id
            for evidence in evidence_refs
            if evidence.review_id is not None
        }

        sentiment_distribution = self._sentiment_distribution(reviews)
        themes = self._build_themes(
            reviews=reviews,
            evidence_by_review=evidence_by_review,
        )
        representative_review_ids = self._representative_review_ids(reviews)
        evidence_ids = [evidence.evidence_id for evidence in evidence_refs]
        status = self._status(reviews)

        insight = ReviewInsight(
            status=status,
            sample_scope=sample_scope,
            sentiment_distribution=sentiment_distribution,
            themes=themes,
            pain_points=[],
            unmet_needs=[],
            representative_review_ids=(
                representative_review_ids
            ),
            evidence_ids=evidence_ids,
        )
        if progress_callback is not None:
            progress_callback(
                ReviewAnalysisProgress(
                    completed_batches=1,
                    total_batches=1,
                    analyzed_reviews=len(reviews),
                    selected_reviews=len(reviews),
                    collected_reviews=len(reviews),
                )
            )
        return insight

    @staticmethod
    def _sentiment_distribution(
        reviews: list[NormalizedReview],
    ) -> dict[str, Decimal | int]:
        counts = Counter(
            review.sentiment.value
            for review in reviews if review.sentiment is not None
        )

        analyzed_count = sum(counts.values())

        result: dict[str, Decimal | int] = {
            "total_count": len(reviews),
            "analyzed_count": analyzed_count,
        }

        if analyzed_count == 0:
            result["coverage_ratio"] = Decimal("0")
        else:
            result["coverage_ratio"] = Decimal(analyzed_count) / Decimal(len(reviews))

        for sentiment in Sentiment:
            count = counts[sentiment.value]
            result[f"{sentiment.value}_count"] = count
            if analyzed_count == 0:
                ratio = Decimal("0")
            else:
                ratio = Decimal(count) / Decimal(analyzed_count)

            result[f"{sentiment.value}_ratio"] = ratio

        return result

    def _build_themes(
        self,
        *,
        reviews: list[NormalizedReview],
        evidence_by_review: dict[str, str],
    ) -> list[ReviewTheme]:
        theme_reviews: dict[str,list[NormalizedReview],] = defaultdict(list)

        for review in reviews:
            # 同一条评论中的重复主题只计算一次
            for theme in set(review.themes):
                theme_reviews[theme].append(review)

        total_reviews = len(reviews)

        result = []

        for theme, matched_reviews in theme_reviews.items():
            representative_reviews = (
                self._sorted_reviews(
                    matched_reviews
                )[:3]
            )

            representative_review_ids = [
                review.review_id
                for review in representative_reviews
            ]

            evidence_ids = [
                evidence_by_review[review.review_id]
                for review in representative_reviews
                if review.review_id in evidence_by_review
            ]

            mention_count = len(matched_reviews)

            result.append(
                ReviewTheme(
                    theme=theme,
                    mention_count=mention_count,
                    mention_ratio=(
                        Decimal(mention_count)
                        / Decimal(total_reviews)
                    ),
                    summary=(
                        f"“{theme}”在 {total_reviews} 条评论中出现 "
                        f"{mention_count} 次。"
                    ),
                    representative_review_ids=(
                        representative_review_ids
                    ),
                    evidence_ids=evidence_ids,
                )
            )

        result.sort(
            key=lambda item: (
                -item.mention_count,
                item.theme.casefold(),
            )
        )

        return result

    def _representative_review_ids(self,reviews: list[NormalizedReview]) -> list[str]:
        return [
            review.review_id for review in self._sorted_reviews(reviews)[:5]
        ]

    @staticmethod
    def _sorted_reviews(reviews: list[NormalizedReview]) -> list[NormalizedReview]:
        return sorted(
            reviews,
            key=lambda review: (
                -(review.helpful_count or 0),
                review.review_id,
            ),
        )

    @staticmethod
    def _status(reviews: list[NormalizedReview]) -> MetricStatus:
        if any(review.data_status is DataStatus.STALE for review in reviews):
            return MetricStatus.STALE

        # 第一版尚未实现完整的文本分析能力
        return MetricStatus.PARTIAL
