"""
accessibility.py — Android Accessibility Service integration.

Uses ADB to query the Android UI hierarchy (uiautomator dump) to supplement
vision-based detection with structured accessibility data like text labels,
content descriptions, and input field states.
"""

import subprocess
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional

from lyra.config import ADB_PATH


class AccessibilityReader:
    """
    Reads the Android accessibility tree via `uiautomator dump`
    to supplement the vision model with text and structural data.
    """

    def __init__(self):
        self.adb_path = str(ADB_PATH)

    def dump_ui_hierarchy(self) -> Optional[str]:
        """
        Dumps the current UI hierarchy XML from the connected device.
        Returns the XML string or None on failure.
        """
        try:
            # Dump to device temp file
            subprocess.run(
                [self.adb_path, "shell", "uiautomator", "dump", "/sdcard/ui_dump.xml"],
                capture_output=True, text=True, check=True, timeout=10, encoding='utf-8', errors='replace'
            )
            # Pull the XML content
            result = subprocess.run(
                [self.adb_path, "shell", "cat", "/sdcard/ui_dump.xml"],
                capture_output=True, text=True, check=True, timeout=10, encoding='utf-8', errors='replace'
            )
            return result.stdout.strip()
        except Exception:
            return None

    def get_ui_elements(self) -> List[Dict]:
        """
        Parses the UI hierarchy and returns a list of interactive elements
        with their text, content-description, bounds, and class.
        """
        xml_str = self.dump_ui_hierarchy()
        if not xml_str:
            return []

        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError:
            return []

        elements = []
        for node in root.iter("node"):
            text = node.attrib.get("text", "")
            content_desc = node.attrib.get("content-desc", "")
            clickable = node.attrib.get("clickable", "false") == "true"
            bounds_str = node.attrib.get("bounds", "")
            class_name = node.attrib.get("class", "")
            focusable = node.attrib.get("focusable", "false") == "true"

            # Only include elements with meaningful content
            if text or content_desc or clickable:
                bounds = self._parse_bounds(bounds_str)
                elements.append({
                    "text": text,
                    "content_desc": content_desc,
                    "class": class_name,
                    "clickable": clickable,
                    "focusable": focusable,
                    "bounds": bounds,
                })

        return elements

    def find_element_by_text(self, target_text: str) -> Optional[Dict]:
        """Finds the first UI element whose text contains the target string."""
        elements = self.get_ui_elements()
        target_lower = target_text.lower()
        for elem in elements:
            if target_lower in elem["text"].lower() or target_lower in elem["content_desc"].lower():
                return elem
        return None

    def get_focused_input(self) -> Optional[Dict]:
        """Returns the currently focused input field, if any."""
        elements = self.get_ui_elements()
        for elem in elements:
            if elem.get("focusable") and "EditText" in elem.get("class", ""):
                return elem
        return None

    @staticmethod
    def _parse_bounds(bounds_str: str) -> List[int]:
        """
        Parses Android bounds string '[x1,y1][x2,y2]' into [x1, y1, x2, y2].
        """
        try:
            parts = bounds_str.replace("][", ",").strip("[]").split(",")
            return [int(p) for p in parts]
        except (ValueError, IndexError):
            return [0, 0, 0, 0]


# Singleton instance
accessibility = AccessibilityReader()
