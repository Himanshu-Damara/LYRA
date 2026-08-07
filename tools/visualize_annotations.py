"""
visualize_annotations.py — Draw bounding box annotations on screenshots for inspection.
"""

import json
from pathlib import Path
import cv2

from lyra.config import (
    RAW_SCREENSHOTS_DIR,
    ANNOTATIONS_DIR,
    PROJECT_ROOT,
)

VIS_DIR = PROJECT_ROOT / "data" / "visualized_annotations"


def visualize_dataset(
    annotations_dir: Path = ANNOTATIONS_DIR,
    raw_images_dir: Path = RAW_SCREENSHOTS_DIR,
    output_dir: Path = VIS_DIR,
    max_images: int = 20,
) -> int:
    """
    Renders bounding boxes and screen state tags on screenshots.
    Saves rendered previews in output_dir.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    json_files = list(annotations_dir.glob("*.json"))
    
    if not json_files:
        print("[VISUALIZER] No JSON annotation files found to visualize.")
        return 0

    count = 0
    colors = [
        (0, 255, 0), (255, 0, 0), (0, 0, 255), (255, 255, 0),
        (255, 0, 255), (0, 255, 255), (128, 0, 255), (255, 128, 0)
    ]

    for json_path in json_files[:max_images]:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        filename = data.get("filename", f"{json_path.stem}.png")
        img_path = raw_images_dir / filename

        if not img_path.exists():
            continue

        img = cv2.imread(str(img_path))
        if img is None:
            continue

        screen_tag = data.get("screen_state_tag", "UNKNOWN")
        # Draw screen tag header
        cv2.putText(
            img, f"STATE: {screen_tag}", (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2
        )

        objects = data.get("objects", [])
        for idx, obj in enumerate(objects):
            label = obj.get("label", "unknown")
            bbox = obj.get("bbox", [])

            if len(bbox) == 4:
                xmin, ymin, xmax, ymax = bbox
                color = colors[idx % len(colors)]
                cv2.rectangle(img, (xmin, ymin), (xmax, ymax), color, 3)
                cv2.putText(
                    img, label, (xmin, max(20, ymin - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2
                )

        out_file = output_dir / f"vis_{filename}"
        cv2.imwrite(str(out_file), img)
        count += 1

    print(f"[VISUALIZER] Successfully rendered {count} preview images to {output_dir}")
    return count


if __name__ == "__main__":
    visualize_dataset()
