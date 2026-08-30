from collections.abc import Iterable

from app.adapters.commerce.commerce_adapter_base import CommerceAdapter


AdapterKey = tuple[str, str]


class CommerceAdapterRegistry:
    """
    Commerce Adapter 注册表。

    使用 (platform, data_source_mode) 作为唯一键，例如：

        ("amazon", "fixed_dataset")
        ("jd", "fixed_dataset")
        ("taobao", "official_api")

    Registry 是应用级对象：
    - 应用启动时注册 Adapter
    - 请求执行时通过 get() 获取 Adapter
    """

    def __init__(
        self,
        adapters: Iterable[CommerceAdapter] | None = None,
    ) -> None:
        self._adapters: dict[AdapterKey, CommerceAdapter] = {}

        if adapters is not None:
            for adapter in adapters:
                self.register(adapter)

    def register(self, adapter: CommerceAdapter) -> None:
        """
        注册一个 Adapter。

        同一个 (platform, data_source_mode) 不允许重复注册。
        """

        platform = self._normalize(
            adapter.platform,
            "platform",
        )
        data_source_mode = self._normalize(
            adapter.data_source_mode,
            "data_source_mode",
        )

        key = (platform, data_source_mode)

        if key in self._adapters:
            raise ValueError(
                "Commerce adapter already registered: "
                f"{platform}/{data_source_mode}"
            )

        self._adapters[key] = adapter

    def get(
        self,
        platform: str,
        data_source_mode: str,
    ) -> CommerceAdapter:
        """
        根据平台和数据源类型获取 Adapter。

        找不到时抛 KeyError，由上层 Tool 转换为
        UNSUPPORTED_DATA_SOURCE。
        """

        key = (
            self._normalize(platform, "platform"),
            self._normalize(
                data_source_mode,
                "data_source_mode",
            ),
        )

        try:
            return self._adapters[key]
        except KeyError as exc:
            raise KeyError(
                "No commerce adapter registered for "
                f"{key[0]}/{key[1]}"
            ) from exc

    def all(self) -> tuple[CommerceAdapter, ...]:
        """返回已注册 Adapter，供能力预览使用。"""

        return tuple(self._adapters.values())

    @staticmethod
    def _normalize(
        value: str,
        field_name: str,
    ) -> str:
        """
        统一 Registry key。

        " Amazon "  -> "amazon"
        "FIXED_DATASET" -> "fixed_dataset"
        """

        if not isinstance(value, str):
            raise TypeError(
                f"{field_name} must be a string"
            )

        normalized = value.strip().casefold()

        if not normalized:
            raise ValueError(
                f"{field_name} is required"
            )

        return normalized
