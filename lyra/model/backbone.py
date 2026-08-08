"""
backbone.py — ResNet-18 backbone with ImageNet pre-trained feature extraction.
"""

import torch
import torch.nn as nn
import torchvision.models as models


class LyraBackbone(nn.Module):
    """
    ImageNet pre-trained ResNet-18 feature extractor.
    Takes input image [B, 3, 416, 416] and outputs feature map [B, 512, 13, 13].
    """
    def __init__(self, pretrained: bool = True):
        super().__init__()
        weights = models.ResNet18_Weights.DEFAULT if pretrained else None
        resnet = models.resnet18(weights=weights)
        
        self.conv1 = resnet.conv1
        self.bn1 = resnet.bn1
        self.relu = resnet.relu
        self.maxpool = resnet.maxpool
        
        self.layer1 = resnet.layer1  # -> 64 channels, 104x104
        self.layer2 = resnet.layer2  # -> 128 channels, 52x52
        self.layer3 = resnet.layer3  # -> 256 channels, 26x26
        self.layer4 = resnet.layer4  # -> 512 channels, 13x13

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu(x)
        x = self.maxpool(x)
        
        x = self.layer1(x)
        x = self.layer2(x)
        x = self.layer3(x)
        x = self.layer4(x)
        return x
