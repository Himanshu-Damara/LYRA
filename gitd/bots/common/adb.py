#!/usr/bin/env python3
"""
adb_core.py Ã¢â‚¬â€ Shared ADB + XML primitives for Android automation.

Single Device class providing tap, swipe, type, screenshot, XML dump,
and other low-level ADB operations used by skills and bot scripts.
"""

import hashlib
import html
import json
import re
import shlex
import subprocess
import time
import unicodedata
from typing import NamedTuple


def ascii_typeable(text: str) -> str:
    """Transliterate text to the closest ASCII `adb shell input text` can send.

    `adb shell input text` is ASCII-only: a single non-ASCII char (e.g. the ÃƒÂ© in
    "SautÃƒÂ©") makes the WHOLE command fail and leaves the field blank. NFKD-decompose
    then drop combining marks so accented letters land as their base letter
    ("SautÃƒÂ©" -> "Saute", "cafÃƒÂ©" -> "cafe"), which fuzzy-matches the intended value
    and is the best the device can physically type. For full-fidelity emoji/CJK the
    caller should use `type_unicode` (ADBKeyboard) instead Ã¢â‚¬â€ this is the graceful
    degradation for the plain `input text` path only.
    """
    if text.isascii():
        return text
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def strip_to_png_signature(raw: bytes) -> bytes:
    """On multi-display devices (foldables), screencap prints a
    "[Warning] Multiple displays were found..." line to stdout ahead of the
    PNG data, corrupting naive reads. Trim anything before the PNG signature.
    """
    idx = raw.find(_PNG_SIGNATURE)
    return raw[idx:] if idx > 0 else raw


def capture_screencap_png(serial: str, timeout: float = 10) -> bytes:
    raw = subprocess.check_output(["adb", "-s", serial, "exec-out", "screencap", "-p"], timeout=timeout)
    return strip_to_png_signature(raw)


_KEYCODE_RE = re.compile(r"^KEYCODE_[A-Z0-9_]+$")


def normalize_keycode(key: str) -> str:
    """Return a validated Android keycode, adding the ``KEYCODE_`` prefix if absent.

    ``adb shell input keyevent <key>`` re-parses its argument through the *device*
    shell, so an agent/attacker-controlled value like ``KEYCODE_HOME; reboot`` would
    otherwise run ``reboot`` on the device. Keycodes are always bare
    ``KEYCODE_[A-Z0-9_]+`` names, so anything else is rejected outright.
    """
    if not key.startswith("KEYCODE_"):
        key = "KEYCODE_" + key
    if not _KEYCODE_RE.match(key):
        raise ValueError(f"invalid keycode {key!r}: expected KEYCODE_[A-Z0-9_]+")
    return key


def input_text_arg(text: str) -> str:
    """Shell-quote text for ``adb shell input text`` so it types literally.

    ``adb shell`` re-parses its argv through the device shell, so metacharacters
    (``; & | $ ` ( ) < > \\n`` Ã¢â‚¬â€ including ones NFKD transliteration folds in from
    fullwidth punctuation) would break out of the ``input text`` call and run on
    the device. Quoting the whole argument neutralizes that; spaces stay encoded
    as ``%s`` (input's own space escape) inside the quotes. Pass already-ASCII
    (``ascii_typeable``) text; the caller keeps the transliterated string for its
    own reporting.
    """
    return shlex.quote(text.replace(" ", "%s"))


class ADBError(RuntimeError):
    """Raised when an adb invocation fails (nonzero exit, timeout, or adb missing).

    Subclasses RuntimeError so the many call sites that already wrap adb calls in
    ``try/except Exception`` keep degrading gracefully Ã¢â‚¬â€ the only behaviour change
    is that a failure now carries a real message instead of masquerading as an
    empty-string success.
    """

    def __init__(self, args, returncode: int, stderr: str = "", stdout: str = ""):
        self.cmd_args = tuple(args)
        self.returncode = returncode
        self.stderr = stderr or ""
        self.stdout = stdout or ""
        detail = self.stderr.strip() or self.stdout.strip() or "no output"
        cmd = "adb " + " ".join(str(a) for a in args)
        super().__init__(f"{cmd} failed (exit {returncode}): {detail}")


class ADBResult(NamedTuple):
    """Result of a soft (non-raising) adb call Ã¢â‚¬â€ see ``Device.adb_soft``."""

    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def _stable_port(serial: str, base: int = 18000) -> int:
    """Deterministic port from serial (stable across Python processes)."""
    return base + int(hashlib.md5(serial.encode()).hexdigest()[:3], 16) % 1000


TIKTOK_PKG = "com.zhiliaoapp.musically"
TIKTOK_MAIN_ACTIVITY = f"{TIKTOK_PKG}/com.ss.android.ugc.aweme.main.MainActivity"
TIKTOK_SPLASH = f"{TIKTOK_PKG}/com.ss.android.ugc.aweme.splash.SplashActivity"

# Shared resource IDs Ã¢â‚¬â€ verified TikTok v44.3.3, 2026-03-21
KNOWN_TIKTOK_VERSION = "44.3.3"
RID_PROFILE_TAB = f"{TIKTOK_PKG}:id/n19"  # bottom nav Profile icon (was myp)
RID_SEARCH_ICON = f"{TIKTOK_PKG}:id/j4d"  # magnifying glass on home (was j29)
RID_SEARCH_BOX = f"{TIKTOK_PKG}:id/gti"  # search text input field (was gry)
RID_SUGGESTION = f"{TIKTOK_PKG}:id/zg6"  # suggestion row in search (was z_i)
RID_USERNAME_ROW = f"{TIKTOK_PKG}:id/zef"  # username in Users tab (was z8q)
RID_FILTER_CHIP = f"{TIKTOK_PKG}:id/ecp"  # filter chips Ã¢â‚¬â€ TODO verify after update

# Known popups to dismiss (specific patterns checked first)
_KNOWN_POPUPS = [
    {"detect": "Continue editing", "button": "Save draft", "label": "Draft resume overlay"},
    {"detect": "connect with people", "button": "Don\u2019t allow", "label": "Contacts access popup"},
    {"detect": "access to your Facebook", "button": "Don't allow", "label": "Facebook friends access popup"},
    {"detect": "Make TikTok Shop more relevant", "button": "Select", "label": "TikTok Shop relevance"},
    {"detect": "shared collections", "button": "Not now", "label": "Shared collections popup"},
    {"detect": "Turn on notifications", "button": "Not now", "label": "Turn on notifications popup"},
    {"detect": "security checkup", "button": "Close", "label": "Security checkup popup"},
    {"detect": "Not now", "button": "Not now", "label": "Not now dialog"},
    {"detect": 'content-desc="Close"', "button": "Close", "label": "Close dialog"},
    {"detect": "Skip", "button": "Skip", "label": "Skip dialog"},
]
# Generic dismiss words (fallback if no specific popup matched)
# 'discard' handles the "Discard draft?" dialog that appears when Back is pressed in creation screen
_DISMISS_WORDS = {"not now", "skip", "cancel", "dismiss", "later", "discard"}
_DISMISS_EXACT = {"cancel", "dismiss", "discard", "save draft", "don\u2019t allow", "don't allow"}


