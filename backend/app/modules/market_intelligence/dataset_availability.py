from dataclasses import dataclass

from app.adapters.commerce.dataset import DatasetRegistry
from app.domain import DatasetMatch
from app.modules.market_intelligence.schemas import DatasetManifest
from app.modules.market_intelligence.schemas.request import MarketIntelligenceRequest


@dataclass(frozen=True)
class CanonicalDatasetInput:
    dataset_id: str
    platform: str
    market: str
    category: str
    keyword: str
    matched_aliases: tuple[str, ...]


class DatasetAvailability:
    """基于 Registry 中的 manifest 元数据匹配可用固定数据集。"""

    def __init__(self, registry: DatasetRegistry) -> None:
        self.registry = registry

    def canonicalize_product(
        self,
        *values: str | None,
    ) -> CanonicalDatasetInput | None:
        searchable = " ".join(value for value in values if value).casefold()
        for entry in self.registry.all():
            manifest = entry.manifest
            aliases = self._aliases(manifest)
            matched = [alias for alias in aliases if alias.casefold() in searchable]
            if matched:
                return CanonicalDatasetInput(
                    dataset_id=manifest.dataset_id,
                    platform=manifest.platform,
                    market=manifest.market,
                    category=manifest.category,
                    keyword=manifest.keyword,
                    matched_aliases=tuple(matched),
                )
        return None

    def default_market(self) -> str | None:
        return self._single_manifest_value("market")

    def default_platform(self) -> str | None:
        return self._single_manifest_value("platform")

    def match(
        self,
        request: MarketIntelligenceRequest,
        *,
        user_query: str = "",
    ) -> list[DatasetMatch]:
        return [
            self._match_manifest(entry.manifest, request, user_query)
            for entry in self.registry.all()
        ]

    def is_supported(self, request: MarketIntelligenceRequest) -> bool:
        return any(match.supported for match in self.match(request))

    def _single_manifest_value(self, field: str) -> str | None:
        values = {getattr(entry.manifest, field) for entry in self.registry.all()}
        return next(iter(values)) if len(values) == 1 else None

    @staticmethod
    def _aliases(manifest: DatasetManifest) -> tuple[str, ...]:
        return tuple(dict.fromkeys([manifest.keyword, manifest.category, *manifest.aliases]))

    @staticmethod
    def _selector(value: str) -> str:
        return " ".join(value.casefold().replace("_", " ").split())

    def _match_manifest(
        self,
        manifest: DatasetManifest,
        request: MarketIntelligenceRequest,
        user_query: str,
    ) -> DatasetMatch:
        platform_match = self._selector(request.platforms[0]) == self._selector(
            manifest.platform
        )
        market_match = self._selector(request.market) == self._selector(manifest.market)
        category_match = self._selector(request.category) == self._selector(
            manifest.category
        )
        keyword_match = self._selector(request.keyword) == self._selector(manifest.keyword)
        supported = platform_match and market_match and category_match and keyword_match
        matched_aliases = [
            alias
            for alias in self._aliases(manifest)
            if alias.casefold() in user_query.casefold()
        ]
        reason_code = None
        if not platform_match:
            reason_code = "PLATFORM_NOT_SUPPORTED"
        elif not market_match:
            reason_code = "MARKET_NOT_SUPPORTED"
        elif not category_match:
            reason_code = "CATEGORY_NOT_SUPPORTED"
        elif not keyword_match:
            reason_code = "KEYWORD_NOT_SUPPORTED"
        return DatasetMatch(
            dataset_id=manifest.dataset_id,
            supported=supported,
            score=(
                0.2 * platform_match
                + 0.2 * market_match
                + 0.25 * category_match
                + 0.35 * keyword_match
            ),
            platform=manifest.platform,
            market=manifest.market,
            category=manifest.category,
            canonical_keyword=manifest.keyword,
            matched_aliases=matched_aliases,
            reason_code=reason_code,
        )


__all__ = ["CanonicalDatasetInput", "DatasetAvailability"]
