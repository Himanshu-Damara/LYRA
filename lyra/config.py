"""
Centralized configuration for the LYRA Agent project.
All paths, model hyperparameters, and runtime settings live here.
"""

import os
from pathlib import Path

# ── Project root ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── Data paths ────────────────────────────────────────────────
DATA_DIR = PROJECT_ROOT / "data"
RAW_SCREENSHOTS_DIR = DATA_DIR / "raw_screenshots"
ANNOTATIONS_DIR = DATA_DIR / "annotations"
PROCESSED_DIR = DATA_DIR / "processed"
TRAIN_DIR = PROCESSED_DIR / "train"
VAL_DIR = PROCESSED_DIR / "val"
TEST_DIR = PROCESSED_DIR / "test"
FAILURES_DIR = DATA_DIR / "failures"

# ── Model paths ───────────────────────────────────────────────
CHECKPOINTS_DIR = PROJECT_ROOT / "checkpoints"
LOGS_DIR = PROJECT_ROOT / "logs"
RESULTS_DIR = PROJECT_ROOT / "results"

# ── Phone & ADB settings ──────────────────────────────────────
ADB_PATH = PROJECT_ROOT / "tools" / "platform-tools" / "adb.exe"
# Resolution is detected dynamically from the connected device.
# Do NOT hardcode resolution values here.
PHONE_RESOLUTION = None  # Set at runtime by adb_controller

# ── Model Vocabulary (Finalized Task 8) ───────────────────────
UI_ELEMENT_CLASSES = [
    "app_icon_instagram",   # Instagram launcher / home screen icon
    "app_icon_camera",      # Camera app launcher icon
    "app_icon_clock",       # Clock app launcher icon
    "story_thumbnail",      # Story circle at top of Instagram feed
    "post_like_unliked",    # Unliked heart icon on Instagram post feed
    "post_like_liked",      # Liked (red) heart icon on Instagram post feed
    "story_like_unliked",   # Unliked heart icon on Instagram story
    "story_like_liked",     # Liked heart icon on Instagram story
    "close_button",         # Close / X button
    "shutter_button",       # Camera capture / shutter button
    "add_alarm_button",     # Plus (+) / add alarm button in Clock app
    "save_button",          # Save / confirm button
    "back_button",          # UI back navigation button
]

SCREEN_STATE_CLASSES = [
    "HOME_SCREEN",          # Launcher / Home screen
    "INSTAGRAM_HOME",       # Instagram main feed
    "INSTAGRAM_STORY",      # Viewing Instagram story
    "CAMERA_VIEWFINDER",    # Camera app active viewfinder
    "CLOCK_MAIN",           # Clock app main alarms list
    "ALARM_CREATE",         # Add / edit alarm screen
    "UNKNOWN",              # Other / unrecognized screen state
]

# ── Model architecture (set during Task 20-22) ───────────────
# Will be populated when we build the model.

# ── Training hyperparameters (set during Task 27) ─────────────
# Will be populated when we build the training loop.

# ── Ensure data directories exist ─────────────────────────────
for d in [RAW_SCREENSHOTS_DIR, ANNOTATIONS_DIR, PROCESSED_DIR,
          TRAIN_DIR, VAL_DIR, TEST_DIR, FAILURES_DIR,
          CHECKPOINTS_DIR, LOGS_DIR, RESULTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)
