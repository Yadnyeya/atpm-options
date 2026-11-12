"""Load config.yaml, the single place where project assumptions live."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"


def load_config() -> dict:
    """Return config.yaml as a dict, so no module hard-codes an assumption."""
    return yaml.safe_load((ROOT / "config.yaml").read_text())
