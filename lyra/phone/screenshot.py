"""
screenshot.py — Real Python/ADB screenshot capture for connected Android device.

Captures the current screen of the connected physical phone using ADB,
reads the raw image into memory or saves it to disk, and validates the output.
Automatically detects and returns image resolution (width, height).
"""

import subprocess
import time
from pathlib import Path
from typing import Tuple, Optional
import cv2
import numpy as np

from lyra.config import ADB_PATH, RAW_SCREENSHOTS_DIR


def capture_screenshot(
    output_path: Optional[Path] = None,
    save_to_raw_dir: bool = False,
    filename_prefix: str = "screenshot"
) -> Tuple[np.ndarray, int, int, Path]:
    """
    Captures the current phone screen via ADB binary.

    Args:
        output_path: Specific Path to save screenshot. If None, auto-generates path.
        save_to_raw_dir: If True and output_path is None, saves in RAW_SCREENSHOTS_DIR.
        filename_prefix: Prefix for auto-generated filename.

    Returns:
        Tuple containing:
            - image (np.ndarray): Image in BGR format (OpenCV format)
            - width (int): Screen width in pixels
            - height (int): Screen height in pixels
            - save_path (Path): Path where image was saved
    """
    if output_path is None:
        timestamp = int(time.time() * 1000)
        target_dir = RAW_SCREENSHOTS_DIR if save_to_raw_dir else RAW_SCREENSHOTS_DIR.parent / "temp"
        target_dir.mkdir(parents=True, exist_ok=True)
        output_path = target_dir / f"{filename_prefix}_{timestamp}.png"
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    # Command: adb exec-out screencap -p (streams PNG binary directly)
    cmd = [str(ADB_PATH), "exec-out", "screencap", "-p"]
    
    try:
        res = subprocess.run(cmd, capture_output=True, check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ADB screencap failed: {e.stderr.decode('utf-8', errors='ignore')}") from e

    raw_bytes = res.stdout
    if not raw_bytes:
        raise RuntimeError("ADB screencap returned empty output!")

    # Decode bytes using OpenCV
    image_array = np.frombuffer(raw_bytes, dtype=np.uint8)
    image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

    if image is None or image.size == 0:
        raise ValueError("Failed to decode screenshot image from raw ADB bytes!")

    height, width, _ = image.shape

    # Save image file locally
    success = cv2.imwrite(str(output_path), image)
    if not success or not output_path.exists():
        raise IOError(f"Failed to save screenshot image to {output_path}")

    return image, width, height, output_path


def get_screen_resolution() -> Tuple[int, int]:
    """
    Queries actual device display resolution via ADB.
    Returns: (width, height) in pixels.
    """
    cmd = [str(ADB_PATH), "shell", "wm", "size"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        out = res.stdout.strip()
        # Typical output: "Physical size: 720x1600"
        if "Physical size:" in out:
            size_str = out.split("Physical size:")[-1].strip().split()[-1]
            w_str, h_str = size_str.split("x")
            return int(w_str), int(h_str)
    except Exception:
        pass

    # Fallback to screenshot dimensions if wm size fails
    _, width, height, _ = capture_screenshot()
    return width, height


if __name__ == "__main__":
    print("Testing real screenshot capture via ADB...")
    img, w, h, path = capture_screenshot(filename_prefix="test_capture")
    print("[SUCCESS] Screenshot captured successfully!")
    print(f"  Dimensions: {w}x{h} pixels")
    print(f"  Saved to: {path}")
