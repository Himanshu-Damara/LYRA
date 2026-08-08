"""
model.py — Combined LyraNet (backbone + detection head + classification head).
"""

import torch
import torch.nn as nn
from lyra.model.backbone import LyraBackbone
from lyra.model.detection_head import LyraDetectionHead
from lyra.model.classification_head import LyraClassificationHead


class LyraNet(nn.Module):
    """
    Combined Multi-Task Learning Network for mobile UI automation.
    Branches into:
      1. UI element object detection (grid-based YOLOv1 style)
      2. Whole-screen classification (screen-state tag)
    """
    def __init__(self, num_classes: int = 13, num_states: int = 7):
        super().__init__()
        self.backbone = LyraBackbone()
        self.detection_head = LyraDetectionHead(num_classes=num_classes)
        self.classification_head = LyraClassificationHead(num_states=num_states)

    def forward(self, x: torch.Tensor):
        # Input: [B, 3, 416, 416]
        features = self.backbone(x)
        det_out = self.detection_head(features)      # -> [B, 54, 13, 13]  (3 anchors × 18 channels)
        class_out = self.classification_head(features)  # -> [B, 7]
        return det_out, class_out
