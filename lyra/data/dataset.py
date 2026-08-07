"""
dataset.py — PyTorch Dataset loader for screenshots, UI element bounding boxes, and screen state classes.
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

import cv2
import numpy as np
import torch
from torch.utils.data import Dataset

from lyra.config import (
    UI_ELEMENT_CLASSES,
    SCREEN_STATE_CLASSES,
)
from lyra.data.preprocessing import (
    letterbox_image,
    remap_bounding_boxes,
    preprocess_image_tensor,
)
from lyra.data.augmentation import UIConservativeAugmentor


class LyraDataset(Dataset):
    """
    PyTorch Dataset loading screenshot images, UI element bounding boxes,
    element class labels, and overall screen state classification labels.
    """

    def __init__(
        self,
        data_dir: Path,
        raw_images_dir: Optional[Path] = None,
        target_size: Tuple[int, int] = (416, 416),
        is_training: bool = False,
    ):
        self.data_dir = Path(data_dir)
        self.raw_images_dir = Path(raw_images_dir) if raw_images_dir else self.data_dir
        self.target_size = target_size
        self.is_training = is_training
        self.augmentor = UIConservativeAugmentor() if is_training else None

        self.ui_label_to_idx = {name: idx for idx, name in enumerate(UI_ELEMENT_CLASSES)}
        self.screen_state_to_idx = {name: idx for idx, name in enumerate(SCREEN_STATE_CLASSES)}

        # Find all json annotation files
        self.json_paths = sorted(list(self.data_dir.glob("*.json")))

    def __len__(self) -> int:
        return len(self.json_paths)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        json_path = self.json_paths[idx]
        with open(json_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

        filename = meta.get("filename", f"{json_path.stem}.png")
        img_path = self.raw_images_dir / filename
        if not img_path.exists():
            img_path = self.data_dir / filename

        img = cv2.imread(str(img_path))
        if img is None:
            # Fallback black image if missing
            img = np.zeros((1600, 720, 3), dtype=np.uint8)

        orig_h, orig_w = img.shape[:2]

        # Apply augmentation if in training mode
        if self.is_training and self.augmentor:
            img = self.augmentor(img)

        # Letterbox image to target resolution
        letterboxed_img, ratio, pad = letterbox_image(img, target_shape=self.target_size)
        img_tensor = preprocess_image_tensor(letterboxed_img)

        # Extract screen state classification label
        screen_state_str = meta.get("screen_state_tag", "UNKNOWN")
        screen_state_idx = self.screen_state_to_idx.get(screen_state_str, self.screen_state_to_idx["UNKNOWN"])

        # Extract object bounding boxes and labels
        objects = meta.get("objects", [])
        boxes = []
        labels = []

        raw_boxes = [obj.get("bbox", []) for obj in objects if len(obj.get("bbox", [])) == 4]
        raw_labels = [obj.get("label", "unknown") for obj in objects if len(obj.get("bbox", [])) == 4]

        # Remap coordinates to letterboxed space
        remapped_boxes = remap_bounding_boxes(raw_boxes, orig_shape=(orig_h, orig_w), target_shape=self.target_size)

        for box, lbl_str in zip(remapped_boxes, raw_labels):
            lbl_idx = self.ui_label_to_idx.get(lbl_str, 0)
            boxes.append(box)
            labels.append(lbl_idx)

        boxes_tensor = torch.tensor(boxes, dtype=torch.float32) if boxes else torch.zeros((0, 4), dtype=torch.float32)
        labels_tensor = torch.tensor(labels, dtype=torch.long) if labels else torch.zeros((0,), dtype=torch.long)
        screen_state_tensor = torch.tensor(screen_state_idx, dtype=torch.long)

        targets = {
            "boxes": boxes_tensor,
            "labels": labels_tensor,
            "screen_state": screen_state_tensor,
            "orig_size": torch.tensor([orig_h, orig_w], dtype=torch.long),
        }

        return img_tensor, targets
