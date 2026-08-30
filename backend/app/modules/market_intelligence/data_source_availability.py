from app.adapters.commerce import CommerceAdapter, CommerceAdapterRegistry
from app.domain import DataSourceOption, DatasetMatch
from app.modules.market_intelligence.schemas import AdapterCapabilities, DataSourceMode
from app.modules.market_intelligence.schemas.request import MarketIntelligenceRequest


class MarketDataSourceAvailability:
    """把数据集、Adapter 能力和租户授权转换为运营端可选项。"""

    def __init__(self, registry: CommerceAdapterRegistry) -> None:
        self.registry = registry

    def options(
        self,
        request: MarketIntelligenceRequest,
        dataset_matches: list[DatasetMatch],
        tenant_id: str | None = None,
    ) -> list[DataSourceOption]:
        options: dict[tuple[str, str, str], DataSourceOption] = {}
        platform = request.platforms[0]
        market = request.market

        fixed_supported = any(item.supported for item in dataset_matches)
        fixed_adapter = self._adapter(platform, DataSourceMode.FIXED_DATASET)
        fixed_capabilities = fixed_adapter.capabilities() if fixed_adapter else None
        self._add(
            options,
            platform=platform,
            market=market,
            mode=DataSourceMode.FIXED_DATASET,
            capabilities=fixed_capabilities,
            available=fixed_supported and fixed_adapter is not None,
            reason=(
                None
                if fixed_supported and fixed_adapter is not None
                else "当前商品、市场或平台没有可用固定数据集"
            ),
        )

        # 注册具体平台 Adapter 后，选择器会自动出现该官方数据源。
        official_platforms = {
            adapter.platform
            for adapter in self.registry.all()
            if adapter.data_source_mode == DataSourceMode.OFFICIAL_API.value
        }
        official_platforms.add(platform)
        for official_platform in sorted(official_platforms):
            adapter = self._adapter(official_platform, DataSourceMode.OFFICIAL_API)
            capabilities = adapter.capabilities() if adapter else None
            authorization_check = getattr(adapter, "is_authorized", None)
            authorized = bool(
                tenant_id
                and callable(authorization_check)
                and authorization_check(tenant_id)
            )
            capable = bool(capabilities and capabilities.supports_products)
            available = capable and authorized
            reason = None
            if adapter is None:
                reason = "该平台官方 API 尚未接入"
            elif not capable:
                reason = "该平台官方 API 暂不支持商品分析"
            elif not authorized:
                reason = "当前账号尚未授权该平台官方 API"
            self._add(
                options,
                platform=official_platform,
                market=market,
                mode=DataSourceMode.OFFICIAL_API,
                capabilities=capabilities,
                available=available,
                reason=reason,
            )

        return list(options.values())

    def is_supported(
        self,
        request: MarketIntelligenceRequest,
        tenant_id: str | None = None,
    ) -> bool:
        adapter = self._adapter(request.platforms[0], request.data_source_mode)
        if adapter is None or not adapter.capabilities().supports_products:
            return False
        if request.data_source_mode is DataSourceMode.FIXED_DATASET:
            return True
        checker = getattr(adapter, "is_authorized", None)
        return bool(tenant_id and callable(checker) and checker(tenant_id))

    def _adapter(
        self,
        platform: str,
        mode: DataSourceMode,
    ) -> CommerceAdapter | None:
        try:
            return self.registry.get(platform, mode.value)
        except KeyError:
            return None

    @staticmethod
    def _add(
        options: dict[tuple[str, str, str], DataSourceOption],
        *,
        platform: str,
        market: str,
        mode: DataSourceMode,
        capabilities: AdapterCapabilities | None,
        available: bool,
        reason: str | None,
    ) -> None:
        platform_label = {
            "amazon": "Amazon",
            "taobao": "淘宝",
            "jd": "京东",
            "pinduoduo": "拼多多",
        }.get(platform.casefold(), platform)
        mode_label = "固定数据集" if mode is DataSourceMode.FIXED_DATASET else "官方 API"
        option = DataSourceOption(
            platform=platform,
            market=market,
            data_source_mode=mode.value,
            label=f"{platform_label} {market.upper()} · {mode_label}",
            available=available,
            supports_products=bool(capabilities and capabilities.supports_products),
            supports_reviews=bool(capabilities and capabilities.supports_reviews),
            supports_market_metrics=bool(
                capabilities and capabilities.supports_market_metrics
            ),
            unavailable_reason=reason,
        )
        options[(platform.casefold(), market.casefold(), mode.value)] = option


__all__ = ["MarketDataSourceAvailability"]
