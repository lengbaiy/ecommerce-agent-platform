from typing import Protocol

from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    CollectionRunRecord,
    EvidenceReferenceRecord,
    ProductSnapshotRecord,
    ReviewSnapshotRecord,
)
from app.modules.market_intelligence.schemas import (
    CollectionRun,
    EvidenceReference,
    NormalizedProduct,
    NormalizedReview,
)


class CollectionRepository(Protocol):
    """市场情报采集结果持久化接口。"""

    def save_product_collection(
        self,
        *,
        run: CollectionRun,
        products: list[NormalizedProduct],
        evidence_refs: list[EvidenceReference],
    ) -> None:
        """保存一次完整的商品采集结果。"""
        ...

    def save_review_collection(
        self,
        *,
        run: CollectionRun,
        reviews: list[NormalizedReview],
        evidence_refs: list[EvidenceReference],
    ) -> None:
        """保存一次完整的评论采集结果。"""
        ...


class SQLAlchemyCollectionRepository:
    """基于 SQLAlchemy 的市场情报采集结果持久化实现。"""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
    ) -> None:
        self.session_factory = session_factory

    def save_product_collection(
        self,
        *,
        run: CollectionRun,
        products: list[NormalizedProduct],
        evidence_refs: list[EvidenceReference],
    ) -> None:
        self._validate_product_collection(
            run=run,
            products=products,
            evidence_refs=evidence_refs,
        )

        with self.session_factory() as session:
            with session.begin():
                session.add(
                    self._to_run_record(run)
                )

                session.add_all(
                    [
                        self._to_product_record(
                            product=product,
                            run=run,
                        )
                        for product in products
                    ]
                )

                session.add_all(
                    [
                        self._to_evidence_record(
                            evidence=evidence,
                            run=run,
                        )
                        for evidence in evidence_refs
                    ]
                )

    def save_review_collection(
        self,
        *,
        run: CollectionRun,
        reviews: list[NormalizedReview],
        evidence_refs: list[EvidenceReference],
    ) -> None:
        self._validate_review_collection(
            run=run,
            reviews=reviews,
            evidence_refs=evidence_refs,
        )

        with self.session_factory() as session:
            with session.begin():
                session.add(
                    self._to_run_record(run)
                )

                session.add_all(
                    [
                        self._to_review_record(
                            review=review,
                            run=run,
                        )
                        for review in reviews
                    ]
                )

                session.add_all(
                    [
                        self._to_evidence_record(
                            evidence=evidence,
                            run=run,
                        )
                        for evidence in evidence_refs
                    ]
                )

    @staticmethod
    def _validate_product_collection(
        *,
        run: CollectionRun,
        products: list[NormalizedProduct],
        evidence_refs: list[EvidenceReference],
    ) -> None:
        """校验商品和证据是否归属于当前采集批次。"""

        for product in products:
            if product.collection_run_id != run.id:
                raise ValueError(
                    "product.collection_run_id must match run.id"
                )

        for evidence in evidence_refs:
            if evidence.collection_run_id != run.id:
                raise ValueError(
                    "evidence.collection_run_id must match run.id"
                )

    @staticmethod
    def _validate_review_collection(
        *,
        run: CollectionRun,
        reviews: list[NormalizedReview],
        evidence_refs: list[EvidenceReference],
    ) -> None:
        """校验评论和证据是否归属于当前采集批次。"""

        for review in reviews:
            if review.collection_run_id != run.id:
                raise ValueError(
                    "review.collection_run_id must match run.id"
                )

        for evidence in evidence_refs:
            if evidence.collection_run_id != run.id:
                raise ValueError(
                    "evidence.collection_run_id must match run.id"
                )

    @staticmethod
    def _to_run_record(
        run: CollectionRun,
    ) -> CollectionRunRecord:
        """将采集批次领域模型转换为 ORM 模型。"""

        return CollectionRunRecord(
            id=run.id,
            tenant_id=run.tenant_id,
            trace_id=run.trace_id,
            task_id=run.task_id,
            keyword=run.keyword,
            requested_count=run.requested_count,
            actual_count=run.actual_count,
            status=run.status.value,
            stop_reason=run.stop_reason,
            adapter_version=run.adapter_version,
            parser_version=run.parser_version,
            started_at=run.started_at,
            finished_at=run.finished_at,
        )

    @staticmethod
    def _to_product_record(
        *,
        product: NormalizedProduct,
        run: CollectionRun,
    ) -> ProductSnapshotRecord:
        """将标准商品模型转换为商品快照 ORM 模型。"""

        return ProductSnapshotRecord(
            # 使用 canonical model 中的 snapshot_id 作为数据库主键
            id=product.snapshot_id,
            tenant_id=run.tenant_id,
            trace_id=run.trace_id,
            collection_run_id=product.collection_run_id,
            platform=product.platform,
            market=product.market,
            product_id=product.product_id,
            title=product.title,
            brand=product.brand,
            category=product.category,
            price=product.price,
            currency=product.currency,
            sales_display=product.sales_display,
            sales_value=product.sales_value,
            sales_value_type=product.sales_value_type.value,
            shop_name=product.shop_name,
            rating=product.rating,
            review_count=product.review_count,
            source_ref=product.source_ref,
            source_url=product.source_url,
            source_snapshot_ref=product.source_snapshot_ref,
            source_timestamp=product.source_timestamp,
            ingest_timestamp=product.ingest_timestamp,
            source_type=product.source_type.value,
            data_status=product.data_status.value,
        )

    @staticmethod
    def _to_review_record(
        *,
        review: NormalizedReview,
        run: CollectionRun,
    ) -> ReviewSnapshotRecord:
        """将标准评论模型转换为评论快照 ORM 模型。"""

        return ReviewSnapshotRecord(
            tenant_id=run.tenant_id,
            trace_id=run.trace_id,
            collection_run_id=review.collection_run_id,
            platform=review.platform,
            market=review.market,
            review_id=review.review_id,
            product_id=review.product_id,
            content=review.content,
            rating=review.rating,
            review_time=review.review_time,
            verified_purchase=review.verified_purchase,
            helpful_count=review.helpful_count,
            sentiment=(
                review.sentiment.value
                if review.sentiment is not None
                else None
            ),
            themes=list(review.themes),
            source_ref=review.source_ref,
            source_snapshot_ref=review.source_snapshot_ref,
            source_timestamp=review.source_timestamp,
            ingest_timestamp=review.ingest_timestamp,
            data_status=review.data_status.value,
        )

    @staticmethod
    def _to_evidence_record(
        *,
        evidence: EvidenceReference,
        run: CollectionRun,
    ) -> EvidenceReferenceRecord:
        """将证据引用模型转换为 ORM 模型。"""

        return EvidenceReferenceRecord(
            id=evidence.evidence_id,
            tenant_id=run.tenant_id,
            trace_id=run.trace_id,
            collection_run_id=evidence.collection_run_id,
            evidence_type=evidence.evidence_type.value,
            data_level=evidence.data_level.value,
            data_source=evidence.data_source,
            platform=evidence.platform,
            product_id=evidence.product_id,
            review_id=evidence.review_id,
            query_range=evidence.query_range,
            source_timestamp=evidence.source_timestamp,
            ingest_timestamp=evidence.ingest_timestamp,
            tool_call_id=evidence.tool_call_id,
            snapshot_ref=evidence.snapshot_ref,
            sha256=evidence.sha256,
            data_version=evidence.data_version,
            sample_scope=evidence.sample_scope.model_dump(
                mode="json"
            ),
        )