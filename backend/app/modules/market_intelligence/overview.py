import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.commerce import CommerceAdapterRegistry
from app.adapters.commerce.dataset import DatasetRegistry
from app.domain import AgentTask, TaskEventType, TaskStatus
from app.modules.market_intelligence.schemas import DataSourceMode, MarketIntelligenceReport
from app.repositories import TaskRepository
from app.repositories.market_metric_repository import MarketMetricRepository


class MarketDatasetOverview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: str
    platform: str
    market: str
    category: str
    display_name: str
    keyword: str
    aliases: list[str]
    product_count: int = Field(ge=0)
    review_count: int = Field(ge=0)
    available_metric_count: int = Field(ge=0)
    partial_metric_count: int = Field(ge=0)
    unavailable_metric_count: int = Field(ge=0)
    profit_input_available: bool
    source_timestamp: datetime


class MarketAssessmentOverview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str
    report_id: str
    report_status: str
    decision: str
    summary: str
    generated_at: datetime


class MarketTaskOverview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str
    status: str
    query: str
    current_step: str | None
    created_at: datetime
    completed_at: datetime | None


class MarketPipelineStage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    label: str
    description: str
    nodes: list[str]
    status: Literal["pending", "running", "completed", "partial", "failed"]


class MarketOverview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    market: str
    generated_at: datetime
    monitored_category_count: int = Field(ge=0)
    fixed_dataset_count: int = Field(ge=0)
    connected_official_platform_count: int = Field(ge=0)
    approved_market_metric_batch_count: int = Field(ge=0)
    available_market_metric_count: int = Field(ge=0)
    available_metric_count: int = Field(ge=0)
    partial_metric_count: int = Field(ge=0)
    profit_ready_dataset_count: int = Field(ge=0)
    datasets: list[MarketDatasetOverview]
    latest_assessment: MarketAssessmentOverview | None
    latest_task: MarketTaskOverview | None
    recent_tasks: list[MarketTaskOverview]
    pipeline: list[MarketPipelineStage]


