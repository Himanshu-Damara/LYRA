"""
primitives.py — Reusable action building blocks for phone automation.

Original primitives: FIND, TAP, TAP_XY, SWIPE, TYPE, BACK, HOME, WAIT_SCREEN, WAIT_ELEMENT, VERIFY.
New primitives:      LAUNCH_APP, FIND_BY_TEXT, TAP_BY_TEXT, SCROLL_TO_FIND, WAIT_FOR_TEXT.

Each primitive is a callable that takes an ActionCoordinator and returns
a result dict describing whether the action succeeded.
"""

import time
from typing import Optional, Dict, Any
from lyra.inference.coordinator import ActionCoordinator
from lyra.agent.verifier import ActionVerifier
from lyra.agent.app_resolver import resolve_package


class Primitive:
    """Base class for all action primitives."""
    name: str = "UNKNOWN"

    def execute(self, coordinator: ActionCoordinator) -> Dict[str, Any]:
        raise NotImplementedError


class FindElement(Primitive):
    """Perceive the screen and find a specific UI element."""
    name = "FIND"

    def __init__(self, label: str, timeout: float = 5.0):
        self.label = label
        self.timeout = timeout

    def execute(self, coordinator: ActionCoordinator) -> Dict[str, Any]:
        det = coordinator.wait_for_element(self.label, timeout=self.timeout)
        return {
            "action": self.name,
            "target": self.label,
            "success": det is not None,
            "detection": det,
        }


class TapElement(Primitive):
    """Find and tap a specific UI element."""
    name = "TAP"

    def __init__(self, label: str, index: int = 0, settle: float = 1.0):
        self.label = label
        self.index = index
        self.settle = settle

    def execute(self, coordinator: ActionCoordinator) -> Dict[str, Any]:
        success = coordinator.tap_element(self.label, index=self.index)
        if success:
            time.sleep(self.settle)
        return {
            "action": self.name,
            "target": self.label,
            "success": success,
        }


class TapCoordinates(Primitive):
    """Tap at specific screen coordinates."""
    name = "TAP_XY"

    def __init__(self, x: int, y: int, settle: float = 0.5):
        self.x = x
        self.y = y
        self.settle = settle

    def execute(self, coordinator: ActionCoordinator) -> Dict[str, Any]:
        coordinator.tap_coordinates(self.x, self.y)
        time.sleep(self.settle)
        return {"action": self.name, "target": f"({self.x},{self.y})", "success": True}


class SwipeScreen(Primitive):
    """Swipe in a direction."""
    name = "SWIPE"

    def __init__(self, direction: str = "up", distance: float = 0.4, settle: float = 0.5):
        self.direction = direction
        self.distance = distance
        self.settle = settle

    def execute(self, coordinator: ActionCoordinator) -> Dict[str, Any]:
        coordinator.swipe_screen(self.direction, self.distance)
        time.sleep(self.settle)
        return {"action": self.name, "target": self.direction, "success": True}


class TypeText(Primitive):
    """Type text into the currently focused input."""
    name = "TYPE"

    def __init__(self, text: str, settle: float = 0.5):
        self.text = text
        self.settle = settle

    def execute(self, coordinator: ActionCoordinator) -> Dict[str, Any]:
        coordinator.type_text(self.text)
        time.sleep(self.settle)
        return {"action": self.name, "target": self.text, "success": True}


class PressBack(Primitive):
    """Press the Android back button."""
    name = "BACK"

    def __init__(self, settle: float = 0.5):
        self.settle = settle

    def execute(self, coordinator: ActionCoordinator) -> Dict[str, Any]:
        coordinator.go_back()
        time.sleep(self.settle)
        return {"action": self.name, "target": "back_key", "success": True}


class PressHome(Primitive):
    """Press the Android home button."""
    name = "HOME"

    def __init__(self, settle: float = 0.5):
        self.settle = settle

    def execute(self, coordinator: ActionCoordinator) -> Dict[str, Any]:
        coordinator.go_home()
        time.sleep(self.settle)
        return {"action": self.name, "target": "home_key", "success": True}


class WaitForScreen(Primitive):
    """Wait until a specific screen state is reached."""
    name = "WAIT_SCREEN"

    def __init__(self, target_state: str, timeout: float = 10.0):
        self.target_state = target_state
        self.timeout = timeout

    def execute(self, coordinator: ActionCoordinator) -> Dict[str, Any]:
        ok = coordinator.wait_for_screen(self.target_state, timeout=self.timeout)
        return {
            "action": self.name,
            "target": self.target_state,
            "success": ok,
        }


class WaitForElement(Primitive):
    """Wait until a specific UI element appears."""
    name = "WAIT_ELEMENT"

    def __init__(self, label: str, timeout: float = 10.0):
        self.label = label
        self.timeout = timeout

    def execute(self, coordinator: ActionCoordinator) -> Dict[str, Any]:
        det = coordinator.wait_for_element(self.label, timeout=self.timeout)
        return {
            "action": self.name,
            "target": self.label,
            "success": det is not None,
            "detection": det,
        }


