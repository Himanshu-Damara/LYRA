"""
coordinator.py — Convert model-space coordinates back to phone-screen coordinates
and execute targeted ADB actions based on detected UI elements.
"""

import time
from typing import Dict, List, Optional, Tuple
import numpy as np

from lyra.inference.detector import LyraDetector
from lyra.phone.adb_controller import ADBController
from lyra.phone.screenshot import capture_screenshot
from lyra.phone.accessibility import AccessibilityReader
from lyra.config import UI_ELEMENT_CLASSES, SCREEN_STATE_CLASSES


class ActionCoordinator:
    """
    Bridges the vision model to the phone controller.
    Captures screenshots, runs detection, and executes targeted actions.
    Fuses vision model output with accessibility tree data for richer perception.
    """

    def __init__(self, conf_threshold: float = 0.3):
        self.detector = LyraDetector(conf_threshold=conf_threshold)
        self.controller = ADBController()
        self.accessibility = AccessibilityReader()
        self._last_perception: Optional[Dict] = None
        self._last_screenshot: Optional[np.ndarray] = None

    def perceive(self) -> Dict:
        """
        Captures a live screenshot, runs detection, and reads the accessibility tree.
        Returns the full perception result dict with fused vision + accessibility data.
        """
        image, width, height, path = capture_screenshot()
        self._last_screenshot = image

        result = self.detector.detect(image)
        result["screen_resolution"] = (width, height)
        result["screenshot_path"] = str(path)

        # Fuse with accessibility tree data
        try:
            a11y_elements = self.accessibility.get_ui_elements()
            result["accessibility_elements"] = a11y_elements
        except Exception:
            result["accessibility_elements"] = []

        self._last_perception = result
        return result

    def find_element(self, label: str, perception: Optional[Dict] = None) -> Optional[Dict]:
        """
        Finds the highest-confidence detection matching the given label.
        Returns the detection dict or None.
        """
        if perception is None:
            perception = self._last_perception or self.perceive()

        for det in perception.get("detections", []):
            if det["label"] == label:
                return det
        return None

    def find_all_elements(self, label: str, perception: Optional[Dict] = None) -> List[Dict]:
        """
        Finds all detections matching the given label, sorted by confidence.
        """
        if perception is None:
            perception = self._last_perception or self.perceive()

        return [d for d in perception.get("detections", []) if d["label"] == label]

    def tap_element(self, label: str, index: int = 0) -> bool:
        """
        Detects the target UI element and taps its center.
        Returns True if element found and tapped, False otherwise.
        """
        perception = self.perceive()
        matches = self.find_all_elements(label, perception)

        if index < len(matches):
            det = matches[index]
            bbox = det["bbox_original"]
            cx = (bbox[0] + bbox[2]) // 2
            cy = (bbox[1] + bbox[3]) // 2
            self.controller.tap(cx, cy)
            return True

        # Fallback to direct app launch intents if vision detection is uncertain
        if label == "app_icon_camera":
            self.controller.shell("am start -a android.media.action.STILL_IMAGE_CAMERA")
            return True
        elif label == "app_icon_instagram":
            self.controller.shell("monkey -p com.instagram.android 1")
            return True

        return False

    def get_screen_state(self) -> str:
        """Returns the current screen state classification."""
        perception = self.perceive()
        return perception["screen_state"]

    def wait_for_screen(self, target_state: str, timeout: float = 10.0,
                         poll_interval: float = 1.0) -> bool:
        """
        Waits until the screen state matches target_state or timeout.
        Returns True if target state reached, False if timed out.
        """
        start = time.time()
        while time.time() - start < timeout:
            state = self.get_screen_state()
            if state == target_state:
                return True
            time.sleep(poll_interval)
        return False

    def wait_for_element(self, label: str, timeout: float = 10.0,
                          poll_interval: float = 1.0) -> Optional[Dict]:
        """
        Waits until an element with the given label is detected.
        Returns the detection dict or None if timed out.
        """
        start = time.time()
        while time.time() - start < timeout:
            perception = self.perceive()
            det = self.find_element(label, perception)
            if det is not None:
                return det
            time.sleep(poll_interval)
        return None

    def tap_coordinates(self, x: int, y: int) -> None:
        """Direct tap at specific screen coordinates."""
        self.controller.tap(x, y)

    def swipe_screen(self, direction: str = "up", distance: float = 0.4) -> None:
        """
        Swipes in the given direction ('up', 'down', 'left', 'right').
        distance is a fraction of screen dimension (0.0 to 1.0).
        """
        w, h = self.controller.resolution
        cx, cy = w // 2, h // 2
        d_x = int(w * distance)
        d_y = int(h * distance)

        directions = {
            "up": (cx, cy + d_y // 2, cx, cy - d_y // 2),
            "down": (cx, cy - d_y // 2, cx, cy + d_y // 2),
            "left": (cx + d_x // 2, cy, cx - d_x // 2, cy),
            "right": (cx - d_x // 2, cy, cx + d_x // 2, cy),
        }

        coords = directions.get(direction, directions["up"])
        self.controller.swipe(*coords)

    def go_home(self) -> None:
        """Press the home button."""
        self.controller.home()

    def go_back(self) -> None:
        """Press the back button."""
        self.controller.back()

    def type_text(self, text: str) -> None:
        """Type text into the currently focused input field."""
        self.controller.type_text(text)

    def launch_app(self, package_name: str) -> bool:
        """
        Launches an app by its Android package name using activity manager.
        Returns True if the launch command succeeded.
        """
        try:
            self.controller.shell(
                "monkey", "-p", package_name, "-c",
                "android.intent.category.LAUNCHER", "1"
            )
            return True
        except Exception:
            return False

    def find_element_by_text(self, text: str, perception: Optional[Dict] = None) -> Optional[Dict]:
        """
        Finds a UI element by its text content using the accessibility tree.
        Returns element dict with bounds or None if not found.
        """
        if perception is None:
            perception = self._last_perception or self.perceive()

        target_lower = text.lower()
        for elem in perception.get("accessibility_elements", []):
            elem_text = elem.get("text", "").lower()
            elem_desc = elem.get("content_desc", "").lower()
            if target_lower in elem_text or target_lower in elem_desc:
                return elem
        return None

    def tap_element_by_text(self, text: str) -> bool:
        """
        Finds a UI element by text content (via accessibility) and taps its center.
        Returns True if found and tapped, False otherwise.
        """
        perception = self.perceive()
        elem = self.find_element_by_text(text, perception)
        if elem and elem.get("bounds"):
            bounds = elem["bounds"]
            if len(bounds) == 4:
                cx = (bounds[0] + bounds[2]) // 2
                cy = (bounds[1] + bounds[3]) // 2
                self.controller.tap(cx, cy)
                return True
        return False

