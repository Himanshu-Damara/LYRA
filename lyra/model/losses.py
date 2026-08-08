"""
losses.py — Advanced multi-task loss functions implemented manually from scratch:
  1. Manual Focal Loss for objectness & classification (handles severe background imbalance)
  2. Manual CIoU (Complete IoU) Loss for bounding box regression (spatial overlap + center distance + aspect ratio)
  3. Anchor-matched target assignment
"""

import math
import torch
import torch.nn as nn
import torch.nn.functional as F
from lyra.model.detection_head import ANCHORS


def manual_focal_loss(
    inputs: torch.Tensor,
    targets: torch.Tensor,
    alpha: float = 0.25,
    gamma: float = 2.0,
    reduction: str = "mean"
) -> torch.Tensor:
    """
    Manually implemented Binary Focal Loss:
    FL(p_t) = -alpha_t * (1 - p_t)^gamma * log(p_t)
    """
    p = torch.sigmoid(inputs)
    bce = F.binary_cross_entropy_with_logits(inputs, targets, reduction="none")
    p_t = p * targets + (1.0 - p) * (1.0 - targets)
    alpha_t = alpha * targets + (1.0 - alpha) * (1.0 - targets)
    focal_weight = alpha_t * (1.0 - p_t) ** gamma

    loss = focal_weight * bce

    if reduction == "sum":
        return loss.sum()
    elif reduction == "mean":
        return loss.mean()
    return loss


def manual_ciou_loss(
    pred_boxes: torch.Tensor,
    target_boxes: torch.Tensor,
    eps: float = 1e-7
) -> torch.Tensor:
    """
    Manually implemented Complete IoU (CIoU) Loss for boxes in [xmin, ymin, xmax, ymax] format.
    CIoU = IoU - (distance_penalty + aspect_ratio_penalty)
    Loss = 1 - CIoU
    """
    px1, py1, px2, py2 = pred_boxes[:, 0], pred_boxes[:, 1], pred_boxes[:, 2], pred_boxes[:, 3]
    tx1, ty1, tx2, ty2 = target_boxes[:, 0], target_boxes[:, 1], target_boxes[:, 2], target_boxes[:, 3]

    # Intersection area
    ix1 = torch.max(px1, tx1)
    iy1 = torch.max(py1, ty1)
    ix2 = torch.min(px2, tx2)
    iy2 = torch.min(py2, ty2)
    inter = torch.clamp(ix2 - ix1, min=0.0) * torch.clamp(iy2 - iy1, min=0.0)

    # Union area
    p_area = (px2 - px1) * (py2 - py1)
    t_area = (tx2 - tx1) * (ty2 - ty1)
    union = p_area + t_area - inter + eps
    iou = inter / union

    # Enclosing (convex hull) box
    cx1 = torch.min(px1, tx1)
    cy1 = torch.min(py1, ty1)
    cx2 = torch.max(px2, tx2)
    cy2 = torch.max(py2, ty2)
    c2 = (cx2 - cx1) ** 2 + (cy2 - cy1) ** 2 + eps

    # Central distance squared
    pcx, pcy = (px1 + px2) / 2.0, (py1 + py2) / 2.0
    tcx, tcy = (tx1 + tx2) / 2.0, (ty1 + ty2) / 2.0
    rho2 = (pcx - tcx) ** 2 + (pcy - tcy) ** 2

    # Aspect ratio penalty v and alpha
    pw, ph = torch.clamp(px2 - px1, min=eps), torch.clamp(py2 - py1, min=eps)
    tw, th = torch.clamp(tx2 - tx1, min=eps), torch.clamp(ty2 - ty1, min=eps)

    v = (4.0 / (math.pi ** 2)) * torch.pow(torch.atan(tw / th) - torch.atan(pw / ph), 2)
    with torch.no_grad():
        alpha_factor = v / ((1.0 - iou) + v + eps)

    ciou = iou - (rho2 / c2 + alpha_factor * v)
    ciou = torch.clamp(ciou, min=-1.0, max=1.0)
    return 1.0 - ciou


