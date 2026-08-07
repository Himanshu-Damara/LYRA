"""
validator.py — Dataset validation, integrity checks, and statistics.
"""

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lyra.config import (
    RAW_SCREENSHOTS_DIR,
    ANNOTATIONS_DIR,
    UI_ELEMENT_CLASSES,
    SCREEN_STATE_CLASSES,
)


def validate_dataset(
    annotations_dir: Path = ANNOTATIONS_DIR,
    raw_images_dir: Path = RAW_SCREENSHOTS_DIR,
) -> Dict[str, any]:
    """
    Validates dataset annotations against schema rules and image integrity.
    """
    stats = {
        "total_annotations": 0,
        "total_images_found": 0,
        "total_bounding_boxes": 0,
        "invalid_boxes": 0,
        "unknown_labels": 0,
        "class_distribution": Counter(),
        "screen_state_distribution": Counter(),
        "warnings": [],
        "errors": []
    }

    if not annotations_dir.exists():
        stats["errors"].append(f"Annotations directory does not exist: {annotations_dir}")
        return stats

    json_files = list(annotations_dir.glob("*.json"))
    stats["total_annotations"] = len(json_files)

    for json_path in json_files:
        with open(json_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except Exception as e:
                stats["errors"].append(f"Corrupt JSON file {json_path.name}: {e}")
                continue

        filename = data.get("filename", "")
        img_path = raw_images_dir / filename
        if img_path.exists():
            stats["total_images_found"] += 1
        else:
            stats["warnings"].append(f"Missing raw image for annotation: {filename}")

        res = data.get("resolution", {})
        width = res.get("width", 720)
        height = res.get("height", 1600)

        screen_state = data.get("screen_state_tag", "UNKNOWN")
        if screen_state not in SCREEN_STATE_CLASSES:
            stats["warnings"].append(f"{json_path.name}: Unknown screen state '{screen_state}'")
        stats["screen_state_distribution"][screen_state] += 1

        objects = data.get("objects", [])
        for obj in objects:
            stats["total_bounding_boxes"] += 1
            label = obj.get("label", "unknown")
            bbox = obj.get("bbox", [])

            if label not in UI_ELEMENT_CLASSES:
                stats["unknown_labels"] += 1
                stats["warnings"].append(f"{json_path.name}: Unrecognized class label '{label}'")
            stats["class_distribution"][label] += 1

            if len(bbox) != 4:
                stats["invalid_boxes"] += 1
                stats["errors"].append(f"{json_path.name}: Bbox does not have 4 coordinates: {bbox}")
                continue

            xmin, ymin, xmax, ymax = bbox
            if xmin >= xmax or ymin >= ymax or xmin < 0 or ymin < 0 or xmax > width or ymax > height:
                stats["invalid_boxes"] += 1
                stats["warnings"].append(
                    f"{json_path.name}: Invalid bbox [{xmin}, {ymin}, {xmax}, {ymax}] for resolution {width}x{height}"
                )

    return stats


def print_dataset_report(stats: Dict[str, any]):
    print("==================================================")
    print("           LYRA DATASET VALIDATION REPORT         ")
    print("==================================================")
    print(f"Total Annotations Checked: {stats['total_annotations']}")
    print(f"Matching Raw Images Found: {stats['total_images_found']}")
    print(f"Total Bounding Boxes:     {stats['total_bounding_boxes']}")
    print(f"Invalid Bounding Boxes:   {stats['invalid_boxes']}")
    print(f"Unknown Labels:           {stats['unknown_labels']}")
    print("\n--- Screen State Distribution ---")
    for state, count in stats["screen_state_distribution"].items():
        print(f"  - {state:<20}: {count}")
    print("\n--- UI Element Class Distribution ---")
    for cls_name, count in stats["class_distribution"].items():
        print(f"  - {cls_name:<25}: {count}")

    if stats["warnings"]:
        print(f"\n[WARNINGS] ({len(stats['warnings'])} warnings):")
        for w in stats["warnings"][:10]:
            print(f"  * {w}")
        if len(stats["warnings"]) > 10:
            print(f"  ... and {len(stats['warnings']) - 10} more warnings.")

    if stats["errors"]:
        print(f"\n[ERRORS] ({len(stats['errors'])} errors):")
        for e in stats["errors"]:
            print(f"  ! {e}")
    else:
        print("\n[SUCCESS] No critical dataset errors found!")


if __name__ == "__main__":
    s = validate_dataset()
    print_dataset_report(s)
