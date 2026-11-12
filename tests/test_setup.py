"""Guards on the project setup: the raw class file and the config."""
import hashlib

from src.config import ROOT, load_config


def test_class_file_is_untouched():
    """Professor's rule: the raw data file is never modified."""
    data = load_config()["data"]
    digest = hashlib.sha256((ROOT / data["class_file"]).read_bytes()).hexdigest()
    assert digest == data["class_file_sha256"]


def test_sample_split_does_not_overlap():
    """Out-of-sample must start after in-sample ends, or the final run is contaminated."""
    sample = load_config()["sample"]
    assert sample["in_sample"][1] < sample["out_of_sample"][0]
