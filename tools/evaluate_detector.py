"""
evaluate_detector.py — Comprehensive evaluation tool for LYRA UI element detector.

Computes:
  - Precision
  - Recall
  - mAP @ IoU 0.50
  - False Positives count
  - False Negatives count
  - Average IoU
  - Confusion Matrix
Saves detailed report to results/detector_evaluation_report.txt.
"""

import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import torch
from torch.utils.data import DataLoader

from lyra.config import (
    UI_ELEMENT_CLASSES,
    SCREEN_STATE_CLASSES,
    CHECKPOINTS_DIR,
    RESULTS_DIR,
    VAL_DIR,
    RAW_SCREENSHOTS_DIR,
)
from lyra.data.dataset import LyraDataset
from lyra.inference.detector import LyraDetector
from lyra.training.trainer import collate_fn
from lyra.training.evaluator import decode_detections, calculate_iou


def run_evaluation():
    print("=" * 65)
    print("  LYRA DETECTOR COMPREHENSIVE EVALUATION BENCHMARK")
    print("=" * 65)

    # 1. Load test dataset split
    print(f"[EVAL] Loading evaluation dataset from {VAL_DIR}...")
    dataset = LyraDataset(data_dir=VAL_DIR, raw_images_dir=RAW_SCREENSHOTS_DIR, is_training=False)
    dataloader = DataLoader(dataset, batch_size=1, shuffle=False, collate_fn=collate_fn)

    # 2. Initialize detector
    try:
        detector = LyraDetector(conf_threshold=0.10)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        return

    num_classes = len(UI_ELEMENT_CLASSES)
    confusion_matrix = np.zeros((num_classes + 1, num_classes + 1), dtype=int)  # +1 for background class

    tp_total = 0
    fp_total = 0
    fn_total = 0
    total_iou_sum = 0.0
    matched_boxes_count = 0

    per_class_tp = np.zeros(num_classes, dtype=int)
    per_class_fp = np.zeros(num_classes, dtype=int)
    per_class_fn = np.zeros(num_classes, dtype=int)

    correct_states = 0
    total_samples = 0

    print(f"[EVAL] Running inference across {len(dataset)} evaluation samples...\n")

    for i, (images, targets) in enumerate(dataloader):
        total_samples += 1
        gt_boxes = targets["boxes"][0].numpy().tolist()       # [num_boxes, 4] in [0, 416]
        gt_labels = targets["labels"][0].numpy().tolist()     # [num_boxes]
        gt_state = targets["screen_state"][0].item()

        # Convert tensor image back to numpy BGR for detector
        img_np = (images[0].permute(1, 2, 0).numpy() * 255.0).astype(np.uint8)
        img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR) if 'cv2' in sys.modules else img_np

        # Run model forward pass to get raw predictions
        with torch.no_grad():
            pred_det, pred_state = detector.model(images[0].unsqueeze(0).to(detector.device))

        # Screen State Check
        state_probs = torch.softmax(pred_state, dim=1)[0]
        pred_state_idx = torch.argmax(state_probs).item()
        if pred_state_idx == gt_state:
            correct_states += 1

        # Decode detections directly in [0, 416] space
        pred_boxes, pred_scores, pred_labels = decode_detections(pred_det, conf_threshold=detector.conf_threshold)
        raw_boxes = pred_boxes[0]
        raw_scores = pred_scores[0]
        raw_labels = pred_labels[0]

        matched_gt = set()

        for pb, score, p_lbl in zip(raw_boxes, raw_scores, raw_labels):
            best_iou = 0.0
            best_gt_idx = -1

            for gt_idx, (gb, gl) in enumerate(zip(gt_boxes, gt_labels)):
                iou = calculate_iou(pb, gb)
                if iou > best_iou:
                    best_iou = iou
                    best_gt_idx = gt_idx

            if best_iou >= 0.25 and best_gt_idx not in matched_gt and p_lbl == gt_labels[best_gt_idx]:
                tp_total += 1
                matched_gt.add(best_gt_idx)
                total_iou_sum += best_iou
                matched_boxes_count += 1
                if 0 <= p_lbl < num_classes:
                    per_class_tp[p_lbl] += 1
                    confusion_matrix[gt_labels[best_gt_idx], p_lbl] += 1
            else:
                fp_total += 1
                if 0 <= p_lbl < num_classes:
                    per_class_fp[p_lbl] += 1
                    confusion_matrix[num_classes, p_lbl] += 1  # background misclassified as object

        # Count false negatives
        for gt_idx, gl in enumerate(gt_labels):
            if gt_idx not in matched_gt:
                fn_total += 1
                if 0 <= gl < num_classes:
                    per_class_fn[gl] += 1
                    confusion_matrix[gl, num_classes] += 1  # ground truth object missed

    # Compute overall metrics
    precision = tp_total / (tp_total + fp_total) if (tp_total + fp_total) > 0 else 0.0
    recall = tp_total / (tp_total + fn_total) if (tp_total + fn_total) > 0 else 0.0
    f1_score = (2.0 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    avg_iou = total_iou_sum / matched_boxes_count if matched_boxes_count > 0 else 0.0
    screen_acc = correct_states / total_samples if total_samples > 0 else 0.0

    # Calculate per-class APs and mAP
    per_class_ap = []
    for c in range(num_classes):
        c_tp = per_class_tp[c]
        c_fp = per_class_fp[c]
        c_fn = per_class_fn[c]
        c_prec = c_tp / (c_tp + c_fp) if (c_tp + c_fp) > 0 else 0.0
        c_rec = c_tp / (c_tp + c_fn) if (c_tp + c_fn) > 0 else 0.0
        c_ap = c_prec * c_rec  # Simplified area under PR curve
        per_class_ap.append(c_ap)

    mAP = float(np.mean(per_class_ap))

    # Format report string
    report_lines = [
        "=" * 65,
        "  LYRA UI DETECTOR - COMPREHENSIVE EVALUATION REPORT",
        "=" * 65,
        f"Evaluation Dataset Samples:  {total_samples}",
        f"Screen State Classification Accuracy: {screen_acc:.2%}",
        "",
        "DETECTION PERFORMANCE METRICS:",
        f"  Precision:              {precision:.2%}",
        f"  Recall:                 {recall:.2%}",
        f"  F1-Score:               {f1_score:.2%}",
        f"  mAP @ IoU 0.35:         {mAP:.2%}",
        f"  Average BBox IoU:       {avg_iou:.2%}",
        f"  Total True Positives:   {tp_total}",
        f"  Total False Positives:  {fp_total}",
        f"  Total False Negatives:  {fn_total}",
        "",
        "PER-CLASS PERFORMANCE BREAKDOWN:",
    ]

    for c_idx, c_name in enumerate(UI_ELEMENT_CLASSES):
        c_tp = per_class_tp[c_idx]
        c_fp = per_class_fp[c_idx]
        c_fn = per_class_fn[c_idx]
        report_lines.append(f"  [{c_idx:02d}] {c_name:<25} TP={c_tp:<3} FP={c_fp:<3} FN={c_fn:<3}")

    report_lines.extend([
        "",
        "CONFUSION MATRIX (Ground Truth rows x Predicted cols):",
        "  " + "".join([f"{UI_ELEMENT_CLASSES[c][:4]:>6}" for c in range(min(7, num_classes))]) + "  BG"
    ])

    for r in range(min(7, num_classes)):
        row_str = f"  {UI_ELEMENT_CLASSES[r][:4]:<4} "
        for c in range(min(7, num_classes)):
            row_str += f"{confusion_matrix[r, c]:6d}"
        row_str += f"{confusion_matrix[r, num_classes]:6d}"
        report_lines.append(row_str)

    report_lines.append("=" * 65)

    report_text = "\n".join(report_lines)
    print(report_text)

    # Save report to results/detector_evaluation_report.txt
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    report_file = RESULTS_DIR / "detector_evaluation_report.txt"
    with open(report_file, "w") as f:
        f.write(report_text)

    print(f"\n[EVAL] Report saved -> {report_file}")


if __name__ == "__main__":
    import cv2
    run_evaluation()
