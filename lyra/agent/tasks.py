"""
tasks.py — Task definitions as composable sequences of primitives.

Each task is a list of Primitive steps that the agent loop executes in order.
"""

from typing import List
from lyra.agent.primitives import (
    Primitive, TapElement, PressHome, PressBack, SwipeScreen,
    TypeText, WaitForScreen, WaitForElement, VerifyAction, TapCoordinates,
)


class TaskDefinition:
    """A named sequence of primitives that accomplish a phone automation goal."""

    def __init__(self, name: str, description: str, steps: List[Primitive]):
        self.name = name
        self.description = description
        self.steps = steps


# ── Pre-defined Task Library ─────────────────────────────────────

def task_open_instagram() -> TaskDefinition:
    """Open Instagram from the home screen."""
    return TaskDefinition(
        name="open_instagram",
        description="Navigate to the home screen and open Instagram",
        steps=[
            PressHome(settle=0.5),
            TapElement("app_icon_instagram", settle=2.0),
        ]
    )


def task_open_camera() -> TaskDefinition:
    """Open the Camera app from the home screen."""
    return TaskDefinition(
        name="open_camera",
        description="Navigate to the home screen and open Camera",
        steps=[
            PressHome(settle=0.5),
            TapElement("app_icon_camera", settle=2.0),
        ]
    )


def task_take_photo() -> TaskDefinition:
    """Open camera and take a photo."""
    return TaskDefinition(
        name="take_photo",
        description="Open camera and capture a photo using the shutter button",
        steps=[
            PressHome(settle=1.0),
            TapElement("app_icon_camera", settle=2.0),
            WaitForScreen("CAMERA_VIEWFINDER", timeout=10.0),
            TapElement("shutter_button", settle=2.0),
            VerifyAction(expected_state="CAMERA_VIEWFINDER"),
        ]
    )


def task_like_instagram_post() -> TaskDefinition:
    """Like the first unliked post visible on the Instagram feed."""
    return TaskDefinition(
        name="like_post",
        description="Open Instagram and like the first unliked post on the feed",
        steps=[
            PressHome(settle=1.0),
            TapElement("app_icon_instagram", settle=2.0),
            WaitForScreen("INSTAGRAM_HOME", timeout=10.0),
            TapElement("post_like_unliked", settle=1.0),
            VerifyAction(expected_element="post_like_liked"),
        ]
    )


def task_view_instagram_story() -> TaskDefinition:
    """Open the first Instagram story."""
    return TaskDefinition(
        name="view_story",
        description="Open Instagram and tap on the first story thumbnail",
        steps=[
            PressHome(settle=1.0),
            TapElement("app_icon_instagram", settle=2.0),
            WaitForScreen("INSTAGRAM_HOME", timeout=10.0),
            TapElement("story_thumbnail", settle=2.0),
            WaitForScreen("INSTAGRAM_STORY", timeout=10.0),
            VerifyAction(expected_state="INSTAGRAM_STORY"),
        ]
    )


def task_go_home() -> TaskDefinition:
    """Return to the home screen."""
    return TaskDefinition(
        name="go_home",
        description="Press home and verify we are on the home screen",
        steps=[
            PressHome(settle=1.0),
            VerifyAction(expected_state="HOME_SCREEN"),
        ]
    )


# ── Task Registry ────────────────────────────────────────────────

TASK_REGISTRY = {
    "open_instagram": task_open_instagram,
    "open_camera": task_open_camera,
    "take_photo": task_take_photo,
    "like_post": task_like_instagram_post,
    "view_story": task_view_instagram_story,
    "go_home": task_go_home,
}


def get_task(name: str) -> TaskDefinition:
    """Look up a task by name from the registry."""
    factory = TASK_REGISTRY.get(name)
    if factory is None:
        raise ValueError(f"Unknown task: '{name}'. Available: {list(TASK_REGISTRY.keys())}")
    return factory()


def list_tasks() -> List[str]:
    """Return the names of all available tasks."""
    return list(TASK_REGISTRY.keys())
