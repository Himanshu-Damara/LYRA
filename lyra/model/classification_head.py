"""
classification_head.py — Custom classification head for screen state.
"""

import torch
import torch.nn as nn


class LyraClassificationHead(nn.Module):
    """
    Classification head predicting global screen states from spatial feature maps.
    Output tensor shape: [B, 7]
    """
    def __init__(self, num_states: int = 7):
        super().__init__()
        self.avgpool = nn.AdaptiveAvgPool2d((1, 1))
        self.fc = nn.Sequential(
            nn.Flatten(),
            nn.Linear(512, 128),
            nn.ReLU(inplace=True),
            nn.Dropout(0.3),
            nn.Linear(128, num_states)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Input shape: [B, 512, 13, 13]
        x = self.avgpool(x)  # -> [B, 512, 1, 1]
        x = self.fc(x)       # -> [B, 7]
        return x