class Device:
    """Encapsulates ADB + XML primitives for one connected Android device."""

    def __init__(self, serial: str):
        self.serial = serial

    # Ã¢â€â‚¬Ã¢â€â‚¬ ADB primitives Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

    def _run(self, args, timeout) -> subprocess.CompletedProcess:
        """Invoke adb once. Raises ADBError if adb is missing or the call times
        out Ã¢â‚¬â€ both are hard failures no caller can recover from as a string."""
        try:
            return subprocess.run(
                ["adb", "-s", self.serial, *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except FileNotFoundError as e:
            raise ADBError(args, 127, "adb executable not found on PATH") from e
        except subprocess.TimeoutExpired as e:
            raise ADBError(args, -1, f"timed out after {timeout}s") from e

    def adb(self, *args, timeout=30) -> str:
        """Run an adb command, returning stripped stdout.

        Raises ADBError on a nonzero exit (device offline/unauthorized/unknown
        serial, adb transport errors) instead of silently returning "" Ã¢â‚¬â€ that
        empty string used to read as success and gave every downstream tool a
        phantom success. Note: app-level tools like ``am``/``pm``/``monkey``
        usually still exit 0 on their own failures and print the error to
        stdout, so callers that care about those must still parse stdout; this
        only surfaces adb-process-level failures. For commands where a nonzero
        exit is expected and tolerable, use ``adb_soft``.
        """
        r = self._run(args, timeout)
        if r.returncode != 0:
            raise ADBError(args, r.returncode, r.stderr, r.stdout)
        return r.stdout.strip()

    def adb_soft(self, *args, timeout=30) -> ADBResult:
        """Run an adb command without raising on a nonzero exit.

        Returns an ADBResult(returncode, stdout, stderr) so the caller can
        inspect the exit code / stderr itself. Use for calls where a nonzero
        exit is a normal, expected outcome (e.g. probing an optional feature
        that may be unavailable on older devices). adb-missing / timeout still
        raise ADBError Ã¢â‚¬â€ those are never a normal outcome.
        """
        r = self._run(args, timeout)
        return ADBResult(r.returncode, r.stdout.strip(), r.stderr.strip())

    def adb_show(self, *args):
        """adb with live output (e.g. for push progress)."""
        subprocess.run(["adb", "-s", self.serial, *args])

    def tap(self, x, y, delay=0.6):
        self.adb("shell", "input", "tap", str(int(x)), str(int(y)))
        time.sleep(delay)

    def swipe(self, x1, y1, x2, y2, ms=500, delay=0.5):
        self.adb("shell", "input", "swipe", str(int(x1)), str(int(y1)), str(int(x2)), str(int(y2)), str(ms))
        time.sleep(delay)

    def back(self, delay=1.0):
        self.adb("shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(delay)

    def press_enter(self, delay=0.5):
        self.adb("shell", "input", "keyevent", "KEYCODE_ENTER")
        time.sleep(delay)

    def long_press(self, x, y, duration_ms=1000, delay=0.5):
        """Long press at (x, y) for duration_ms milliseconds."""
        self.adb("shell", "input", "swipe", str(int(x)), str(int(y)), str(int(x)), str(int(y)), str(duration_ms))
        time.sleep(delay)

    def clipboard_get(self) -> str:
        """Get clipboard text (requires API 29+).

        Uses adb_soft Ã¢â‚¬â€ the clipboard service is unavailable on some devices
        and returns nonzero; that's a normal "no clipboard" outcome, not an
        error worth raising through every caller.
        """
        return self.adb_soft("shell", "cmd", "clipboard", "get-text").stdout or ""

    def clipboard_set(self, text: str):
        """Set clipboard text."""
        self.adb("shell", "cmd", "clipboard", "set-text", text)

    # Ã¢â€â‚¬Ã¢â€â‚¬ Multi-touch / pinch Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

    def pinch_in(self, cx, cy, start_dist=300, end_dist=50, duration_ms=500, delay=0.5):
        """Pinch-to-zoom in (two fingers moving inward)."""
        steps = max(10, duration_ms // 20)
        self.adb(
            "shell", "input", "swipe", str(cx - start_dist), str(cy), str(cx - end_dist), str(cy), str(duration_ms)
        )
        time.sleep(delay)

    def pinch_out(self, cx, cy, start_dist=50, end_dist=300, duration_ms=500, delay=0.5):
        """Pinch-to-zoom out (two fingers moving outward)."""
        self.adb(
            "shell", "input", "swipe", str(cx - start_dist), str(cy), str(cx - end_dist), str(cy), str(duration_ms)
        )
        time.sleep(delay)

    # Ã¢â€â‚¬Ã¢â€â‚¬ Unicode text input (ADBKeyboard) Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

    def type_unicode(self, text: str, delay=0.3):
        """Type text including emoji/unicode via ADBKeyboard broadcast.

        Requires ADBKeyboard APK installed on device.
        Flow: enable IME Ã¢â€ â€™ set IME Ã¢â€ â€™ broadcast text Ã¢â€ â€™ restore Gboard.
        """
        adb_ime = "com.android.adbkeyboard/.AdbIME"
        gboard = "com.google.android.inputmethod.latin/com.android.inputmethod.latin.LatinIME"

        # Enable and switch to ADBKeyboard
        self.adb("shell", "ime", "enable", adb_ime)
        self.adb("shell", "ime", "set", adb_ime)
        time.sleep(0.2)

        # Broadcast text (handles emoji, CJK, accented chars)
        escaped = text.replace('"', '\\"')
        self.adb("shell", "am", "broadcast", "-a", "ADB_INPUT_TEXT", "--es", "msg", f'"{escaped}"')
        time.sleep(delay)

        # Restore original IME immediately (stealth: minimize time on ADBKeyboard)
        self.adb("shell", "ime", "set", gboard)
        self.adb("shell", "ime", "disable", adb_ime)

    # Ã¢â€â‚¬Ã¢â€â‚¬ Notifications Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

    def open_notifications(self, delay=0.5):
        """Swipe down from status bar to open notification shade."""
        self.adb("shell", "cmd", "statusbar", "expand-notifications")
        time.sleep(delay)

    def close_notifications(self, delay=0.3):
        """Close notification shade."""
        self.adb("shell", "cmd", "statusbar", "collapse")
        time.sleep(delay)

    def read_notifications(self) -> str:
        """Dump XML of notification shade. Call open_notifications() first."""
        return self.dump_xml()

    def clear_notifications(self, delay=0.5):
        """Open notifications and tap 'Clear all'."""
        self.open_notifications(delay=0.5)
        xml = self.dump_xmlë]4¶‰žËkºwµç@€€€€€€€€€€áµ°€ôÍ•±˜¹‘ÕµÁ}áµ° ¤4(€€€€€€€€€€€ˆ€ôÍ•±˜¹™¥¹‘}‰½Õ¹‘Ì¡áµ°°É•Í½ÕÉ•}¥õ˜‰íQ%-Q=-}A-ôé¥½å™¬ˆ¤4(€€€€€€€€€€€¥˜ˆ½È€‰É…™ÑÌèˆ¥¸áµ°è4(€€€€€€€€€€€€€€€‰É•…¬4(€€€€€€€€€€€¥˜…¹ä¡¥¹¥¸áµ°™½È¥¹¥¸AI=%1}%9%Q=IL¤è4(€€€€€€€€€€€€€€€Í•±˜¹…‘ˆ ‰Í¡•±°ˆ°€‰…´ˆ°€‰™½É”µÍÑ½Àˆ°Q%-Q=-}A-¤4(€€€€€€€€€€€€€€€É•ÑÕÉ¸9½¹”€€ŒÁÉ½™¥±”±½…‘•‰ÕÐ¹¼‰…¹¹•Èƒ‹ŠƒŠd€À‘É…™ÑÌ4(€€€€€€€€€€€Í•±˜¹‘¥Íµ¥ÍÍ}Á½ÁÕÁÌ¡áµ°¤4(€€€€€€€€€€€Ñ¥µ”¹Í±••À Ä¤4(€€€€€€€•±Í”è4(€€€€€€€€€€€Í•±˜¹…‘ˆ ‰Í¡•±°ˆ°€‰…´ˆ°€‰™½É”µÍÑ½Àˆ°Q%-Q=-}A-¤4(€€€€€€€€€€€É•ÑÕÉ¸9½¹”4(4(€€€€€€€Í•±˜¹Ñ…À ©Í•±˜¹‰½Õ¹‘Í}•¹Ñ•È¡ˆ¤°‘•±…äôÈ¸Ô¤4(4(€€€€€€€€Œ]…¥Ð™½ÈÉ…™ÑÌÉ¥4(€€€€€€€™½È|¥¸É…¹” à¤è4(€€€€€€€€€€€áµ°€ôÍ•±˜¹‘ÕµÁ}áµ° ¤4(€€€€€€€€€€€¥˜˜‰íQ%-Q=-}A-ôé¥½•„Ìˆ¥¸áµ°½È€‰‘É…™ÑÌˆ¥¸áµ°¹±½Ý•È ¤è4(€€€€€€€€€€€€€€€É•ÑÕÉ¸áµ°4(€€€€€€€€€€€Ñ¥µ”¹Í±••À Ä¤4(€€€€€€€É•ÑÕÉ¸Í•±˜¹‘ÕµÁ}áµ° ¤€€ŒÉ•ÑÕÉ¸Ý¡…Ñ•Ù•ÈÝ”¡…Ù”4(4(€€€‘•˜‘¥Íµ¥ÍÍ}Á½ÁÕÁÌ¡Í•±˜°áµ°èÍÑÈð9½¹”€ô9½¹”°Á½ÁÕÁÌè±¥ÍÑm‘¥Ñtð9½¹”€ô9½¹”¤€´ø‰½½°è4(€€€€€€€€ˆˆ‰¥Íµ¥ÍÌ­¹½Ý¸Á½ÁÕÁÌ¸A…ÍÌÍ­¥±°µÍÁ•¥™¥ŒÁ½ÁÕÁÌ½ÈÕÍ•Ì±½‰…°‘•™…Õ±ÑÌ¸4(€€€€€€€I•ÑÕÉ¹ÌQÉÕ”¥˜Í½µ•Ñ¡¥¹œÝ…Ì‘¥Íµ¥ÍÍ•¸ˆˆˆ4(€€€€€€€¥˜áµ°¥Ì9½¹”è4(€€€€€€€€€€€áµ°€ôÍ•±˜¹‘ÕµÁ}áµ° ¤4(€€€€€€€€Œ€Ä¸MÁ•¥™¥Œ­¹½Ý¸Á½ÁÕÁÌ™¥ÉÍÐ€¡Í­¥±°µÍÁ•¥™¥Œ½Ù•ÉÉ¥‘”±½‰…°¤4(€€€€€€€Á½ÁÕÁ}±¥ÍÐ€ôÁ½ÁÕÁÌ¥˜Á½ÁÕÁÌ¥Ì¹½Ð9½¹”•±Í”}-9=]9}A=AUAL4(€€€€€€€™½ÈÁ½ÁÕÀ¥¸Á½ÁÕÁ}±¥ÍÐè4(€€€€€€€€€€€¥˜Á½ÁÕÁl‰‘•Ñ•Ð‰t¹½Ð¥¸áµ°è4(€€€€€€€€€€€€€€€½¹Ñ¥¹Õ”4(€€€€€€€€€€€ÁÉ¥¹Ð¡˜‰mÁ½ÁÕÁtíÁ½ÁÕÀ¹•Ð ±…‰•°œ°Á½ÁÕÁl‘•Ñ•Ðt¥ôˆ¤4(€€€€€€€€€€€€Œµ•Ñ¡½è€‰‰…¬ˆµ•…¹ÌÁÉ•ÍÌ	…¬¥¹ÍÑ•…½˜Ñ…ÁÁ¥¹œ„‰ÕÑÑ½¸4(€€€€€€€€€€€¥˜Á½ÁÕÀ¹•Ð ‰µ•Ñ¡½ˆ¤€ôô€‰‰…¬ˆè4(€€€€€€€€€€€€€€€Í•±˜¹‰…¬¡‘•±…äôÄ¸À¤4(€€€€€€€€€€€€€€€É•ÑÕÉ¸QÉÕ”4(€€€€€€€€€€€‰Ñ¸€ôÁ½ÁÕÁl‰‰ÕÑÑ½¸‰t4(€€€€€€€€€€€µ…Ñ¡•Ì€ômt4(€€€€€€€€€€€™½È´¥¸É”¹™¥¹‘¥Ñ•È¡É˜œ üéÑ•áÑñ½¹Ñ•¹Ðµ‘•ÍŒ¤ô‰íÉ”¹•Í…Á”¡‰Ñ¸¥ô‰mxùt©‰½Õ¹‘Ìôˆ¡mx‰t¬¤ˆœ°áµ°¤è4(€€€€€€€€€€€€€€€¹ÕµÌ€ô±¥ÍÐ¡µ…À¡¥¹Ð°É”¹™¥¹‘…±°¡È‰q¬ˆ°´¹É½ÕÀ Ä¤¤¤¤4(€€€€€€€€€€€€€€€µ…Ñ¡•Ì¹…ÁÁ•¹ ¡¹ÕµÍlÅt°´¹É½ÕÀ Ä¤¤¤4(€€€€€€€€€€€¥˜µ…Ñ¡•Ìè4(€€€€€€€€€€€€€€€µ…Ñ¡•Ì¹Í½ÉÐ¡­•äõ±…µ‰‘„àèálÁt¤4(€€€€€€€€€€€€€€€Í•±˜¹Ñ…À ©Í•±˜¹‰½Õ¹‘Í}•¹Ñ•È¡µ…Ñ¡•ÍlÁulÅt¤°‘•±…äôÄ¸À¤4(€€€€€€€€€€€€€€€É•ÑÕÉ¸QÉÕ”4(€€€€€€€€Œ€È¸•¹•É¥Œ™…±±‰…¬ƒ‹Š
³Št±¥­…‰±”‰ÕÑÑ½¹ÌÝ¥Ñ ‘¥Íµ¥ÍÌµ±¥­”Ñ•áÐ4(€€€€€€€€Œ€€€¥±Ñ•È½ÕÐ±…É”¹½‘•Ì€¡Ù¥‘•¼…ÁÑ¥½¹Ì•ÑŒ¸¤ƒ‹Š
³ŠtÁ½ÁÕÀ‰ÕÑÑ½¹Ì…É”Íµ…±°¸4(€€€€€€€™½È¹½‘”¥¸Í•±˜¹¹½‘•Ì¡áµ°¤è4(€€€€€€€€€€€¥˜€±¥­…‰±”ô‰ÑÉÕ”ˆœ¹½Ð¥¸¹½‘”è4(€€€€€€€€€€€€€€€½¹Ñ¥¹Õ”4(€€€€€€€€€€€±…‰•°€ô€¡Í•±˜¹¹½‘•}Ñ•áÐ¡¹½‘”¤€¬€ˆ€ˆ€¬Í•±˜¹¹½‘•}½¹Ñ•¹Ñ}‘•ÍŒ¡¹½‘”¤¤¹±½Ý•È ¤¹ÍÑÉ¥À ¤4(€€€€€€€€€€€ˆ€ôÍ•±˜¹¹½‘•}‰½Õ¹‘Ì¡¹½‘”¤4(€€€€€€€€€€€¥˜¹½Ðˆ½È‰lÍt€ð€ÈÀÀè4(€€€€€€€€€€€€€€€½¹Ñ¥¹Õ”4(€€€€€€€€€€€€ŒM­¥À¹½‘•ÌÝ¥‘•ÈÑ¡…¸€ØÀÁÁàƒ‹Š
³ŠtÑ¡½Í”…É”½¹Ñ•¹Ð…É•…Ì°¹½ÐÁ½ÁÕÀ‰ÕÑÑ½¹Ì4(€€€€€€€€€€€¹½‘•}Ý¥‘Ñ €ô‰lÉt€´‰lÁt4(€€€€€€€€€€€¥˜¹½‘•}Ý¥‘Ñ €ø€ØÀÀè4(€€€€€€€€€€€€€€€½¹Ñ¥¹Õ”4(€€€€€€€€€€€Ý½É‘Ì€ôÍ•Ð¡±…‰•°¹ÍÁ±¥Ð ¤¤4(€€€€€€€€€€€¥˜±…‰•°¥¸}%M5%MM}aP½ÈÝ½É‘Ì€˜}%M5%MM}]=ILè4(€€€€€€€€€€€€€€€à°ä€ôÍ•±˜¹¹½‘•}•¹Ñ•È¡ˆ¤4(€€€€€€€€€€€€€€€ÁÉ¥¹Ð¡˜‰mÁ½ÁÕÁt‘¥Íµ¥ÍÍ¥¹œ€í±…‰•±lèÌÁuôœ €¡íáô±íåô¤ˆ¤4(€€€€€€€€€€€€€€€Í•±˜¹Ñ…À¡à°ä°‘•±…äôÄ¸À¤4(€€€€€€€€€€€€€€€É•ÑÕÉ¸QÉÕ”4(€€€€€€€€Œ€Ì¸%¹Ù¥Í¥‰±”½Ù•É±…ä™…±±‰…¬ƒ‹Š
³ŠtÍ½µ”Q¥­Q½¬Á½ÁÕÁÌ€¡…µ¥±äA…¥É¥¹œ°ÁÉ½µ½Ì¤4(€€€€€€€€Œ€€€…É”É•¹‘•É•½Ù•É±…åÌ¥¹Ù¥Í¥‰±”Ñ¼Õ¥…ÕÑ½µ…Ñ½È¸¥Íµ¥ÍÌÝ¥Ñ 	…¬¸4(€€€€€€€¥˜€‰1•…É¸µ½É”ˆ¥¸áµ°…¹€½¹Ñ•¹Ðµ‘•ÍŒôˆ1•…É¸µ½É”ˆœ¥¸áµ°è4(€€€€€€€€€€€ÁÉ¥¹Ð ‰mÁ½ÁÕÁt¥¹Ù¥Í¥‰±”½Ù•É±…ä€¡1•…É¸µ½É”Ù¥Í¥‰±”¤ƒ‹Š
³ŠtÁÉ•ÍÍ¥¹œ	…¬ˆ¤4(€€€€€€€€€€€Í•±˜¹‰…¬¡‘•±…äôÄ¸À¤4(€€€€€€€€€€€É•ÑÕÉ¸QÉÕ”4(€€€€€€€É•ÑÕÉ¸…±Í”4(4(€€€‘•˜Í•…É¡}¹…Ù¥…Ñ”¡Í•±˜°ÅÕ•ÉäèÍÑÈ°Ñ…ˆèÍÑÈð9½¹”€ô9½¹”¤€´øÍÑÈè4(€€€€€€€€ˆˆ‰=Á•¸Í•…É °ÑåÁ”ÅÕ•Éä°ÍÕ‰µ¥Ð°½ÁÑ¥½¹…±±ä¹…Ù¥…Ñ”Ñ¼„¹…µ•Ñ…ˆ¸4(4(€€€€€€€]½É­Ì™É½´…¹äÍÉ••¸ÍÑ…Ñ”€¡¡½µ”°Í•…É¡}É•ÍÕ±ÑÌ°•ÑŒ¸¤¸4(€€€€€€€ÅÕ•Éä€€ƒ‹Š
³ŠtÍ•…É Ñ•É´ì€œŒœƒ‹ŠƒŠd-e=}A=U9°€œ€œƒ‹ŠƒŠd€•Ìì€ œÍÑÉ¥ÁÁ•…ÕÑ½µ…Ñ¥…±±ä4(€€€€€€€Ñ…ˆ€€€€ƒ‹Š
³Št”¹œ¸€UÍ•ÉÌœ°€Q½Àœ°€Y¥‘•½Ìœƒ‹Š
³ŠtÑ…ÀÑ¡…ÐÑ…ˆ…™Ñ•ÈÉ•ÍÕ±ÑÌ±½…4(€€€€€€€I•ÑÕÉ¹Ì™É•Í a50…™Ñ•È¹…Ù¥…Ñ¥½¸¸4(€€€€€€€€ˆˆˆ4(€€€€€€€áµ°€ôÍ•±˜¹‘ÕµÁ}áµ° ¤4(€€€€€€€ÍÐ€ôÍ•±˜¹ÍÉ••¹}ÑåÁ”¡áµ°¤4(4(€€€€€€€€Œƒ‹ŠwŠ
³‹ŠwŠ
°=Á•¸Í•…É ƒ‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
°4(€€€€€€€¥˜ÍÐ€ôô€‰¡½µ”ˆè4(€€€€€€€€€€€¹½‘•Ì€ôÍ•±˜¹™¥¹‘}¹½‘•Ì¡áµ°°É¥õI%}MI!}%=8¤4(€€€€€€€€€€€Í•±˜¹Ñ…Á}¹½‘”¡¹½‘•ÍlÁt°‘•±…äôÄ¸À¤¥˜¹½‘•Ì•±Í”Í•±˜¹Ñ…À ÄÀÄÄ°€ÄÈä°‘•±…äôÄ¸À¤4(€€€€€€€•±¥˜ÍÐ¥¸€ ‰Í•…É¡}É•ÍÕ±ÑÌˆ°€‰ÕÍ•ÉÍ}Ñ…ˆˆ¤è4(€€€€€€€€€€€¹½‘•Ì€ôÍ•±˜¹™¥¹‘}¹½‘•Ì¡áµ°°É¥õI%}MI!}	=`¤4(€€€€€€€€€€€Í•±˜¹Ñ…Á}¹½‘”¡¹½‘•ÍlÁt°‘•±…äôÄ¸À¤¥˜¹½‘•Ì•±Í”Í•±˜¹Ñ…À ÔÐÀ°€ØÔ°‘•±…äôÄ¸À¤4(€€€€€€€€Œ•±Í”…±É•…‘ä…ÐÍ•…É¡}¥¹ÁÕÐƒ‹Š
³ŠtÁÉ½••‘¥É•Ñ±ä4(4(€€€€€€€€Œ]…¥ÐÕ¹Ñ¥°Í•…É ¥¹ÁÕÐ¥ÌÉ•…‘ä‰•™½É”ÑåÁ¥¹œ€¡É•ÑÉäÑ…À¥˜¹••‘•¤4(€€€€€€€™½È…ÑÑ•µÁÐ¥¸É…¹” Ì¤è4(€€€€€€€€€€€™½È|¥¸É…¹” Ø¤è4(€€€€€€€€€€€€€€€áµ°€ôÍ•±˜¹‘ÕµÁ}áµ° ¤4(€€€€€€€€€€€€€€€¥˜Í•±˜¹ÍÉ••¹}ÑåÁ”¡áµ°¤€ôô€‰Í•…É¡}¥¹ÁÕÐˆè4(€€€€€€€€€€€€€€€€€€€‰É•…¬4(€€€€€€€€€€€€€€€Í•±˜¹‘¥Íµ¥ÍÍ}Á½ÁÕÁÌ¡áµ°¤4(€€€€€€€€€€€€€€€Ñ¥µ”¹Í±••À Ä¸À¤4(€€€€€€€€€€€•±Í”è4(€€€€€€€€€€€€€€€€Œ¥‘¸ÐÉ•… Í•…É¡}¥¹ÁÕÐƒ‹Š
³ŠtÑ…À¥½¸……¥¸…¹É•ÑÉä4(€€€€€€€€€€€€€€€áµ°€ôÍ•±˜¹‘ÕµÁ}áµ° ¤4(€€€€€€€€€€€€€€€ÕÈ€ôÍ•±˜¹ÍÉ••¹}ÑåÁ”¡áµ°¤4(€€€€€€€€€€€€€€€¥˜ÕÈ€ôô€‰¡½µ”ˆè4(€€€€€€€€€€€€€€€€€€€¹½‘•Ì€ôÍ•±˜¹™¥¹‘}¹½‘•Ì¡áµ°°É¥õI%}MI!}%=8¤4(€€€€€€€€€€€€€€€€€€€Í•±˜¹Ñ…Á}¹½‘”¡¹½‘•ÍlÁt°‘•±…äôÄ¸Ô¤¥˜¹½‘•Ì•±Í”Í•±˜¹Ñ…À ÄÀÄÄ°€ÄÈä°‘•±…äôÄ¸Ô¤4(€€€€€€€€€€€€€€€•±¥˜ÕÈ¥¸€ ‰Í•…É¡}É•ÍÕ±ÑÌˆ°€‰ÕÍ•ÉÍ}Ñ…ˆˆ¤è4(€€€€€€€€€€€€€€€€€€€¹½‘•Ì€ôÍ•±˜¹™¥¹‘}¹½‘•Ì¡áµ°°É¥õI%}MI!}	=`¤4(€€€€€€€€€€€€€€€€€€€Í•±˜¹Ñ…Á}¹½‘”¡¹½‘•ÍlÁt°‘•±…äôÄ¸È¤¥˜¹½‘•Ì•±Í”Í•±˜¹Ñ…À ÔÐÀ°€ØÔ°‘•±…äôÄ¸È¤4(€€€€€€€€€€€€€€€½¹Ñ¥¹Õ”4(€€€€€€€€€€€‰É•…¬€€ŒÉ•…¡•Í•…É¡}¥¹ÁÕÐ4(4(€€€€€€€€Œƒ‹ŠwŠ
³‹ŠwŠ
°QåÁ”ÅÕ•Éäƒ‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
°4(€€€€€€€±•…¸€ôÅÕ•Éä¹±ÍÑÉ¥À ‰ ˆ¤4(€€€€€€€Í•±˜¹…‘ˆ ‰Í¡•±°ˆ°€‰¥¹ÁÕÐˆ°€‰­•å•Ù•¹Ðˆ°€‰-e=}5=Y}9ˆ¤4(€€€€€€€™½È|¥¸É…¹” àÀ¤è4(€€€€€€€€€€€Í•±˜¹…‘ˆ ‰Í¡•±°ˆ°€‰¥¹ÁÕÐˆ°€‰­•å•Ù•¹Ðˆ°€‰-e=}0ˆ¤4(€€€€€€€™½È ¥¸±•…¸è4(€€€€€€€€€€€¥˜ €ôô€ˆŒˆè4(€€€€€€€€€€€€€€€Í•±˜¹…‘ˆ ‰Í¡•±°ˆ°€‰¥¹ÁÕÐˆ°€‰­•å•Ù•¹Ðˆ°€‰-e=}A=U9ˆ¤4(€€€€€€€€€€€•±¥˜ €ôô€ˆ€ˆè4(€€€€€€€€€€€€€€€Í•±˜¹…‘ˆ ‰Í¡•±°ˆ°€‰¥¹ÁÕÐˆ°€‰Ñ•áÐˆ°€ˆ•Ìˆ¤4(€€€€€€€€€€€•±Í”è4(€€€€€€€€€€€€€€€Í•±˜¹…‘ˆ ‰Í¡•±°ˆ°€‰¥¹ÁÕÐˆ°€‰Ñ•áÐˆ° ¤4(€€€€€€€€€€€Ñ¥µ”¹Í±••À À¸È¤4(€€€€€€€€ŒQ…À€‰M•…É ˆ‰ÕÑÑ½¸¥¹ÍÑ•…½˜9QH€¡9QHÍ•±•ÑÌ…ÕÑ½½µÁ±•Ñ”¤4(€€€€€€€áµ°€ôÍ•±˜¹‘ÕµÁ}áµ° ¤4(€€€€€€€Í•…É¡}‰Ñ¸€ôl4(€€€€€€€€€€€¸4(€€€€€€€€€€€™½È¸¥¸Í•±˜¹¹½‘•Ì¡áµ°¤4(€€€€€€€€€€€¥˜Í•±˜¹¹½‘•}Ñ•áÐ¡¸¤€ôô€‰M•…É ˆ…¹€±¥­…‰±”ô‰ÑÉÕ”ˆœ¥¸¸…¹€¡ˆ€èôÍ•±˜¹¹½‘•}‰½Õ¹‘Ì¡¸¤¤…¹‰lÅt€ð€ÈÀÀ4(€€€€€€€t4(€€€€€€€¥˜Í•…É¡}‰Ñ¸è4(€€€€€€€€€€€Í•±˜¹Ñ…Á}¹½‘”¡Í•…É¡}‰Ñ¹lÁt°‘•±…äôÈ¸Ô¤4(€€€€€€€•±Í”è4(€€€€€€€€€€€Í•±˜¹ÁÉ•ÍÍ}•¹Ñ•È¡‘•±…äôÈ¸Ô¤4(4(€€€€€€€€Œƒ‹ŠwŠ
³‹ŠwŠ
°]…¥Ð™½ÈÉ•ÍÕ±ÑÌƒ‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
°4(€€€€€€€áµ°€ôÍ•±˜¹‘ÕµÁ}áµ° ¤4(€€€€€€€™½È…ÑÑ•µÁÐ¥¸É…¹” Ü¤è4(€€€€€€€€€€€ÍÐ€ôÍ•±˜¹ÍÉ••¹}ÑåÁ”¡áµ°¤4(€€€€€€€€€€€¥˜ÍÐ¥¸€ ‰Í•…É¡}É•ÍÕ±ÑÌˆ°€‰ÕÍ•ÉÍ}Ñ…ˆˆ¤è4(€€€€€€€€€€€€€€€‰É•…¬4(€€€€€€€€€€€¥˜Í•±˜¹‘¥Íµ¥ÍÍ}Á½ÁÕÁÌ¡áµ°¤è4(€€€€€€€€€€€€€€€áµ°€ôÍ•±˜¹‘ÕµÁ}áµ° ¤4(€€€€€€€€€€€€€€€½¹Ñ¥¹Õ”4(€€€€€€€€€€€¥˜ÍÐ€ôô€‰Í•…É¡}¥¹ÁÕÐˆè4(€€€€€€€€€€€€€€€ÍÕœ€ôl4(€€€€€€€€€€€€€€€€€€€¸4(€€€€€€€€€€€€€€€€€€€™½È¸¥¸Í•±˜¹™¥¹‘}¹½‘•Ì¡áµ°°É¥õI%}MUMQ%=8¤4(€€€€€€€€€€€€€€€€€€€¥˜±•…¸¹±½Ý•È ¤¹±ÍÑÉ¥À ˆŒˆ¤¥¸Í•±˜¹¹½‘•}Ñ•áÐ¡¸¤¹±½Ý•È ¤4(€€€€€€€€€€€€€€€t4(€€€€€€€€€€€€€€€¥˜ÍÕœè4(€€€€€€€€€€€€€€€€€€€Í•±˜¹Ñ…Á}¹½‘”¡ÍÕlÁt°‘•±…äôÈ¸À¤4(€€€€€€€€€€€€€€€•±Í”è4(€€€€€€€€€€€€€€€€€€€€ŒQ…ÀÑ¡”€‰M•…É ˆ‰ÕÑÑ½¸€¡Ñ½ÀµÉ¥¡Ð¤¥¹ÍÑ•…½˜9QH4(€€€€€€€€€€€€€€€€€€€€Œ€¡9QHÍ•±•ÑÌ…ÕÑ½½µÁ±•Ñ”ÍÕ•ÍÑ¥½¹Ì¥¹ÍÑ•…½˜ÍÕ‰µ¥ÑÑ¥¹œ¤4(€€€€€€€€€€€€€€€€€€€Í•…É¡}‰Ñ¸€ôl4(€€€€€€€€€€€€€€€€€€€€€€€¸4(€€€€€€€€€€€€€€€€€€€€€€€™½È¸¥¸Í•±˜¹¹½‘•Ì¡áµ°¤4(€€€€€€€€€€€€€€€€€€€€€€€¥˜Í•±˜¹¹½‘•}Ñ•áÐ¡¸¤€ôô€‰M•…É ˆ4(€€€€€€€€€€€€€€€€€€€€€€€…¹€±¥­…‰±”ô‰ÑÉÕ”ˆœ¥¸¸4(€€€€€€€€€€€€€€€€€€€€€€€…¹€¡ˆ€èôÍ•±˜¹¹½‘•}‰½Õ¹‘Ì¡¸¤¤4(€€€€€€€€€€€€€€€€€€€€€€€…¹‰lÅt€ð€ÈÀÀ4(€€€€€€€€€€€€€€€€€€€t4(€€€€€€€€€€€€€€€€€€€¥˜Í•…É¡}‰Ñ¸è4(€€€€€€€€€€€€€€€€€€€€€€€Í•±˜¹Ñ…Á}¹½‘”¡Í•…É¡}‰Ñ¹lÁt°‘•±…äôÈ¸Ô¤4(€€€€€€€€€€€€€€€€€€€•±Í”è4(€€€€€€€€€€€€€€€€€€€€€€€Í•±˜¹…‘ˆ ‰Í¡•±°ˆ°€‰¥¹ÁÕÐˆ°€‰­•å•Ù•¹Ðˆ°€‰-e=}9QHˆ¤4(€€€€€€€€€€€€€€€€€€€€€€€Ñ¥µ”¹Í±••À È¸À¤4(€€€€€€€€€€€•±Í”è4(€€€€€€€€€€€€€€€Ñ¥µ”¹Í±••À Ä¸Ô¤4(€€€€€€€€€€€áµ°€ôÍ•±˜¹‘ÕµÁ}áµ° ¤4(€€€€€€€•±Í”è4(€€€€€€€€€€€É…¥Í”IÕ¹Ñ¥µ•ÉÉ½È¡˜½Õ±¹½ÐÉ•… Í•…É É•ÍÕ±ÑÌ™½È€‰íÅÕ•Éåôˆ…™Ñ•È€Ü…ÑÑ•µÁÑÌœ¤4(4(€€€€€€€€Œƒ‹ŠwŠ
³‹ŠwŠ
°9…Ù¥…Ñ”Ñ¼Ñ…ˆƒ‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
°4(€€€€€€€¥˜Ñ…ˆè4(€€€€€€€€€€€™½È¹½‘”¥¸Í•±˜¹¹½‘•Ì¡áµ°¤è4(€€€€€€€€€€€€€€€¥˜Í•±˜¹¹½‘•}Ñ•áÐ¡¹½‘”¤€„ôÑ…ˆè4(€€€€€€€€€€€€€€€€€€€½¹Ñ¥¹Õ”4(€€€€€€€€€€€€€€€ˆ€ôÍ•±˜¹¹½‘•}‰½Õ¹‘Ì¡¹½‘”¤4(€€€€€€€€€€€€€€€¥˜ˆ…¹‰lÍt€ð€ÌÔÀè4(€€€€€€€€€€€€€€€€€€€Í•±˜¹Ñ…À ©Í•±˜¹¹½‘•}•¹Ñ•È¡ˆ¤°‘•±…äôÈ¸À¤4(€€€€€€€€€€€€€€€€€€€áµ°€ôÍ•±˜¹‘ÕµÁ}áµ° ¤4(€€€€€€€€€€€€€€€€€€€‰É•…¬4(4(€€€€€€€É•ÑÕÉ¸áµ°4(4(€€€‘•˜ÍÉ••¹}ÑåÁ”¡Í•±˜°áµ°èÍÑÈ¤€´øÍÑÈè4(€€€€€€€€ˆˆ‰±…ÍÍ¥™äÕÉÉ•¹ÐQ¥­Q½¬ÍÉ••¸¸4(4(€€€€€€€I•ÑÕÉ¹Ìè¡½µ”ðÍ•…É¡}¥¹ÁÕÐðÍ•…É¡}É•ÍÕ±ÑÌðÕÍ•ÉÍ}Ñ…ˆð™¥±Ñ•ÉÍ}Á…¹•°ðÕ¹­¹½Ý¸4(€€€€€€€€ˆˆˆ4(€€€€€€€¥˜Í•±˜¹™¥¹‘}¹½‘•Ì¡áµ°°É¥õI%}UMI95}I=\¤è4(€€€€€€€€€€€É•ÑÕÉ¸€‰ÕÍ•ÉÍ}Ñ…ˆˆ4(€€€€€€€¥˜Í•±˜¹™¥¹‘}¹½‘•Ì¡áµ°°É¥õI%}%1QI}!%@¤è4(€€€€€€€€€€€É•ÑÕÉ¸€‰™¥±Ñ•ÉÍ}Á…¹•°ˆ4(€€€€€€€¥˜…¹ä ¡ˆ€èôÍ•±˜¹¹½‘•}‰½Õ¹‘Ì¡¸¤¤…¹‰lÍt€ð€ÌÔÀ™½È¸¥¸Í•±˜¹™¥¹‘}¹½‘•Ì¡áµ°°Ñ•áÐô‰UÍ•ÉÌˆ¤¤è4(€€€€€€€€€€€É•ÑÕÉ¸€‰Í•…É¡}É•ÍÕ±ÑÌˆ4(€€€€€€€¥˜Í•±˜¹™¥¹‘}¹½‘•Ì¡áµ°°É¥õI%}MI!}	=`¤è4(€€€€€€€€€€€É•ÑÕÉ¸€‰Í•…É¡}¥¹ÁÕÐˆ4(€€€€€€€¥˜Í•±˜¹™¥¹‘}¹½‘•Ì¡áµ°°É¥õI%}MI!}%=8¤è4(€€€€€€€€€€€É•ÑÕÉ¸€‰¡½µ”ˆ4(€€€€€€€É•ÑÕÉ¸€‰Õ¹­¹½Ý¸ˆ4(4(€€€‘•˜¡•­}Ñ¥­Ñ½­}Ù•ÉÍ¥½¸¡Í•±˜¤€´øÍÑÈè4(€€€€€€€€ˆˆ‰I•ÑÕÉ¸¥¹ÍÑ…±±•Q¥­Q½¬Ù•ÉÍ¥½¸¸]…É¸¥˜¥Ð‘¥™™•ÉÌ™É½´-9=]9}Q%-Q=-}YIM%=8¸ˆˆˆ4(€€€€€€€½ÕÐ€ôÍ•±˜¹…‘ˆ ‰Í¡•±°ˆ°€‰‘ÕµÁÍåÌˆ°€‰Á…­…”ˆ°Q%-Q=-}A-°Ñ¥µ•½ÕÐôÄÀ¤4(€€€€€€€´€ôÉ”¹Í•…É ¡È‰Ù•ÉÍ¥½¹9…µ”ô¡qL¬¤ˆ°½ÕÐ¤4(€€€€€€€Ù•È€ô´¹É½ÕÀ Ä¤¥˜´•±Í”€‰Õ¹­¹½Ý¸ˆ4(€€€€€€€¥˜Ù•È€„ô-9=]9}Q%-Q=-}YIM%=8è4(€€€€€€€€€€€ÁÉ¥¹Ð¡˜‰m]I9tQ¥­Q½¬Ù•ÉÍ¥½¸íÙ•Éô€„ô•áÁ•Ñ•í-9=]9}Q%-Q=-}YIM%=9ôƒ‹Š
³ŠtI%Ìµ…ä‰”ÍÑ…±”„ˆ¤4(€€€€€€€É•ÑÕÉ¸Ù•È4(4(€€€‘•˜•Ñ}…ÁÁ}Ù•ÉÍ¥½¸¡Í•±˜°Á…­…”èÍÑÈ¤€´øÍÑÈè4(€€€€€€€€ˆˆ‰I•ÑÕÉ¸Ù•ÉÍ¥½¹9…µ”™½È…¹ä¥¹ÍÑ…±±•Á…­…”¸ˆˆˆ4(€€€€€€€½ÕÐ€ôÍ•±˜¹…‘ˆ ‰Í¡•±°ˆ°€‰‘ÕµÁÍåÌˆ°€‰Á…­…”ˆ°Á…­…”°Ñ¥µ•½ÕÐôÄÀ¤4(€€€€€€€´€ôÉ”¹Í•…É ¡È‰Ù•ÉÍ¥½¹9…µ”ô¡qL¬¤ˆ°½ÕÐ¤4(€€€€€€€É•ÑÕÉ¸´¹É½ÕÀ Ä¤¥˜´•±Í”€‰Õ¹­¹½Ý¸ˆ4(4(€€€‘•˜ÕÁ‘…Ñ•}…ÁÀ¡Í•±˜°Á…­…”èÍÑÈ°Ñ¥µ•½ÕÐè¥¹Ð€ô€ÌÀÀ°±½œõÁÉ¥¹Ð¤€´øÍÑÈè4(€€€€€€€€ˆˆ‰UÁ‘…Ñ”…¸…ÁÀÙ¥„A±…äMÑ½É”¸I•ÑÕÉ¹Ì¹•ÜÙ•ÉÍ¥½¸ÍÑÉ¥¹œ¸4(4(€€€€€€€±½Üè™½É”µÍÑ½À…ÁÀƒ‹ŠƒŠd½Á•¸A±…äMÑ½É”Á…”ƒ‹ŠƒŠdÑ…ÀUÁ‘…Ñ”ƒ‹ŠƒŠdÁ½±°™½È½µÁ±•Ñ¥½¸¸4(€€€€€€€I…¥Í•ÌIÕ¹Ñ¥µ•ÉÉ½È¥˜ÕÁ‘…Ñ”‰ÕÑÑ½¸¹½Ð™½Õ¹½ÈÑ¥µ•Ì½ÕÐ¸4(€€€€€€€€ˆˆˆ4(€€€€€€€½±‘}Ù•È€ôÍ•±˜¹•Ñ}…ÁÁ}Ù•ÉÍ¥½¸¡Á…­…”¤4(€€€€€€€±½œ¡˜‰mÕÁ‘…Ñ•tíÁ…­…•ôÕÉÉ•¹ÐÙ•ÉÍ¥½¸èí½±‘}Ù•Éôˆ¤4(4(€€€€€€€€Œ½É”µÍÑ½ÀÑ¡”…ÁÀÍ¼¥Ð‘½•Í¸Ð¥¹Ñ•É™•É”4(€€€€€€€Í•±˜¹…‘ˆ ‰Í¡•±°ˆ°€‰…´ˆ°€‰™½É”µÍÑ½Àˆ°Á…­…”¤4(€€€€€€€Ñ¥µ”¹Í±••À Ä¤4(4(€€€€€€€€Œ=Á•¸A±…äMÑ½É”Á…”™½ÈÑ¡¥Ì…ÁÀ4(€€€€€€€Í•±˜¹…‘ˆ ‰Í¡•±°ˆ°€‰…´ˆ°€‰ÍÑ…ÉÐˆ°€ˆµ„ˆ°€‰…¹‘É½¥¹¥¹Ñ•¹Ð¹…Ñ¥½¸¹Y%\ˆ°€ˆµˆ°˜‰µ…É­•Ðè¼½‘•Ñ…¥±Ìý¥õíÁ…­…•ôˆ¤4(€€€€€€€Ñ¥µ”¹Í±••À Ð¤4(4(€€€€€€€€Œ¥¹…¹Ñ…À€‰UÁ‘…Ñ”ˆ‰ÕÑÑ½¸4(€€€€€€€áµ°€ôÍ•±˜¹‘ÕµÁ}áµ° ¤4(€€€€€€€ÕÁ‘…Ñ•}¹½‘”€ô9½¹”4(€€€€€€€™½È¹½‘”¥¸Í•±˜¹¹½‘•Ì¡áµ°¤è4(€€€€€€€€€€€¥˜Í•±˜¹¹½‘•}Ñ•áÐ¡¹½‘”¤€ôô€‰UÁ‘…Ñ”ˆè4(€€€€€€€€€€€€€€€ÕÁ‘…Ñ•}¹½‘”€ô¹½‘”4(€€€€€€€€€€€€€€€‰É•…¬4(€€€€€€€¥˜¹½ÐÕÁ‘…Ñ•}¹½‘”è4(€€€€€€€€€€€€Œ¡•¬¥˜…±É•…‘äÕÀÑ¼‘…Ñ”4(€€€€€€€€€€€™½È¹½‘”¥¸Í•±˜¹¹½‘•Ì¡áµ°¤è4(€€€€€€€€€€€€€€€¥˜Í•±˜¹¹½‘•}Ñ•áÐ¡¹½‘”¤€ôô€‰=Á•¸ˆè4(€€€€€€€€€€€€€€€€€€€±½œ¡˜‰mÕÁ‘…Ñ•t±É•…‘äÕÀÑ¼‘…Ñ”èí½±‘}Ù•Éôˆ¤4(€€€€€€€€€€€€€€€€€€€É•ÑÕÉ¸½±‘}Ù•È4(€€€€€€€€€€€É…¥Í”IÕ¹Ñ¥µ•ÉÉ½È¡˜‰UÁ‘…Ñ”‰ÕÑÑ½¸¹½Ð™½Õ¹™½ÈíÁ…­…•ôˆ¤4(4(€€€€€€€ˆ€ôÍ•±˜¹¹½‘•}‰½Õ¹‘Ì¡ÕÁ‘…Ñ•}¹½‘”¤4(€€€€€€€¥˜ˆè4(€€€€€€€€€€€à°ä€ôÍ•±˜¹¹½‘•}•¹Ñ•È¡ˆ¤4(€€€€€€€€€€€±½œ¡˜‰mÕÁ‘…Ñ•tQ…ÁÁ¥¹œUÁ‘…Ñ” €¡íáô±íåô¤ˆ¤4(€€€€€€€€€€€Í•±˜¹Ñ…À¡à°ä°‘•±…äôÈ¸À¤4(€€€€€€€•±Í”è4(€€€€€€€€€€€É…¥Í”IÕ¹Ñ¥µ•ÉÉ½È ‰UÁ‘…Ñ”‰ÕÑÑ½¸¡…Ì¹¼‰½Õ¹‘Ìˆ¤4(4(€€€€€€€€ŒA½±°Õ¹Ñ¥°€‰=Á•¸ˆ…ÁÁ•…ÉÌ€¡ÕÁ‘…Ñ”½µÁ±•Ñ”¤½ÈÑ¥µ•½ÕÐ4(€€€€€€€Á½±±}¥¹Ñ•ÉÙ…°€ô€Ô4(€€€€€€€•±…ÁÍ•€ô€À4(€€€€€€€Ý¡¥±”•±…ÁÍ•€ðÑ¥µ•½ÕÐè4(€€€€€€€€€€€Ñ¥µ”¹Í±••À¡Á½±±}¥¹Ñ•ÉÙ…°¤4(€€€€€€€€€€€•±…ÁÍ•€¬ôÁ½±±}¥¹Ñ•ÉÙ…°4(€€€€€€€€€€€áµ°€ôÍ•±˜¹‘ÕµÁ}áµ° ¤4(€€€€€€€€€€€™½È¹½‘”¥¸Í•±˜¹¹½‘•Ì¡áµ°¤è4(€€€€€€€€€€€€€€€ÑáÐ€ôÍ•±˜¹¹½‘•}Ñ•áÐ¡¹½‘”¤4(€€€€€€€€€€€€€€€¥˜ÑáÐ€ôô€‰=Á•¸ˆè4(€€€€€€€€€€€€€€€€€€€¹•Ý}Ù•È€ôÍ•±˜¹•Ñ}…ÁÁ}Ù•ÉÍ¥½¸¡Á…­…”¤4(€€€€€€€€€€€€€€€€€€€±½œ¡˜‰mÕÁ‘…Ñ•t½¹”„í½±‘}Ù•Éôƒ‹ŠƒŠdí¹•Ý}Ù•Éô€¡í•±…ÁÍ•‘õÌ¤ˆ¤4(€€€€€€€€€€€€€€€€€€€É•ÑÕÉ¸¹•Ý}Ù•È4(€€€€€€€€€€€±½œ¡˜‰mÕÁ‘…Ñ•t½Ý¹±½…‘¥¹œ¸¸¸€¡í•±…ÁÍ•‘õÌ¤ˆ¤4(4(€€€€€€€É…¥Í”IÕ¹Ñ¥µ•ÉÉ½È¡˜‰UÁ‘…Ñ”Ñ¥µ•½ÕÐ…™Ñ•ÈíÑ¥µ•½ÕÑõÌˆ¤4(4(4)‘•˜•Ñ}‘•Ù¥”¡Í•É¥…°èÍÑÈð9½¹”€ô9½¹”¤€´ø•Ù¥”è4(€€€€ˆˆ‰I•ÑÕÉ¸„•Ù¥”¥¹ÍÑ…¹”¸ÕÑ¼µ‘•Ñ•ÑÌ¥˜½¹±ä½¹”Á¡½¹”½¹¹•Ñ•¸ˆˆˆ4(€€€¥µÁ½ÉÐ½Ì4(4(€€€Í•É¥…°€ôÍ•É¥…°½È½Ì¹•¹Ù¥É½¸¹•Ð ‰Y%ˆ¤4(€€€¥˜Í•É¥…°è4(€€€€€€€É•ÑÕÉ¸•Ù¥”¡Í•É¥…°¤4(€€€½¹¹•Ñ•€ô±¥ÍÑ}½¹¹•Ñ• ¤4(€€€¥˜±•¸¡½¹¹•Ñ•¤€ôô€Äè4(€€€€€€€É•ÑÕÉ¸•Ù¥”¡½¹¹•Ñ•‘lÁt¤4(€€€É…¥Í”IÕ¹Ñ¥µ•ÉÉ½È¡˜‰5Õ±Ñ¥Á±”‘•Ù¥•Ì½¹¹•Ñ•ƒ‹Š
³ŠtÍÁ•¥™äÍ•É¥…°¸½Õ¹èí½¹¹•Ñ•‘ôˆ¤4(4(4)‘•˜±¥ÍÑ}½¹¹•Ñ• ¤€´ø±¥ÍÑmÍÑÉtè4(€€€½ÕÐ€ôÍÕ‰ÁÉ½•ÍÌ¹ÉÕ¸¡l‰…‘ˆˆ°€‰‘•Ù¥•Ì‰t°…ÁÑÕÉ•}½ÕÑÁÕÐõQÉÕ”°Ñ•áÐõQÉÕ”¤¹ÍÑ‘½ÕÐ4(€€€É•ÑÕÉ¸m±¥¹”¹ÍÁ±¥Ð ¥lÁt™½È±¥¹”¥¸½ÕÐ¹ÍÁ±¥Ñ±¥¹•Ì ¥lÄét¥˜±¥¹”¹ÍÑÉ¥À ¤…¹±¥¹”¹ÍÁ±¥Ð ¥l´Åt€ôô€‰‘•Ù¥”‰t4