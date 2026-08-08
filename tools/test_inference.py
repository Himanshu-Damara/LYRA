"""
test_inference.py — Run the trained LYRA model on a single screenshot and visualize predictions.

Usage:
    python tools/test_inference.py --image path/to/screenshot.png
"""

import sys
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import cv2
from lyra.config import (
    UI_ELEMENT_CLASSES,
    RESULTS_DIR,
)
from lyra.inference.detector import LyraDetector


def run_inference(image_path: str, conf_threshold: float = 0.40):
    try:
        detector = LyraDetector(conf_threshold=conf_threshold)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        return

    img_path = Path(image_path)
    if not img_path.exists():
        print(f"[ERROR] Image not found: {img_path}")
        return

    img_bgr = cv2.imread(str(img_path))
    if img_bgr is None:
        print(f"[ERROR] Could not read image: {img_path}")
        return

    orig_h, orig_w = img_bgr.shape[:2]
    print(f"[INFERENCE] Input image: {img_path.name} ({orig_w}x{orig_h})")

    # Run multi-stage NMS detector
    result = detector.detect(img_bgr, iou_threshold=0.25, single_per_class=True)

    pred_state_str = result["screen_state"]
    state_conf = result["screen_confidence"]
    detections = result["detections"]

    print(f"\n{'='*60}")
    print(f"  SCREEN STATE: {pred_state_str}  (confidence: {state_conf:.1%})")
    print(f"{'='*60}")

    print(f"\n  Detected UI Elements ({len(detections)} found after Multi-Stage NMS):")
    if not detections:
        print("    (none detected above confidence threshold)")
    else:
        for idx, det in enumerate(detections):
            lbl = det["label"]
            score = det["confidence"]
            bbox = det["bbox_original"]
            print(f"    [{idx+1}] Class: {lbl:<22} Conf: {score:.2%}  BBox: [{bbox[0]}, {bbox[1]}, {bbox[2]}, {bbox[3]}]")

    # Clean Visualization
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_img = img_bgr.copy()

    colors = [
        (0, 255, 0), (255, 0, 0), (0, 0, 255), (255, 255, 0),
        (255, 0, 255), (0, 255, 255), (128, 0, 255), (255, 128, 0),
        (0, 128, 255), (128, 255, 0), (255, 0, 128), (64, 192, 255), (255, 192, 64)
    ]

    # Draw screen state banner
    cv2.rectangle(output_img, (0, 0), (orig_w, 50), (0, 0, 0), -1)
    cv2.putText(
        output_img, f"STATE: {pred_state_str} ({state_conf:.0%})", (15, 35),
        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2
    )

    # Draw clean non-overlapping bounding boxes
    for idx, det in enumerate(detections):
        lbl = det["label"]
        score = det["confidence"]
        xmin, ymin, xmax, ymax = det["bbox_original"]

        lbl_idx = UI_ELEMENT_CLASSES.index(lbl) if lbl in UI_ELEMENT_CLASSES else idx
        color = colors[lbl_idx % len(colors)]

        # Draw box outline
        cv2.rectangle(output_img, (xmin, ymin), (xmax, ymax), color, 3)

        # Label string: Class Name | Conf%
        text = f"{lbl} {score:.0%}"
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(output_img, (xmin, max(0, ymin - th - 10)), (xmin + tw + 8, ymin), color, -1)
        cv2.putText(
            output_img, text, (xmin + 4, max(th + 4, ymin - 4)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2
        )

    out_path = RESULTS_DIR / f"inference_{img_path.stem}.png"
    cv2.imwrite(str(out_path), output_img)
    print(f"\n  [SAVED] Clean annotated result -> {out_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LYRA Model Inference on a single screenshot")
    parser.add_argument("--image", type=str, required=True, help="Path to the screenshot PNG")
    parser.add_argument("--conf", type=float, default=0.40, help="Confidence threshold (default: 0.40)")
    args = parser.parse_args()
    run_inference(args.image, conf_threshold=args.conf)
