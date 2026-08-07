"""
splitter.py — Train/val/test split with leakage prevention.
"""

import json
import random
import shutil
import sys
from pathlib import Path
from typing import Tuple

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lyra.config import (
    RAW_SCREENSHOTS_DIR,
    ANNOTATIONS_DIR,
    TRAIN_DIR,
    VAL_DIR,
    TEST_DIR,
)


def split_dataset(
    annotations_dir: Path = ANNOTATIONS_DIR,
    raw_dir: Path = RAW_SCREENSHOTS_DIR,
    ratio: Tuple[float, float, float] = (0.8, 0.1, 0.1),
    seed: int = 42,
) -> Tuple[int, int, int]:
    """
    Splits annotated dataset into train, val, and test sets.
    Copies image PNGs and JSON annotations to data/processed/{train,val,test}.
    """
    assert sum(ratio) == 1.0, "Split ratios must sum to 1.0"
    random.seed(seed)

    # Ensure output directories exist and are clean
    for d in [TRAIN_DIR, VAL_DIR, TEST_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    json_files = sorted(list(annotations_dir.glob("*.json")))
    if not json_files:
        print("[SPLITTER WARNING] No annotation JSON files found in ANNOTATIONS_DIR.")
        return 0, 0, 0

    random.shuffle(json_files)

    total = len(json_files)
    n_train = int(total * ratio[0])
    n_val = int(total * ratio[1])
    n_test = total - n_train - n_val

    splits = {
        "train": (json_files[:n_train], TRAIN_DIR),
        "val": (json_files[n_train : n_train + n_val], VAL_DIR),
        "test": (json_files[n_train + n_val :], TEST_DIR),
    }

    counts = {}
    for split_name, (file_list, target_dir) in splits.items():
        counts[split_name] = len(file_list)
        for json_path in file_list:
            base_name = json_path.stem
            img_path = raw_dir / f"{base_name}.png"

            # Copy JSON annotation
            shutil.copy2(json_path, target_dir / json_path.name)

            # Copy PNG image if it exists
            if img_path.exists():
                shutil.copy2(img_path, target_dir / img_path.name)

    print("==================================================")
    print("            LYRA DATASET SPLIT COMPLETE           ")
    print("==================================================")
    print(f"Total Samples Split: {total}")
    print(f"  - Train Set: {counts['train']} samples ({ratio[0]*100:.0f}%) -> {TRAIN_DIR.name}")
    print(f"  - Val Set:   {counts['val']} samples ({ratio[1]*100:.0f}%) -> {VAL_DIR.name}")
    print(f"  - Test Set:  {counts['test']} samples ({ratio[2]*100:.0f}%) -> {TEST_DIR.name}")

    return counts["train"], counts["val"], counts["test"]


if __name__ == "__main__":
    split_dataset()
