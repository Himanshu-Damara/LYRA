"""
perception.py — Unified multi-modal perception orchestrator.

Fuses three signal sources into a comprehensive screen understanding:
  1. Vision Model (LyraNet): UI element detection + screen state classification
  2. Accessibility Tree (uiautomator): Text labels, clickable state, content descriptions
  3. OCR (optional): On-screen text reading for elements missed by accessibility

Provides a structured ScreenState object that the LLM planner can consume.
"""

import time
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field

from lyra.phone.screenshot import capture_screenshot, capture_screenshot_in_memory
from lyra.phone.accessibility import AccessibilityReader
from lyra.config import UI_ELEMENT_CLASSES, SCREEN_STATE_CLASSES


@dataclass
class UIElement:
    """A unified UI element from any perception source."""
    element_id: int
    source: str  # "vision", "accessibility", "ocr"
    text: str = ""
    label: str = ""
    content_desc: str = ""
    clickable: bool = False
    bounds: List[int] = field(default_factory=list)
    confidence: float = 0.0
    element_class: str = ""

    @property
    def center(self) -> Tuple[int, int]:
        """Center coordinates of the element."""
        if len(self.bounds) == 4:
            return (self.bounds[0] + self.bounds[2]) // 2, (self.bounds[1] + self.bounds[3]) // 2
        return (0, 0)

    @property
    def display_name(self) -> str:
        """Human-readable name for this element."""
        return self.text or self.content_desc or self.label or f"element_{self.element_id}"


@dataclass
class ScreenState:
    """Complete representation of the current phone screen."""
    screen_class: str = "UNKNOWN"
    screen_confidence: float = 0.0
    elements: List[UIElement] = field(default_factory=list)
    resolution: Tuple[int, int] = (0, 0)
    screenshot_path: str = ""
    raw_vision: Optional[Dict] = None
    raw_accessibility: Optional[List[Dict]] = None
    perception_time_ms: float = 0.0

    def to_text_description(self, max_elements: int = 20) -> str:
        """
        Converts the screen state into a natural language description
        suitable for LLM consumption.
        """
        lines = [
            f"Screen: {self.screen_class} ({self.screen_confidence:.0%} confidence)",
            f"Resolution: {self.resolution[0]}x{self.resolution[1]}",
            f"Total elements: {len(self.elements)}",
        ]

        if self.elements:
            lines.append("\nUI Elements:")
            for elem in self.elements[:max_elements]:
                click_str = " [clickable]" if elem.clickable else ""
                source_str = f" ({elem.source})"
                bounds_str = f" at {elem.bounds}" if elem.bounds else ""
                lines.append(
                    f"  [{elem.element_id}] \"{elem.display_name}\"{click_str}{source_str}{bounds_str}"
                )
            if len(self.elements) > max_elements:
                lines.append(f"  ... and {len(self.elements) - max_elements} more")

        return "\n".join(lines)

    def find_by_text(self, text: str) -> Optional[UIElement]:
        """Find the first element containing the given text."""
        text_lower = text.lower()
        for elem in self.elements:
            if (text_lower in elem.text.lower() or
                text_lower in elem.content_desc.lower() or
                text_lower in elem.label.lower()):
                return elem
        return None

    def find_clickable_elements(self) -> List[UIElement]:
        """Return all clickable elements."""
        return [e for e in self.elements if e.clickable]

    def to_dict(self) -> Dict:
        """Convert to a dict for JSON serialization or LLM consumption."""
        return {
            "screen_class": self.screen_class,
            "screen_confidence": self.screen_confidence,
            "resolution": self.resolution,
            "elements": [
                {
                    "id": e.element_id,
                    "text": e.display_name,
                    "clickable": e.clickable,
                    "bounds": e.bounds,
                    "source": e.source,
                }
                for e in self.elements
            ],
        }


class PerceptionEngine:
    """
    Multi-modal perception engine that fuses vision, accessibility, and OCR
    into a unified ScreenState.
    """

    def __init__(self, use_vision: bool = True, use_accessibility: bool = True,
                 use_ocr: bool = False):
        self.use_vision = use_vision
        self.use_accessibility = use_accessibility
        self.use_ocr = use_ocr

        # Lazy-loaded components
        self._detector = None
        self._accessibility = None
        self._ocr = None

    @property
    def detector(self):
        """Lazy-load the vision detector."""
        if self._detector is None and self.use_vision:
            try:
                from lyra.inference.detector import LyraDetector
                self._detector = LyraDetector()
            except Exception as e:
                print(f"  [PERCEPTION] Vision model unavailable: {e}")
                self.use_vision = False
        return self._detector

    @property
    def accessibility(self):
        """Lazy-load the accessibility reader."""
        if self._accessibility is None and self.use_accessibility:
            self._accessibility = AccessibilityReader()
        return self._accessibility

    def perceive(self, include_screenshot: bool = True) -> ScreenState:
        """
        Capture and fuse all perception signals into a unified ScreenState.

        Args:
            include_screenshot: Whether to save screenshot to disk

        Returns:
            A ScreenState object with all detected elements
        """
        start_time = time.time()
        state = ScreenState()
        element_id_counter = 0

        # 1. Capture screenshot
        if include_screenshot:
            image, width, height, path = capture_screenshot()
            state.resolution = (width, height)
            state.screenshot_path = str(path)
        else:
            image, width, height = capture_screenshot_in_memory()
            state.resolution = (width, height)

        # 2. Vision model detection
        if self.use_vision and self.detector:
            try:
                vision_result = self.detector.detect(image)
                state.screen_class = vision_result.get("screen_state", "UNKNOWN")
                state.screen_confidence = vision_result.get("screen_confidence", 0.0)
                state.raw_vision = vision_result

                for det in vision_result.get("detections", []):
                    element_id_counter += 1
                    state.elements.append(UIElement(
                        element_id=element_id_counter,
                        source="vision",
                        label=det.get("label", ""),
                        confidence=det.get("confidence", 0.0),
                        bounds=det.get("bbox_original", []),
                    ))
            except Exception as e:
                print(f"  [PERCEPTION] Vision detection failed: {e}")

        # 3. Accessibility tree
        if self.use_accessibility and self.accessibility:
            try:
                a11y_elements = self.accessibility.get_ui_elements()
                state.raw_accessibility = a11y_elements

                for elem in a11y_elements:
                    # Skip elements with no useful information
                    text = elem.get("text", "")
                    desc = elem.get("content_desc", "")
                    if not text and not desc and not elem.get("clickable"):
                        continue

                    element_id_counter += 1
                    state.elements.append(UIElement(
                        element_id=element_id_counter,
                        source="accessibility",
                        text=text,
                        content_desc=desc,
                        clickable=elem.get("clickable", False),
                        bounds=elem.get("bounds", []),
                        element_class=elem.get("class", ""),
                    ))
            except Exception as e:
                print(f"  [PERCEPTION] Accessibility read failed: {e}")

        # 4. OCR (placeholder for future integration)
        # This would add EasyOCR/PaddleOCR text regions as UIElements

        state.perception_time_ms = (time.time() - start_time) * 1000

        return state
