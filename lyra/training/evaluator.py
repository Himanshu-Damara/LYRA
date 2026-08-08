"""
evaluator.py — Validation metrics calculation for screen classification and UI detection.
"""

import torch
import numpy as np
from typing import List, Dict, Any, Tuple
from lyra.model.detection_head import ANCHORS


def calculate_iou(box1: List[float], box2: List[float]) -> float:
    """
    Computes Intersection over Union (IoU) of two bounding boxes [xmin, ymin, xmax, ymax].
    """
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])

    inter_area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    box1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])
    box2_area = (box2[2] - box2[0]) * (box2[3] - box2[1])

    union_area = box1_area + box2_area - inter_area
    if union_area <= 0.0:
        return 0.0
    return inter_area / union_area


def decode_detections(
    pred_det: torch.Tensor,
    conf_threshold: float = 0.3
) -> Tuple[List[List[List[float]]], List[List[float]], List[List[int]]]:
    """
    Decodes anchor-based predictions [B, 54, 13, 13] into bounding boxes [xmin, ymin, xmax, ymax],
    confidence scores, and class labels in 416x416 pixel space.
    """
    batch_size = pred_det.size(0)
    device = pred_det.device
    anchors = torch.tensor(ANCHORS, device=device)

    # Reshape from [B, 54, 13, 13] to [B, 3, 13, 13, 18]
    pred_det = pred_det.view(batch_size, 3, 18, 13, 13).permute(0, 1, 3, 4, 2).cpu()

    batch_boxes = []
    batch_scores = []
    batch_labels = []

    grid_y, grid_x = torch.meshgrid(torch.arange(13), torch.arange(13), indexing="ij")

    for i in range(batch_size):
        boxes = []
        scores = []
        labels = []

        img_det = pred_det[i]  # [3, 13, 13, 18]

        for a_idx, (anchor_w_norm, anchor_h_norm) in enumerate(ANCHORS):
            anchor_det = img_det[a_idx]  # [13, 13, 18]

            raw_tx = anchor_det[..., 0]
            raw_ty = anchor_det[..., 1]
            raw_tw = anchor_det[..., 2]
            raw_th = anchor_det[..., 3]
            conf = torch.sigmoid(anchor_det[..., 4])
            class_probs = torch.softmax(anchor_det[..., 5:], dim=-1)

            # Combined score: objectness * max class prob
            max_class_prob, class_idx = torch.max(class_probs, dim=-1)
            combined_scores = conf * max_class_prob

            mask = (combined_scores > conf_threshold)

            for gy, gx in mask.nonzero():
                tx_val = torch.sigmoid(raw_tx[gy, gx]).item()
                ty_val = torch.sigmoid(raw_ty[gy, gx]).item()
                tw_val = torch.exp(raw_tw[gy, gx]).item() * anchor_w_norm
                th_val = torch.exp(raw_th[gy, gx]).item() * anchor_h_norm

                xc_pixels = (gx.item() + tx_val) / 13.0 * 416.0
                yc_pixels = (gy.item() + ty_val) / 13.0 * 416.0
                w_pixels = tw_val * 416.0
                h_pixels = th_val * 416.0

                xmin = max(0.0, xc_pixels - w_pixels / 2.0)
                ymin = max(0.0, yc_pixels - h_pixels / 2.0)
                xmax = min(416.0, xc_pixels + w_pixels / 2.0)
                ymax = min(416.0, yc_pixels + h_pixels / 2.0)

                score_val = combined_scores[gy, gx].item()
                cls_val = class_idx[gy, gx].item()

                boxes.append([xmin, ymin, xmax, ymax])
                scores.append(score_val)
                labels.append(int(cls_val))

        batch_boxes.append(boxes)
        batch_scores.append(scores)
        batch_labels.append(labels)

    return batch_boxes, batch_scores, batch_labels


def evaluate_model(
    model: torch.nn.Module,
    dataloader: torch.utils.data.DataLoader,
    device: torch.device
) -> Dict[str, float]:
    """
    Evaluates model on validation set.
    """
    model.eval()

    correct_states = 0
    total_samples = 0

    tp_boxes = 0
    fp_boxes = 0
    total_gt_boxes = 0

    with torch.no_grad():
        for images, targets in dataloader:
            images = images.to(device)
            pred_det, pred_state = model(images)

            # 1. Screen state accuracy
            pred_state_cls = torch.argmax(pred_state, dim=1)
            gt_state = targets["screen_state"].to(device)
            correct_states += (pred_state_cls == gt_state).sum().item()
            total_samples += images.size(0)

            # 2. Bbox IoU accuracy
            pred_boxes, _, pred_labels = decode_detections(pred_det, conf_threshold=0.3)

            for i in range(images.size(0)):
                gt_b = targets["boxes"][i].cpu().numpy().tolist()
                gt_l = targets["labels"][i].cpu().numpy().tolist()

                p_b = pred_boxes[i]
                p_l = pred_labels[i]

                total_gt_boxes += len(gt_b)

                matched_gt = set()
                for pb, pl in zip(p_b, p_l):
                    best_iou = 0.0
                    best_gt_idx = -1

                    for gt_idx, (gb, gl) in enumerate(zip(gt_b, gt_l)):
                        if gl != pl:
                            continue
                        iou = calculate_iou(pb, gb)
                        if iou > best_iou:
                            best_iou = iou
                            best_gt_idx = gt_idx

                    if best_iou >= 0.5 and best_gt_idx not in matched_gt:
                        tp_boxes += 1
                        matched_gt.add(best_gt_idx)
                    else:
                        fp_boxes += 1

    screen_accuracy = correct_states / total_samples if total_samples > 0 else 0.0
    precision = tp_boxes / (tp_boxes + fp_boxes) if (tp_boxes + fp_boxes) > 0 else 0.0
    recall = tp_boxes / total_gt_boxes if total_gt_boxes > 0 else 0.0
    f1 = (2.0 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "screen_accuracy": screen_accuracy,
        "det_precision": precision,
        "det_recall": recall,
        "det_f1": f1
    }
