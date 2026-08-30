import hashlib
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATASET_DIR = (
    BASE_DIR
    / "data"
    / "market_intelligence"
    / "amazon_us_portable_blender_v1"
)



def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


def main():
    manifest_path = DATASET_DIR / "manifest.json"

    with manifest_path.open(
        "r",
        encoding="utf-8",
    ) as f:
        manifest = json.load(f)

    files = [
        "products.jsonl",
        "reviews.jsonl",
        "market_metrics.json",
        "profit_inputs.json",
    ]

    for filename in files:
        path = DATASET_DIR / filename

        manifest["checksums"][filename] = sha256_file(path)

    with manifest_path.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            manifest,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print("checksums updated")


if __name__ == "__main__":
    main()