class VerifyAction(Primitive):
    """Verify post-action state."""
    name = "VERIFY"

    def __init__(self, expected_state: Optional[str] = None,
                 expected_element: Optional[str] = None,
                 absent_element: Optional[str] = None):
        self.expected_state = expected_state
        self.expected_element = expected_element
        self.absent_element = absent_element

    def execute(self, coordinator: ActionCoordinator) -> Dict[str, Any]:
        verifier = ActionVerifier(coordinator)
        result = verifier.verify_action(
            self.name,
            expected_state=self.expected_state,
            expected_element=self.expected_element,
            absent_element=self.absent_element,
        )
        return result


class LaunchApp(Primitive):
    """Launch an Android app by its natural name or package name."""
    name = "LAUNCH_APP"

    def __init__(self, app_name: str, settle: float = 2.0):
        self.app_name = app_name
        self.settle = settle
        self.label = app_name  # For logging

    def execute(self, coordinator: ActionCoordinator) -> Dict[str, Any]:
        package = resolve_package(self.app_name)
        if not package:
            return {
                "action": self.name,
                "target": self.app_name,
                "success": False,
                "error": f"Unknown app: '{self.app_name}'. Could not resolve package name.",
            }
        success = coordinator.launch_app(package)
        if success:
            time.sleep(self.settle)
        return {
            "action": self.name,
            "target": self.app_name,
            "package": package,
            "success": success,
        }


class FindByText(Primitive):
    """Find a UI element by its visible text using the accessibility tree."""
    name = "FIND_BY_TEXT"

    def __init__(self, text: str, timeout: float = 5.0):
        self.text = text
        self.label = text
        self.timeout = timeout

    def execute(self, coordinator: ActionCoordinator) -> Dict[str, Any]:
        start = time.time()
        while time.time() - start < self.timeout:
            perception = coordinator.perceive()
            elem = coordinator.find_element_by_text(self.text, perception)
            if elem is not None:
                return {
                    "action": self.name,
                    "target": self.text,
                    "success": True,
                    "element": elem,
                }
            time.sleep(0.5)
        return {
            "action": self.name,
            "target": self.text,
            "success": False,
            "error": f"Text '{self.text}' not found on screen.",
        }


class TapByText(Primitive):
    """Find and tap a UI element by its visible text using the accessibility tree."""
    name = "TAP_BY_TEXT"

    def __init__(self, text: str, settle: float = 1.0):
        self.text = text
        self.label = text
        self.settle = settle

    def execute(self, coordinator: ActionCoordinator) -> Dict[str, Any]:
        success = coordinator.tap_element_by_text(self.text)
        if success:
            time.sleep(self.settle)
        return {
            "action": self.name,
            "target": self.text,
            "success": success,
            "error": None if success else f"Text '{self.text}' not found or not tappable.",
        }


class ScrollToFind(Primitive):
    """Scroll down the screen repeatedly until text is found or max attempts reached."""
    name = "SCROLL_TO_FIND"

    def __init__(self, text: str, max_scrolls: int = 5, direction: str = "up",
                 settle: float = 1.0):
        self.text = text
        self.label = text
        self.max_scrolls = max_scrolls
        self.direction = direction
        self.settle = settle

    def execute(self, coordinator: ActionCoordinator) -> Dict[str, Any]:
        for attempt in range(self.max_scrolls):
            perception = coordinator.perceive()
            elem = coordinator.find_element_by_text(self.text, perception)
            if elem is not None:
                return {
                    "action": self.name,
                    "target": self.text,
                    "success": True,
                    "element": elem,
                    "scrolls_needed": attempt,
                }
            coordinator.swipe_screen(self.direction, distance=0.4)
            time.sleep(self.settle)

        return {
            "action": self.name,
            "target": self.text,
            "success": False,
            "error": f"Text '{self.text}' not found after {self.max_scrolls} scrolls.",
        }


class WaitForText(Primitive):
    """Wait until specific text appears on screen."""
    name = "WAIT_FOR_TEXT"

    def __init__(self, text: str, timeout: float = 10.0):
        self.text = text
        self.label = text
        self.timeout = timeout

    def execute(self, coordinator: ActionCoordinator) -> Dict[str, Any]:
        start = time.time()
        while time.time() - start < self.timeout:
            perception = coordinator.perceive()
            elem = coordinator.find_element_by_text(self.text, perception)
            if elem is not None:
                return {
                    "action": self.name,
                    "target": self.text,
                    "success": True,
                }
            time.sleep(1.0)
        return {
            "action": self.name,
            "target": self.text,
            "success": False,
            "error": f"Text '{self.text}' did not appear within {self.timeout}s.",
        }
