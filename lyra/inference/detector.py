"""
detector.py — Run the trained model on a screenshot and return detections.

Provides a reusable LyraDetector class that loads the model once and exposes
a simple `detect(image)` API returning screen state, bounding boxes, and classes.
"""

import torch
import numpy as np
import cv2
from pathlib import Path
from typing import List, Dict, Tuple, Optional

from lyra.config import (
    UI_ELEMENT_CLASSES,
    SCREEN_STATE_CLASSES,
    CHECKPOINTS_DIR,
)
from lyra.model.model import LyraNet
from lyra.data.preprocessing import letterbox_image, preprocess_image_tensor
from lyra.training.evaluator import decode_detections, calculate_iou


class LyraDetector:
    """
    Inference-ready detector that wraps the trained LyraNet model.
    Loads model weights once and provides a detect(image) method.
    """

    def __init__(self, checkpoint: str = "best_model.pth", conf_threshold: float = 0.40):
        self.conf_threshold = conf_threshold
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        ckpt_path = CHECKPOINTS_DIR / checkpoint
        if not ckpt_path.exists():
            ckpt_path = CHECKPOINTS_DIR / "latest_model.pth"
        if not ckpt_path.exists():
            raise FileNotFoundError(f"No model checkpoint found in {CHECKPOINTS_DIR}")

        self.model = LyraNet()
        data = torch.load(ckpt_path, map_location=self.device, weights_only=False)
        self.model.load_state_dict(data["model_state_dict"])
        self.model.to(self.device)
        self.model.eval()

    def detect(
        self,
        image: np.ndarray,
        iou_threshold: float = 0.25,
        single_per_class: bool = True
    ) -> Dict:
        """
        Run detection on a BGR numpy image.

        Steps:
          1. Confidence filtering (conf * class_prob > conf_threshold)
          2. Per-class Non-Maximum Suppression (iou > iou_threshold)
          3. Single-instance filter (keep only highest confidence prediction per class if requested)
          4. Scaling back to original image coordinates

        Returns dict with:
            screen_state: str
            screen_confidence: float
            detections: list of {label, confidence, bbox_original [xmin,ymin,xmax,ymax]}
        """
        orig_h, orig_w = image.shape[:2]

        letterboxed, ratio, (pad_x, pad_y) = letterbox_image(image, target_shape=(416, 416))
        tensor = preprocess_image_tensor(letterboxed).unsqueeze(0).to(self.device)

        with torch.no_grad():
            pred_det, pred_state = self.model(tensor)

        # 1. Screen State Classification
        state_probs = torch.softmax(pred_state, dim=1)[0]
        state_idx = torch.argmax(state_probs).item()
        screen_state = SCREEN_STATE_CLASSES[state_idx]
        screen_conf = state_probs[state_idx].item()

        # 2. Prediction Decoding
        pred_boxes, pred_scores, pred_labels = decode_detections(
            pred_det, conf_threshold=self.conf_threshold
        )

        raw_boxes = pred_boxes[0]
        raw_scores = pred_scores[0]
        raw_labels = pred_labels[0]

        # 3. Multi-Stage NMS Implementation
        detections = self._nms(
            raw_boxes, raw_scores, raw_labels,
            ratio, pad_x, pad_y, orig_w, orig_h,
            iou_threshold=iou_threshold,
            single_per_class=single_per_class
        )

        return {
            "screen_state": screen_state,
            "screen_confidence": screen_conf,
            "detections": detections,
        }

    def _nms(
        self,
        boxes: List[List[float]],
        scores: List[float],
        labels: List[int],
        ratio: float,
        pad_x: float,
        pad_y: float,
        orig_w: int,
        orig_h: int,
        iou_threshold: float = 0.25,
        single_per_class: bool = True
    ) -> List[Dict]:
        """
        Multi-Stage NMS Pipeline:
          Stage 1: Confidence filtering (already completed in decode_detections)
          Stage 2: Perform Per-Class NMS (iou > iou_threshold)
          Stage 3: Perform single-instance filtering for UI icons
        """
        if not boxes:
            return []

        # Convert letterbox boxes to original image coordinates
        candidates = []
        for box, score, lbl_id in zip(boxes, scores, labels):
            xmin = max(0, (box[0] - pad_x) / ratio)
            ymin = max(0, (box[1] - pad_y) / ratio)
            xmax = min(orig_w, (box[2] - pad_x) / ratio)
            ymax = min(orig_h, (box[3] - pad_y) / ratio)

            label_str = UI_ELEMENT_CLASSES[lbl_id] if lbl_id < len(UI_ELEMENT_CLASSES) else f"unknown_{lbl_id}"
            candidates.append({
                "label": label_str,
                "label_id": lbl_id,
                "confidence": float(score),
                "bbox_original": [int(xmin), int(ymin), int(xmax), int(ymax)],
                "box_float": [xmin, ymin, xmax, ymax],
            })

        # Group by class label
        class_groups: Dict[int, List[Dict]] = {}
        for c in candidates:
            class_groups.setdefault(c["label_id"], []).append(c)

        nms_kept = []

        # Stage 2: Per-class NMS
        for cls_id, cls_candidates in class_groups.items():
            # Sort candidates by confidence descending
            cls_candidates.sort(key=lambda c: c["confidence"], reverse=True)

            suppressed = set()
            cls_kept = []

            for i, cand in enumerate(cls_candidates):
                if i in suppressed:
                    continue
                cls_kept.append(cand)

                for j in range(i + 1, len(cls_candidates)):
                    if j in suppressed:
                        continue
                    iou = calculate_iou(cand["box_float"], cls_candidates[j]["box_float"])
                    if iou > iou_threshold:
                        suppressed.add(j)

            # Stage 3: Single-instance filter per class (if single_per_class is True)
            if single_per_class and len(cls_kept) > 1:
                # Keep ONLY the single highest confidence prediction for this class
                cls_kept = [cls_kept[0]]

            nms_kept.extend(cls_kept)

        # Sort all final detections by confidence
        nms_kept.sort(key=lambda d: d["confidence"], reverse=True)

        # Format final output dictionaries
        result = []
        for item in nms_kept:
            result.append({
                "label": item["label"],
                "confidence": item["confidence"],
                "bbox_original": item["bbox_original"],
            })

        return result
