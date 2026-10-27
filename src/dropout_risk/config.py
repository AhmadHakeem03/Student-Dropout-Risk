"""Configuration loading."""

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_config(path: str | Path | None = None) -> dict:
    """Load the YAML config. Relative paths inside it are resolved against the project root."""
    load_dotenv(PROJECT_ROOT / ".env")
    path = Path(path or os.getenv("DROPOUT_RISK_CONFIG", "config/config.yaml"))
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["data"]["raw_path"] = PROJECT_ROOT / cfg["data"]["raw_path"]
    cfg["data"]["processed_dir"] = PROJECT_ROOT / cfg["data"]["processed_dir"]
    cfg["output_dir"] = PROJECT_ROOT / cfg["output_dir"]
    return cfg
