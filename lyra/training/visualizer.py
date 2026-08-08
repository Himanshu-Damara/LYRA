"""
visualizer.py — Render predicted bounding boxes and screen state labels on screenshots.
"""

import os
from pathlib import Path
import cv2
import numpy as np
import torch

from lyra.config import (
    UI_ELEMENT_CLASSES,
    SCREEN_STATE_CLASSES,
    RESULTS_DIR,
)
from lyra.training.evaluator import decode_detections


def visualize_predictions(
    model: torch.nn.Module,
    dataset: torch.utils.data.Dataset,
    device: torch.device,
    output_dir: Path = RESULTS_DIR,
    max_images: int = 5
):
    """
    Runs model inference on several validation images and draws bounding boxes
    and screen state classifications on them.
    Saves visual results to output_dir.
    """
    model.eval()
    output_dir.mkdir(parents=True, exist_ok=True)
    
    colors = [
        (0, 255, 0), (255, 0, 0), (0, 0, 255), (255, 255, 0),
        (255, 0, 255), (0, 255, 255), (128, 0, 255), (255, 128, 0)
    ]

    count = min(max_images, len(dataset))
    
    for i in range(count):
        img_tensor, targets = dataset[i]
        
        # Add batch dimension
        x = img_tensor.unsqueeze(0).to(device)
        
        with torch.no_grad():
            pred_det, pred_state = model(x)
            
        pred_state_idx = torch.argmax(pred_state, dim=1).item()
        pred_state_str = SCREEN_STATE_CLASSES[pred_state_idx]
        
        # Decode bounding boxes (shape: [1, 23, 13, 13])
        pred_boxes, pred_scores, pred_labels = decode_detections(pred_det, conf_threshold=0.3)
        p_boxes = pred_boxes[0]
        p_scores = pred_scores[0]
        p_labels = pred_labels[0]
        
        # Reconstruct BGR image from tensor (channels, height, width) [0, 1]
        img_np = (img_tensor.permute(1, 2, 0).numpy() * 255.0).astype(np.uint8)
        img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
        
        # Draw screen state tag
        cv2.putText(
            img_bgr, f"STATE: {pred_state_str}", (15, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2
        )
        
        # Draw bounding boxes
        for idx, (box, score, lbl_idx) in enumerate(zip(p_boxes, p_scores, p_labels)):
            xmin, ymin, xmax, ymax = box
            
            # Map float coordinates [0, 416] to int pixel positions
            xmin = int(max(0, min(xmin, 416)))
            ymin = int(max(0, min(ymin, 416)))
            xmax = int(max(0, min(xmax, 416)))
            ymax = int(max(0, min(ymax, 416)))
            
            color = colors[idx % len(colors)]
            label_str = UI_ELEMENT_CLASSES[lbl_idx]
            
            cv2.rectangle(img_bgr, (xmin, ymin), (xmax, ymax), color, 2)
            cv2.putText(
                img_bgr, f"{label_str} ({score:.2f})", (xmin, max(15, ymin - 5)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1
            )
            
        # Draw ground truth for comparison (in dashed or white)
        gt_boxes = targets["boxes"].cpu().numpy()
        gt_labels = targets["labels"].cpu().numpy()
        
        for box, lbl_idx in zip(gt_boxes, gt_labels):
            xmin, ymin, xmax, ymax = box
            xmin = int(max(0, min(xmin, 416)))
            ymin = int(max(0, min(ymin, 416)))
            xmax = int(max(0, min(xmax, 416)))
            ymax = int(max(0, min(ymax, 416)))
            
            label_str = UI_ELEMENT_CLASSES[lbl_idx]
            cv2.rectangle(img_bgr, (xmin, ymin), (xmax, ymax), (255, 255, 255), 1)
            cv2.putText(
                img_bgr, f"GT: {label_str}", (xmin, max(15, ymin - 18)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1
            )

        # Save image
        out_path = output_dir / f"pred_val_{i}.png"
        cv2.imwrite(str(out_path), img_bgr)

    print(f"[VISUALIZER] Saved predicted visualizations to {output_dir}")
