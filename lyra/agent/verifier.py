"""
verifier.py — Post-action verification using model output.

After performing an action, the verifier takes a new screenshot and checks whether
the expected outcome was achieved (e.g., screen state changed, target element appeared/disappeared).
"""

import time
from typing import Optional
from lyra.inference.coordinator import ActionCoordinator


class ActionVerifier:
    """
    Verifies that an action had the expected effect by comparing
    pre-action and post-action model perceptions.
    """

    def __init__(self, coordinator: ActionCoordinator, settle_time: float = 1.0):
        self.coordinator = coordinator
        self.settle_time = settle_time

    def verify_screen_state(self, expected_state: str, max_retries: int = 3) -> bool:
        """
        Checks if the current screen state matches the expected state.
        Retries with a settle delay between attempts.
        """
        for attempt in range(max_retries):
            time.sleep(self.settle_time)
            perception = self.coordinator.perceive()
            current_state = perception["screen_state"]

            if current_state == expected_state:
                return True

        return False

    def verify_element_present(self, label: str, max_retries: int = 3) -> bool:
        """
        Checks if a specific UI element is visible on screen.
        """
        for attempt in range(max_retries):
            time.sleep(self.settle_time)
            perception = self.coordinator.perceive()
            det = self.coordinator.find_element(label, perception)
            if det is not None:
                return True

        return False

    def verify_element_absent(self, label: str, max_retries: int = 2) -> bool:
        """
        Checks if a specific UI element has disappeared (e.g., after closing a dialog).
        """
        for attempt in range(max_retries):
            time.sleep(self.settle_time)
            perception = self.coordinator.perceive()
            det = self.coordinator.find_element(label, perception)
            if det is None:
                return True

        return False

    def verify_action(self, action_name: str, expected_state: Optional[str] = None,
                      expected_element: Optional[str] = None,
                      absent_element: Optional[str] = None) -> dict:
        """
        Combined verification after an action. Returns a result dict.
        """
        result = {
            "action": action_name,
            "success": True,
            "checks": [],
        }

        if expected_state:
            ok = self.verify_screen_state(expected_state)
            result["checks"].append({
                "type": "screen_state",
                "expected": expected_state,
                "passed": ok,
            })
            if not ok:
                result["success"] = False

        if expected_element:
            ok = self.verify_element_present(expected_element)
            result["checks"].append({
                "type": "element_present",
                "expected": expected_element,
                "passed": ok,
            })
            if not ok:
                result["success"] = False

        if absent_element:
            ok = self.verify_element_absent(absent_element)
            result["checks"].append({
                "type": "element_absent",
                "expected": absent_element,
                "passed": ok,
            })
            if not ok:
                result["success"] = False

        return result
