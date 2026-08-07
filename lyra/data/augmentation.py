"""
augmentation.py — Conservative data augmentation for phone UI screenshots.
"""

import random
import numpy as np
import cv2


class UIConservativeAugmentor:
    """
    Safe data augmentations tailored for mobile UI screenshots.
    Preserves text orientation and icon geometry (no flips).
    """

    def __init__(
        self,
        brightness_range: float = 0.15,
        contrast_range: float = 0.15,
        saturation_range: float = 0.15,
        prob: float = 0.5,
    ):
        self.brightness_range = brightness_range
        self.contrast_range = contrast_range
        self.saturation_range = saturation_range
        self.prob = prob

    def __call__(self, img: np.ndarray) -> np.ndarray:
        if random.random() > self.prob:
            return img

        augmented = img.astype(np.float32)

        # Random brightness adjust
        if random.random() < 0.5:
            delta = random.uniform(-self.brightness_range * 255, self.brightness_range * 255)
            augmented = np.clip(augmented + delta, 0, 255)

        # Random contrast adjust
        if random.random() < 0.5:
            alpha = random.uniform(1.0 - self.contrast_range, 1.0 + self.contrast_range)
            mean = np.mean(augmented)
            augmented = np.clip((augmented - mean) * alpha + mean, 0, 255)

        augmented = augmented.astype(np.uint8)

        # Random HSV saturation adjust
        if random.random() < 0.5:
            hsv = cv2.cvtColor(augmented, cv2.COLOR_BGR2HSV).astype(np.float32)
            sat_scale = random.uniform(1.0 - self.saturation_range, 1.0 + self.saturation_range)
            hsv[:, :, 1] = np.clip(hsv[:, :, 1] * sat_scale, 0, 255)
            augmented = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

        return augmented
