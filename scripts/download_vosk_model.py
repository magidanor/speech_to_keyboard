#!/usr/bin/env python3
"""Downloads and unpacks a Vosk speech model into ./models.

Usage:
    python scripts/download_vosk_model.py
    python scripts/download_vosk_model.py --model vosk-model-en-us-0.22
"""
import argparse
import sys
import urllib.request
import zipfile
from pathlib import Path

BASE_URL = "https://alphacephei.com/vosk/models/{model}.zip"
MODELS_DIR = Path(__file__).resolve().parent.parent / "models"

MODEL_CHOICES = {
    "vosk-model-small-en-us-0.15": "~40MB, fastest - recommended starting point for a closed command set.",
    "vosk-model-en-us-0.22-lgraph": "~128MB, a middle ground on size/accuracy.",
    "vosk-model-en-us-0.22": "~1.8GB, most accurate, higher latency/CPU cost.",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="vosk-model-small-en-us-0.15", choices=list(MODEL_CHOICES))
    args = parser.parse_args()

    MODELS_DIR.mkdir(exist_ok=True)
    dest_dir = MODELS_DIR / args.model
    if dest_dir.exists():
        print(f"{dest_dir} already exists, skipping download.")
        return 0

    url = BASE_URL.format(model=args.model)
    zip_path = MODELS_DIR / f"{args.model}.zip"
    print(f"Downloading {url} ...")
    urllib.request.urlretrieve(url, zip_path)

    print("Extracting...")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(MODELS_DIR)
    zip_path.unlink()

    print(f"Done. Model ready at {dest_dir}")
    print(f"Set vosk.model_path: {dest_dir.relative_to(MODELS_DIR.parent)} in config.yaml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
