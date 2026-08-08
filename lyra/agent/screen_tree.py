"""
screen_tree.py — LLM-readable indented UI hierarchy from the accessibility tree.

Inspired by Ghost in the Droid's get_screen_tree():
  Each node: [idx] ClassName "label" [clickable] [x1,y1][x2,y2]

Produces a compact, structured representation of the phone screen that
an LLM can read and reason about directly.
"""

import xml.etree.ElementTree as ET
import re
from typing import Optional, List, Dict

from lyra.phone.accessibility import AccessibilityReader


def get_screen_tree(max_nodes: int = 60) -> str:
    """
    Get an LLM-readable indented UI hierarchy tree from the connected device.

    Format per node:
      [idx] ClassName "label" [clickable,scrollable] [x1,y1][x2,y2]

    Skips deep non-interactive unlabelled nodes. Returns a string the LLM can
    read directly to understand screen layout and pick elements to interact with.
    """
    reader = AccessibilityReader()
    xml_str = reader.dump_ui_hierarchy()

    if not xml_str:
        return "(empty screen — could not read UI hierarchy)"

    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return "(XML parse error)"

    lines = []
    idx_counter = [0]

    def _walk(node, depth=0):
        if len(lines) >= max_nodes:
            return

        text_val = node.get("text", "") or ""
        desc = node.get("content-desc", "") or ""
        rid = node.get("resource-id", "") or ""
        cls_full = node.get("class", "") or ""
        cls = cls_full.split(".")[-1] if "." in cls_full else cls_full
        bounds = node.get("bounds", "")
        clickable = node.get("clickable", "") == "true"
        scrollable = node.get("scrollable", "") == "true"
        focusable = node.get("focusable", "") == "true"
        label = text_val or desc

        # Only show nodes the LLM can actually use:
        # - Has visible text/description, OR
        # - Is interactive (clickable/scrollable/focusable)
        is_useful = bool(label) or clickable or scrollable
        if not is_useful:
            # Still walk children — useful nodes may be nested
            for child in node:
                _walk(child, depth)
            return

        idx_counter[0] += 1
        idx = idx_counter[0]
        indent = "  " * min(depth, 6)
        flags = []
        if clickable:
            flags.append("clickable")
        if scrollable:
            flags.append("scrollable")
        if focusable and "EditText" in cls_full:
            flags.append("input")
        flag_str = f" [{','.join(flags)}]" if flags else ""
        label_str = f' "{label}"' if label else ""

        # Show resource-id only for unlabelled interactive elements
        rid_str = ""
        if not label and rid:
            rid_short = rid.split("/")[-1] if "/" in rid else rid
            rid_str = f' "{rid_short}"'

        lines.append(f"{indent}[{idx}] {cls}{label_str}{rid_str}{flag_str} {bounds}")

        for child in node:
            _walk(child, depth + 1)

    for child in root:
        _walk(child, 0)

    # Detect if the page might be scrollable
    try:
        all_y = []
        for n in root.iter("node"):
            b = n.get("bounds", "")
            nums = re.findall(r"\d+", b)
            if len(nums) == 4:
                all_y.append(int(nums[3]))
        if all_y:
            max_y = max(all_y)
            # Estimate screen height from widest element
            screen_h = 0
            for n in root.iter("node"):
                b = n.get("bounds", "")
                nums = re.findall(r"\d+", b)
                if len(nums) == 4 and int(nums[2]) > 400:
                    screen_h = max(screen_h, int(nums[3]))
            if screen_h and max_y >= screen_h - 50 and len(lines) > 10:
                lines.append("\n[Page likely scrollable — swipe up to see more]")
    except Exception:
        pass

    return "\n".join(lines) if lines else "(no interactive elements found)"


def get_interactive_elements() -> List[Dict]:
    """
    Get interactive UI elements as a structured list.
    Each element: {idx, text, content_desc, class, bounds, center, clickable}.

    These indices can be used for precise element targeting.
    """
    reader = AccessibilityReader()
    xml_str = reader.dump_ui_hierarchy()

    if not xml_str:
        return []

    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return []

    elements = []

    for node in root.iter("node"):
        text = node.get("text", "") or ""
        desc = node.get("content-desc", "") or ""
        rid = node.get("resource-id", "") or ""
        cls_full = node.get("class", "") or ""
        cls = cls_full.split(".")[-1] if "." in cls_full else cls_full
        bounds_str = node.get("bounds", "")
        clickable = node.get("clickable", "") == "true"
        scrollable = node.get("scrollable", "") == "true"

        # Only include meaningful elements
        if not clickable and not scrollable and not text and not desc:
            continue

        # Parse bounds
        bounds_nums = re.findall(r"\d+", bounds_str)
        if len(bounds_nums) != 4:
            continue
        x1, y1, x2, y2 = int(bounds_nums[0]), int(bounds_nums[1]), int(bounds_nums[2]), int(bounds_nums[3])
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

        elements.append({
            "idx": len(elements),
            "text": text,
            "content_desc": desc,
            "resource_id": rid.split("/")[-1] if "/" in rid else rid,
            "class": cls,
            "bounds": [x1, y1, x2, y2],
            "center": {"x": cx, "y": cy},
            "clickable": clickable,
            "scrollable": scrollable,
        })

    return elements
