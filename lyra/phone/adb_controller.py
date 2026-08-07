"""
adb_controller.py — Real low-level phone control functions via ADB commands.

Implements:
- tap(x, y)
- swipe(x1, y1, x2, y2, duration)
- back()
- home()
- type_text(text)

Automatically queries and caches real device resolution dynamically.
"""

import subprocess
import time
from typing import Tuple, Optional
from lyra.config import ADB_PATH
from lyra.phone.screenshot import get_screen_resolution


class ADBController:
    def __init__(self):
        self.adb_path = str(ADB_PATH)
        self._resolution: Optional[Tuple[int, int]] = None

    @property
    def resolution(self) -> Tuple[int, int]:
        """Dynamically retrieves and caches the physical screen (width, height)."""
        if self._resolution is None:
            self._resolution = get_screen_resolution()
        return self._resolution

    def _run_adb_shell(self, *args: str) -> str:
        """Executes an `adb shell` command."""
        cmd = [self.adb_path, "shell"] + list(args)
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return res.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"ADB shell command failed ({cmd}): {e.stderr.strip()}") from e

    def tap(self, x: int, y: int) -> None:
        """
        Emulates a single touch tap at screen coordinate (x, y).

        Args:
            x (int): Horizontal pixel coordinate (0 <= x < width)
            y (int): Vertical pixel coordinate (0 <= y < height)
        """
        w, h = self.resolution
        # Clamp coordinates within bounds
        x_clamped = max(0, min(int(x), w - 1))
        y_clamped = max(0, min(int(y), h - 1))

        self._run_adb_shell("input", "tap", str(x_clamped), str(y_clamped))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        """
        Emulates a swipe gesture from (x1, y1) to (x2, y2).

        Args:
            x1, y1: Start coordinates
            x2, y2: End coordinates
            duration_ms: Gesture duration in milliseconds (default: 300ms)
        """
        w, h = self.resolution
        x1_c = max(0, min(int(x1), w - 1))
        y1_c = max(0, min(int(y1), h - 1))
        x2_c = max(0, min(int(x2), w - 1))
        y2_c = max(0, min(int(y2), h - 1))

        self._run_adb_shell(
            "input", "swipe",
            str(x1_c), str(y1_c),
            str(x2_c), str(y2_c),
            str(int(duration_ms))
        )

    def back(self) -> None:
        """Triggers the Android Back key event (KEYCODE_BACK / 4)."""
        self._run_adb_shell("input", "keyevent", "4")

    def home(self) -> None:
        """Triggers the Android Home key event (KEYCODE_HOME / 3)."""
        self._run_adb_shell("input", "keyevent", "3")

    def type_text(self, text: str) -> None:
        """
        Types string text into the currently focused text input field.
        Escapes spaces as `%s` for ADB input command format.
        """
        if not text:
            return
        # ADB text input expects spaces replaced with %s
        escaped_text = text.replace(" ", "%s").replace("&", "\\&").replace("<", "\\<").replace(">", "\\>")
        self._run_adb_shell("input", "text", escaped_text)


# Default controller singleton instance
controller = ADBController()

if __name__ == "__main__":
    print("ADB Controller initialized.")
    w, h = controller.resolution
    print(f"Detected dynamic device resolution: {w}x{h}")
