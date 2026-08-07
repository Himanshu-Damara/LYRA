"""
collect_screenshots.py — Utility to rapidly collect REAL screenshots from connected phone.

Features:
- Auto-generates unique timestamped filenames (no overwriting)
- Saves raw screenshots in `data/raw_screenshots/`
- Writes a matching `.json` metadata file for each screenshot (timestamp, resolution, device, screen tag)
- Interactive modes:
    1. Interval mode: Automatically captures every N seconds as you navigate
    2. Manual mode: Captures a screenshot every time you press Enter
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
import cv2

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lyra.config import RAW_SCREENSHOTS_DIR, SCREEN_STATE_CLASSES
from lyra.phone.screenshot import capture_screenshot, get_screen_resolution


def save_screenshot_with_metadata(screen_tag: str = "UNKNOWN") -> Path:
    """
    Captures a real screenshot and saves PNG + JSON metadata in RAW_SCREENSHOTS_DIR.
    """
    now = datetime.now()
    timestamp_str = now.strftime("%Y%m%d_%H%M%S_%f")[:19]
    filename = f"raw_{timestamp_str}.png"
    img_path = RAW_SCREENSHOTS_DIR / filename
    meta_path = RAW_SCREENSHOTS_DIR / f"raw_{timestamp_str}.json"

    # Capture screen via ADB
    img, width, height, _ = capture_screenshot(output_path=img_path)

    # Save metadata JSON
    metadata = {
        "filename": filename,
        "timestamp": now.isoformat(),
        "resolution": {"width": width, "height": height},
        "screen_state_tag": screen_tag if screen_tag in SCREEN_STATE_CLASSES else "UNKNOWN"
    }

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    return img_path


def run_manual_collector():
    print("==================================================")
    print("   LYRA SCREENSHOT COLLECTOR (MANUAL ENTER MODE)  ")
    print("==================================================")
    print(f"Saving screenshots to: {RAW_SCREENSHOTS_DIR}")
    print("Press ENTER to capture a screenshot.")
    print("Type 'q' and press ENTER to stop collecting.\n")

    count = 0
    w, h = get_screen_resolution()
    print(f"Connected Phone Resolution: {w}x{h}\n")

    while True:
        user_in = input("Press ENTER to capture (or 'q' to quit): ").strip()
        if user_in.lower() == 'q':
            break

        path = save_screenshot_with_metadata()
        count += 1
        print(f"  [{count}] Saved: {path.name}")

    print(f"\n[DONE] Collected {count} raw screenshots!")


def run_interval_collector(interval_sec: float = 2.0, max_count: int = 50):
    print("==================================================")
    print(f" LYRA SCREENSHOT COLLECTOR (INTERVAL {interval_sec}s MODE) ")
    print("==================================================")
    print(f"Saving to: {RAW_SCREENSHOTS_DIR}")
    print(f"Capturing 1 screenshot every {interval_sec} seconds (Max: {max_count}).")
    print("Starting in 3 seconds... Navigate your phone now!\n")
    time.sleep(3)

    count = 0
    try:
        while count < max_count:
            start_time = time.time()
            path = save_screenshot_with_metadata()
            count += 1
            print(f"  [{count}/{max_count}] Captured: {path.name}")
            
            elapsed = time.time() - start_time
            sleep_time = max(0.1, interval_sec - elapsed)
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\n[STOPPED] Collection stopped by user.")

    print(f"\n[DONE] Collected {count} raw screenshots!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LYRA Raw Screenshot Collector Utility")
    parser.add_argument("--mode", choices=["manual", "interval"], default="manual", help="Collection mode")
    parser.add_argument("--interval", type=float, default=2.0, help="Interval in seconds for interval mode")
    parser.add_argument("--max", type=int, default=50, help="Max screenshots for interval mode")
    args = parser.parse_args()

    if args.mode == "manual":
        run_manual_collector()
    else:
        run_interval_collector(interval_sec=args.interval, max_count=args.max)