class LyraLoss(nn.Module):
    """
    Anchor-matched multi-task loss combining:
      1. Bounding box regression (Manual CIoU Loss)
      2. Objectness confidence (Manual Binary Focal Loss)
      3. UI class classification (Focal Loss / Cross-Entropy)
      4. Screen state classification (Cross-Entropy Loss)
    """
    def __init__(self, num_classes: int = 13, num_states: int = 7):
        super().__init__()
        self.num_classes = num_classes
        self.num_states = num_states
        self.anchors = torch.tensor(ANCHORS)  # Shape [3, 2] in normalized coords

    def forward(self, pred_det: torch.Tensor, pred_state: torch.Tensor, targets: dict):
        # pred_det shape: [B, 54, 13, 13]
        # pred_state shape: [B, 7]
        batch_size = pred_det.size(0)
        device = pred_det.device
        anchors = self.anchors.to(device)

        # Reshape pred_det to [B, 3, 18, 13, 13] -> [B, 3, 13, 13, 18]
        # 18 channels per anchor: (tx, ty, tw, th, conf, cls_0..12)
        pred_det = pred_det.view(batch_size, 3, 18, 13, 13).permute(0, 1, 3, 4, 2)

        # Build anchor-matched grid targets
        target_conf = torch.zeros((batch_size, 3, 13, 13), device=device)
        target_bbox = torch.zeros((batch_size, 3, 13, 13, 4), device=device)
        target_class = torch.zeros((batch_size, 3, 13, 13), dtype=torch.long, device=device)
        obj_mask = torch.zeros((batch_size, 3, 13, 13), dtype=torch.bool, device=device)

        for i in range(batch_size):
            boxes = targets["boxes"][i]    # [num_boxes, 4] normalized [0, 416]
            labels = targets["labels"][i]  # [num_boxes]

            for box, label in zip(boxes, labels):
                xmin, ymin, xmax, ymax = box
                w_norm = (xmax - xmin) / 416.0
                h_norm = (ymax - ymin) / 416.0
                xc_norm = (xmin + xmax) / 2.0 / 416.0
                yc_norm = (ymin + ymax) / 2.0 / 416.0

                if w_norm <= 0 or h_norm <= 0:
                    continue

                grid_x = int(xc_norm * 13.0)
                grid_y = int(yc_norm * 13.0)
                grid_x = max(0, min(grid_x, 12))
                grid_y = max(0, min(grid_y, 12))

                # Match to anchor with highest IoU
                box_wh = torch.tensor([w_norm, h_norm], device=device)
                anchor_ious = torch.min(box_wh[0], anchors[:, 0]) * torch.min(box_wh[1], anchors[:, 1]) / (
                    box_wh[0] * box_wh[1] + anchors[:, 0] * anchors[:, 1] - torch.min(box_wh[0], anchors[:, 0]) * torch.min(box_wh[1], anchors[:, 1])
                )
                best_anchor = torch.argmax(anchor_ious).item()

                target_conf[i, best_anchor, grid_y, grid_x] = 1.0
                target_bbox[i, best_anchor, grid_y, grid_x] = torch.tensor([
                    xmin / 416.0, ymin / 416.0, xmax / 416.0, ymax / 416.0
                ], device=device)
                target_class[i, best_anchor, grid_y, grid_x] = label
                obj_mask[i, best_anchor, grid_y, grid_x] = True

        # Extract predictions
        raw_tx = pred_det[..., 0]
        raw_ty = pred_det[..., 1]
        raw_tw = pred_det[..., 2]
        raw_th = pred_det[..., 3]
        conf_logits = pred_det[..., 4]
        class_logits = pred_det[..., 5:]  # [B, 3, 13, 13, 13]

        # Grid cell offsets for decoding predictions
        grid_y_idx, grid_x_idx = torch.meshgrid(
            torch.arange(13, device=device), torch.arange(13, device=device), indexing="ij"
        )

        # Decode predicted boxes to [xmin, ymin, xmax, ymax] normalized [0, 1]
        grid_x_idx = grid_x_idx.view(1, 1, 13, 13).expand(batch_size, 3, 13, 13)
        grid_y_idx = grid_y_idx.view(1, 1, 13, 13).expand(batch_size, 3, 13, 13)
        anchor_w = anchors[:, 0].view(1, 3, 1, 1).expand(batch_size, 3, 13, 13)
        anchor_h = anchors[:, 1].view(1, 3, 1, 1).expand(batch_size, 3, 13, 13)

        pxc = (torch.sigmoid(raw_tx) + grid_x_idx) / 13.0
        pyc = (torch.sigmoid(raw_ty) + grid_y_idx) / 13.0
        pw = torch.exp(raw_tw) * anchor_w
        ph = torch.exp(raw_th) * anchor_h

        pxmin = torch.clamp(pxc - pw / 2.0, min=0.0, max=1.0)
        pymin = torch.clamp(pyc - ph / 2.0, min=0.0, max=1.0)
        pxmax = torch.clamp(pxc + pw / 2.0, min=0.0, max=1.0)
        pymax = torch.clamp(pyc + ph / 2.0, min=0.0, max=1.0)

        pred_boxes_all = torch.stack([pxmin, pymin, pxmax, pymax], dim=-1)

        # 1. CIoU Bounding Box Loss (only on matched anchor cells)
        loss_bbox = torch.tensor(0.0, device=device)
        if obj_mask.sum() > 0:
            pred_obj_boxes = pred_boxes_all[obj_mask]
            target_obj_boxes = target_bbox[obj_mask]
            ciou = manual_ciou_loss(pred_obj_boxes, target_obj_boxes)
            loss_bbox = ciou.mean()

        # 2. Manual Focal Loss for Objectness Confidence
        loss_conf = manual_focal_loss(conf_logits, target_conf, alpha=0.25, gamma=2.0, reduction="mean")

        # 3. Class Classification Loss (Cross Entropy on object cells)
        loss_class = torch.tensor(0.0, device=device)
        if obj_mask.sum() > 0:
            pred_obj_class = class_logits[obj_mask]
            target_obj_class = target_class[obj_mask]
            loss_class = F.cross_entropy(pred_obj_class, target_obj_class)

        # 4. Screen State Classification Loss
        loss_state = F.cross_entropy(pred_state, targets["screen_state"])

        # Combine losses
        total_loss = 5.0 * loss_bbox + 2.0 * loss_conf + loss_class + loss_state

        return total_loss, {
            "loss": total_loss.item(),
            "bbox_loss": loss_bbox.item(),
            "conf_loss": loss_conf.item(),
            "class_loss": loss_class.item(),
            "state_loss": loss_state.item(),
        }
