"""
preprocessing.py — Image resize, normalization, letterboxing, and coordinate remapping for LYRA model.
"""

from typing import Tuple, List, Dict, Any
import numpy as np
import cv2
import torch


def letterbox_image(
    img: np.ndarray,
    target_shape: Tuple[int, int] = (416, 416),
    color: Tuple[int, int, int] = (114, 114, 114)
) -> Tuple[np.ndarray, float, Tuple[int, int]]:
    """
    Resizes image with aspect-ratio preserving letterboxing.
    Returns: (letterboxed_img, ratio, (pad_x, pad_y))
    """
    h_orig, w_orig = img.shape[:2]
    w_target, h_target = target_shape

    ratio = min(w_target / w_orig, h_target / h_orig)
    w_new = int(round(w_orig * ratio))
    h_new = int(round(h_orig * ratio))

    pad_x = (w_target - w_new) // 2
    pad_y = (h_target - h_new) // 2

    resized_img = cv2.resize(img, (w_new, h_new), interpolation=cv2.INTER_LINEAR)

    letterboxed_img = np.full((h_target, w_target, 3), color, dtype=np.uint8)
    letterboxed_img[pad_y : pad_y + h_new, pad_x : pad_x + w_new] = resized_img

    return letterboxed_img, ratio, (pad_x, pad_y)


def remap_bounding_boxes(
    boxes: List[List[float]],
    orig_shape: Tuple[int, int],
    target_shape: Tuple[int, int] = (416, 416)
) -> List[List[float]]:
    """
    Remaps bounding boxes from original image coordinates to letterboxed target coordinates.
    Boxes: [[xmin, ymin, xmax, ymax], ...]
    Returns remapped boxes in target_shape coordinate space.
    """
    h_orig, w_orig = orig_shape
    w_target, h_target = target_shape

    ratio = min(w_target / w_orig, h_target / h_orig)
    w_new = int(round(w_orig * ratio))
    h_new = int(round(h_orig * ratio))

    pad_x = (w_target - w_new) // 2
    pad_y = (h_target - h_new) // 2

    remapped = []
    for box in boxes:
        xmin, ymin, xmax, ymax = box
        rx1 = xmin * ratio + pad_x
        ry1 = ymin * ratio + pad_y
        rx2 = xmax * ratio + pad_x
        ry2 = ymax * ratio + pad_y

        rx1 = max(0.0, min(rx1, float(w_target)))
        ry1 = max(0.0, min(ry1, float(h_target)))
        rx2 = max(0.0, min(rx2, float(w_target)))
        ry2 = max(0.0, min(ry2, float(h_target)))

        if rx2 > rx1 and ry2 > ry1:
            remapped.append([rx1, ry1, rx2, ry2])

    return remapped


def preprocess_image_tensor(img: np.ndarray) -> torch.Tensor:
    """
    Converts HWC BGR uint8 numpy array to CHW RGB float32 PyTorch tensor normalized [0, 1].
    """
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    tensor = torch.from_numpy(rgb).permute(2, 0, 1).float() / 255.0
    return tensor
