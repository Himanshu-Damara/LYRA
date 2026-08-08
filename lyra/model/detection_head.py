"""
detection_head.py — Anchor-based detection head with 3 scale priors per grid cell.
"""

import torch
import torch.nn as nn


# Predefined anchor scale priors in normalized [0, 1] relative to 416x416 input space:
# Anchor 0: (32x32 pixels) — Small UI icons / heart buttons
# Anchor 1: (64x64 pixels) — Medium app icons / shutter button
# Anchor 2: (128x128 pixels) — Large UI elements / story thumbnails
ANCHORS = [
    (32.0 / 416.0, 32.0 / 416.0),
    (64.0 / 416.0, 64.0 / 416.0),
    (128.0 / 416.0, 128.0 / 416.0),
]


class LyraDetectionHead(nn.Module):
    """
    Anchor-based detection head predicting UI element bounding box offsets,
    objectness confidence, and class probabilities for a 13x13 grid with 3 anchors per cell.

    Output tensor shape: [B, 54, 13, 13]
      - 3 anchors per cell
      - 18 channels per anchor: (tx, ty, tw, th, conf, cls_0..cls_12)
    """
    def __init__(self, num_classes: int = 13, num_anchors: int = 3):
        super().__init__()
        self.num_classes = num_classes
        self.num_anchors = num_anchors
        self.anchors = ANCHORS
        
        # 5 parameters (tx, ty, tw, th, conf) + num_classes per anchor
        self.channels_per_anchor = 5 + num_classes
        self.output_channels = num_anchors * self.channels_per_anchor
        
        self.conv = nn.Sequential(
            nn.Conv2d(512, 256, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(256),
            nn.LeakyReLU(0.1, inplace=True),
            nn.Conv2d(256, 256, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(256),
            nn.LeakyReLU(0.1, inplace=True),
            nn.Conv2d(256, self.output_channels, kernel_size=1)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Input: [B, 512, 13, 13]
        # Output: [B, 54, 13, 13]
        return self.conv(x)
