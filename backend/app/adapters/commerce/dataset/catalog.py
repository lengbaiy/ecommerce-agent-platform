import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.modules.market_intelligence.schemas import DatasetManifest


class DatasetCatalogError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class DatasetCatalogEntry:
    dataset_dir: Path
    manifest: DatasetManifest


class DatasetRegistry:
    """Catalog 加载后的只读数据集注册表。"""

    def __init__(self, entries: list[DatasetCatalogEntry]) -> None:
        self._entries = tuple(entries)
        self._by_id = {entry.manifest.dataset_id: entry for entry in entries}
        if len(self._by_id) != len(entries):
            raise DatasetCatalogError(
                "DATASET_ID_CONFLICT",
                "Dataset manifests contain duplicate dataset_id values.",
            )

    def all(self) -> tuple[DatasetCatalogEntry, ...]:
        return self._entries

    def get(self, dataset_id: str) -> DatasetCatalogEntry | None:
        return self._by_id.get(dataset_id)


class DatasetCatalog:
    """扫描固定数据集目录并验证 manifest，文件路径只保留在后端。"""

    def __init__(self, dataset_root: str | Path) -> None:
        self.dataset_root = Path(dataset_root).resolve()

    def load(self) -> DatasetRegistry:
        if not self.dataset_root.is_dir():
            raise DatasetCatalogError(
                "DATA_SOURCE_DISABLED",
                f"Dataset root does not exist: {self.dataset_root.name}.",
            )
        try:
            dataset_dirs = sorted(
                path for path in self.dataset_root.iterdir() if path.is_dir()
            )
        except OSError as exc:
            raise DatasetCatalogError(
                "DATASET_CATALOG_UNAVAILABLE",
                "Dataset root cannot be read.",
            ) from exc

        entries: list[DatasetCatalogEntry] = []
        for dataset_dir in dataset_dirs:
            manifest_path = dataset_dir / "manifest.json"
            if manifest_path.is_file():
                entries.append(self._load_entry(dataset_dir, manifest_path))
        return DatasetRegistry(entries)

    @staticmethod
    def _load_entry(dataset_dir: Path, manifest_path: Path) -> DatasetCatalogEntry:
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = DatasetManifest.model_validate(raw)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise DatasetCatalogError(
                "DATASET_MANIFEST_INVALID",
                f"Dataset manifest is invalid: {dataset_dir.name}.",
            ) from exc
        if manifest.dataset_id != dataset_dir.name:
            raise DatasetCatalogError(
                "DATASET_ID_MISMATCH",
                f"Dataset directory and dataset_id differ: {dataset_dir.name}.",
            )
        return DatasetCatalogEntry(dataset_dir=dataset_dir, manifest=manifest)


__all__ = [
    "DatasetCatalog",
    "DatasetCatalogEntry",
    "DatasetCatalogError",
    "DatasetRegistry",
]
