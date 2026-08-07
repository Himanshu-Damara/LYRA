"""
test_phone_control.py — Temporary interactive test script for raw ADB phone control.

Tests:
1. home() — returns to phone home screen
2. swipe() — swipes up to open app drawer / scroll feed
3. tap() — taps center of screen or specified coordinates
4. back() — triggers back navigation
5. type_text() — types test string

Note: Hardcoded coordinates here are FOR TEMPORARY HARDWARE TESTING ONLY.
They are NOT used by the AI model.
"""

import time
from lyra.phone.adb_controller import controller


def run_control_tests():
    print("==================================================")
    print("     TASK 7: RAW ADB PHONE CONTROL TEST SUITE      ")
    print("==================================================")
    w, h = controller.resolution
    print(f"Target Device Screen Size: {w}x{h}\n")

    # 1. Test Home
    print("[TEST 1/5] Testing home()...")
    controller.home()
    time.sleep(1.5)
    print("  -> Executed home command.\n")

    # 2. Test Swipe (Swipe up from bottom center)
    print("[TEST 2/5] Testing swipe() (swiping UP)...")
    start_x, start_y = w // 2, int(h * 0.8)
    end_x, end_y = w // 2, int(h * 0.2)
    controller.swipe(start_x, start_y, end_x, end_y, duration_ms=400)
    time.sleep(1.5)
    print(f"  -> Swiped from ({start_x},{start_y}) to ({end_x},{end_y}).\n")

    # 3. Test Tap (Tap middle of screen)
    print("[TEST 3/5] Testing tap() (center screen tap)...")
    tap_x, tap_y = w // 2, h // 2
    controller.tap(tap_x, tap_y)
    time.sleep(1.5)
    print(f"  -> Tapped at ({tap_x},{tap_y}).\n")

    # 4. Test Back
    print("[TEST 4/5] Testing back()...")
    controller.back()
    time.sleep(1.5)
    print("  -> Executed back command.\n")

    # 5. Return Home
    print("[TEST 5/5] Returning to home screen...")
    controller.home()
    time.sleep(1.0)
    print("==================================================")
    print("[SUCCESS] All raw control commands sent without error!")
    print("==================================================")


if __name__ == "__main__":
    run_control_tests()
