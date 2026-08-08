"""
a11y_diff.py — Before/after accessibility tree diff.

Inspired by Ghost in the Droid / DroidRun / AndroidWorld pattern:
after a UI action, show the agent *what changed* (which elements appeared
or disappeared) instead of making it re-read the whole tree.

The diff is purely additive — it's appended to a tool result, never alters
the action that ran.
"""

from typing import List, Dict, Optional, Tuple

# How many added/removed entries to list before truncating
_MAX_LISTED = 8
# Position-bucket size (px). Elements whose centers land in the same
# bucket are treated as the same slot, so sub-pixel jitter doesn't
# register as a change.
_POS_BUCKET = 40


def element_label(el: Dict) -> str:
    """Human-readable label for an element."""
    return (el.get("text") or el.get("content_desc") or "").strip()


def element_key(el: Dict) -> Tuple:
    """
    Identity key for diffing: label + class + coarse position.
    Deliberately coarse so identical screens produce identical keys
    despite minor coordinate jitter between successive dumps.
    """
    bounds = el.get("bounds", [0, 0, 0, 0])
    if isinstance(bounds, list) and len(bounds) == 4:
        cx = (bounds[0] + bounds[2]) // 2 // _POS_BUCKET
        cy = (bounds[1] + bounds[3]) // 2 // _POS_BUCKET
    elif isinstance(bounds, dict):
        cx = int(bounds.get("x", 0)) // _POS_BUCKET
        cy = int(bounds.get("y", 0)) // _POS_BUCKET
    else:
        cx, cy = 0, 0

    return (element_label(el)[:30], el.get("class", ""), cx, cy)


def diff_elements(
    prev: Optional[List[Dict]],
    curr: Optional[List[Dict]],
) -> str:
    """
    Return a compact text diff of which elements appeared / disappeared.

    Returns:
        "" if there's no previous state (first action)
        "A11y diff: no change." if states are equivalent
        Multi-line diff string showing added/removed elements
    """
    if not prev:
        return ""

    curr = curr or []
    prev_keys = {element_key(e) for e in prev}
    curr_keys = {element_key(e) for e in curr}

    added = [e for e in curr if element_key(e) not in prev_keys]
    removed = [e for e in prev if element_key(e) not in curr_keys]

    if not added and not removed:
        return "A11y diff: no change."

    parts = ["A11y diff (since last action):"]

    for e in added[:_MAX_LISTED]:
        cls = e.get("class", "")
        label = element_label(e)
        parts.append(f"  + '{label}' ({cls})")
    if len(added) > _MAX_LISTED:
        parts.append(f"  + ...{len(added) - _MAX_LISTED} more new elements")

    for e in removed[:_MAX_LISTED]:
        cls = e.get("class", "")
        label = element_label(e)
        parts.append(f"  - '{label}' ({cls})")
    if len(removed) > _MAX_LISTED:
        parts.append(f"  - ...{len(removed) - _MAX_LISTED} more elements gone")

    return "\n".join(parts)