class MarketOverviewService:
    """从有效数据集和租户任务中聚合市场概览，不生成模拟指标。"""

    _PIPELINE = (
        (
            "market_scan",
            "类目扫描",
            "校验输入并构建市场指标快照。",
            ("validate_input", "build_market_snapshot"),
        ),
        (
            "competitor_analysis",
            "竞品拆解",
            "采集商品样本并生成竞品矩阵。",
            ("search_products", "build_competitor_matrix"),
        ),
        (
            "review_analysis",
            "评论洞察",
            "分析评论情感、主题、痛点与未满足需求。",
            ("analyze_reviews",),
        ),
        (
            "profit_analysis",
            "利润约束",
            "使用确定性计算检查利润和最低毛利要求。",
            ("calculate_profit",),
        ),
        (
            "report_synthesis",
            "机会评审",
            "合成报告、校验证据并持久化结果。",
            ("synthesize_report", "validate_evidence", "persist_result"),
        ),
    )

    def __init__(
        self,
        registry: DatasetRegistry,
        task_repository: TaskRepository,
        commerce_registry: CommerceAdapterRegistry,
        market_metric_repository: MarketMetricRepository,
    ) -> None:
        self._registry = registry
        self._tasks = task_repository
        self._commerce = commerce_registry
        self._market_metrics = market_metric_repository

    def overview(
        self,
        tenant_id: str,
        market: str = "US",
        category: str | None = None,
    ) -> MarketOverview:
        candidates = [
            entry
            for entry in self._registry.all()
            if entry.manifest.market.casefold() == market.casefold()
            and (category is None or entry.manifest.category.casefold() == category.casefold())
        ]
        entries_by_scope = {}
        for entry in candidates:
            scope = (
                entry.manifest.platform.casefold(),
                entry.manifest.market.casefold(),
                entry.manifest.category.casefold(),
                entry.manifest.keyword.casefold(),
            )
            current = entries_by_scope.get(scope)
            if current is None or entry.manifest.source_timestamp > current.manifest.source_timestamp:
                entries_by_scope[scope] = entry
        entries = list(entries_by_scope.values())
        datasets = [self._dataset_overview(entry.dataset_dir, entry.manifest) for entry in entries]
        market_tasks = [
            task
            for task in self._tasks.list(tenant_id, limit=100)
            if task.request.intent == "market_entry"
            and self._task_matches(task, market, category)
        ]
        latest_task = market_tasks[0] if market_tasks else None
        latest_report = self._latest_report(market_tasks)
        metric_stats = self._market_metrics.overview_stats(
            tenant_id=tenant_id,
            market=market,
        )

        return MarketOverview(
            market=market,
            generated_at=datetime.now(UTC),
            monitored_category_count=len({item.category.casefold() for item in datasets}),
            fixed_dataset_count=len(datasets),
            connected_official_platform_count=self._official_platform_count(tenant_id),
            approved_market_metric_batch_count=metric_stats.approved_batch_count,
            available_market_metric_count=metric_stats.available_metric_count,
            available_metric_count=sum(item.available_metric_count for item in datasets),
            partial_metric_count=sum(item.partial_metric_count for item in datasets),
            profit_ready_dataset_count=sum(item.profit_input_available for item in datasets),
            datasets=datasets,
            latest_assessment=self._assessment(latest_report),
            latest_task=self._task(latest_task),
            recent_tasks=[self._task(task) for task in market_tasks[:5]],
            pipeline=self._pipeline(latest_task),
        )

    def _official_platform_count(self, tenant_id: str) -> int:
        platforms: set[str] = set()
        for adapter in self._commerce.all():
            if adapter.data_source_mode != DataSourceMode.OFFICIAL_API.value:
                continue
            if not adapter.capabilities().supports_products:
                continue
            authorization_check = getattr(adapter, "is_authorized", None)
            if callable(authorization_check) and authorization_check(tenant_id):
                platforms.add(adapter.platform.casefold())
        return len(platforms)

    @staticmethod
    def _line_count(path: Path) -> int:
        if not path.is_file():
            return 0
        with path.open("r", encoding="utf-8") as stream:
            return sum(1 for line in stream if line.strip())

    @staticmethod
    def _json(path: Path, default):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default

    def _dataset_overview(self, dataset_dir: Path, manifest) -> MarketDatasetOverview:
        metrics = self._json(dataset_dir / "market_metrics.json", [])
        metrics = metrics if isinstance(metrics, list) else []
        statuses = [item.get("status") for item in metrics if isinstance(item, dict)]
        profit_inputs = self._json(dataset_dir / "profit_inputs.json", [])
        return MarketDatasetOverview(
            dataset_id=manifest.dataset_id,
            platform=manifest.platform,
            market=manifest.market,
            category=manifest.category,
            display_name=next(
                (
                    alias
                    for alias in manifest.aliases
                    if any(ord(character) > 127 for character in alias)
                ),
                manifest.category,
            ),
            keyword=manifest.keyword,
            aliases=list(manifest.aliases),
            product_count=self._line_count(dataset_dir / "products.jsonl"),
            review_count=self._line_count(dataset_dir / "reviews.jsonl"),
            available_metric_count=statuses.count("available"),
            partial_metric_count=statuses.count("partial"),
            unavailable_metric_count=statuses.count("unavailable"),
            profit_input_available=bool(profit_inputs),
            source_timestamp=manifest.source_timestamp,
        )

    @staticmethod
    def _report(task: AgentTask) -> MarketIntelligenceReport | None:
        if task.result is None:
            return None
        raw = task.result.payload.get("market_intelligence_report")
        if raw is None:
            return None
        try:
            return MarketIntelligenceReport.model_validate(raw)
        except ValueError:
            return None

    @staticmethod
    def _task_matches(task: AgentTask, market: str, category: str | None) -> bool:
        context = task.request.business_context
        raw = context.get("market_intelligence_request")
        if not isinstance(raw, dict):
            raw = context  # 兼容早期任务将 market/category 直接存放在 business_context 的结构。
        task_market = raw.get("market")
        task_category = raw.get("category")
        if not isinstance(task_market, str) or task_market.casefold() != market.casefold():
            return False
        return category is None or (
            isinstance(task_category, str) and task_category.casefold() == category.casefold()
        )

    def _latest_report(
        self,
        tasks: list[AgentTask],
    ) -> tuple[AgentTask, MarketIntelligenceReport] | None:
        for task in tasks:
            report = self._report(task)
            if report is not None:
                return task, report
        return None

    @staticmethod
    def _assessment(
        latest: tuple[AgentTask, MarketIntelligenceReport] | None,
    ) -> MarketAssessmentOverview | None:
        if latest is None:
            return None
        task, report = latest
        return MarketAssessmentOverview(
            task_id=str(task.id),
            report_id=report.report_id,
            report_status=report.status.value,
            decision=report.entry_assessment.decision.value,
            summary=report.entry_assessment.summary,
            generated_at=report.generated_at,
        )

    @staticmethod
    def _task(task: AgentTask | None) -> MarketTaskOverview | None:
        if task is None:
            return None
        return MarketTaskOverview(
            task_id=str(task.id),
            status=task.status.value,
            query=task.request.user_query,
            current_step=task.current_step,
            created_at=task.created_at,
            completed_at=task.completed_at,
        )

    def _pipeline(self, task: AgentTask | None) -> list[MarketPipelineStage]:
        completed = {
            event.step
            for event in (task.events if task else [])
            if event.event_type is TaskEventType.NODE_COMPLETED and event.step
        }
        current = task.current_step if task else None
        failed = bool(task and task.status is TaskStatus.FAILED)
        stages: list[MarketPipelineStage] = []
        for code, label, description, nodes in self._PIPELINE:
            node_set = set(nodes)
            if node_set.issubset(completed):
                status = "completed"
            elif current in node_set and failed:
                status = "failed"
            elif current in node_set:
                status = "running"
            elif node_set.intersection(completed):
                status = "partial"
            else:
                status = "pending"
            stages.append(
                MarketPipelineStage(
                    code=code,
                    label=label,
                    description=description,
                    nodes=list(nodes),
                    status=status,
                )
            )
        return stages


__all__ = ["MarketOverview", "MarketOverviewService"]
