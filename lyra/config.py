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

# ── Model Vocabulary (Task 8 & Extended for DM / Gmail) ────────
UI_ELEMENT_CLASSES = [
    # App Launcher Icons
    "app_icon_instagram",   # Instagram launcher / home screen icon
    "app_icon_camera",      # Camera app launcher icon
    "app_icon_clock",       # Clock app launcher icon
    "app_icon_gmail",       # Gmail app launcher icon

    # Instagram Feed & Story
    "story_thumbnail",      # Story circle at top of Instagram feed
    "post_like_unliked",    # Unliked heart icon on Instagram post feed
    "post_like_liked",      # Liked (red) heart icon on Instagram post feed
    "story_like_unliked",   # Unliked heart icon on Instagram story
    "story_like_liked",     # Liked heart icon on Instagram story

    # Instagram DM
    "dm_icon",              # DM / Messenger icon on Instagram top bar
    "dm_search_bar",        # Search bar in Instagram DM list
    "chat_input_field",     # Text input area at bottom of Instagram chat
    "send_message_button",  # Send button inside Instagram chat

    # Gmail
    "compose_email_button", # Compose button in Gmail main screen
    "send_email_button",    # Send paper airplane icon in Gmail compose
    "email_to_field",       # "To" recipient field in Gmail compose
    "email_subject_field",  # "Subject" field in Gmail compose
    "email_body_field",     # Message body input in Gmail compose

    # General Controls
    "shutter_button",       # Camera capture / shutter button
    "add_alarm_button",     # Plus (+) / add alarm button in Clock app
    "save_button",          # Save / confirm button
    "close_button",         # Close / X button
    "back_button",          # UI back navigation button
]

SCREEN_STATE_CLASSES = [
    "HOME_SCREEN",          # Launcher / Home screen
    "INSTAGRAM_HOME",       # Instagram main feed
    "INSTAGRAM_STORY",      # Viewing Instagram story
    "INSTAGRAM_DM_LIST",    # Instagram Direct Messages inbox list
    "INSTAGRAM_CHAT",       # Open Instagram chat thread
    "CAMERA_VIEWFINDER",    # Camera app active viewfinder
    "CLOCK_MAIN",           # Clock app main alarms list
    "ALARM_CREATE",         # Add / edit alarm screen
    "GMAIL_MAIN",           # Gmail inbox / main list screen
    "GMAIL_COMPOSE",        # Gmail email creation / compose screen
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
