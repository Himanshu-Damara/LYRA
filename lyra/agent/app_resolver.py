"""
app_resolver.py — Maps natural language app names to Android package names.

Provides a lookup table for common apps and a fallback mechanism using
`pm list packages` to search the device's installed packages.
"""

from typing import Optional
from lyra.phone.adb_controller import ADBController


# Common app name -> package name mappings
APP_PACKAGES = {
    # Social Media
    "instagram": "com.instagram.android",
    "whatsapp": "com.whatsapp",
    "facebook": "com.facebook.katana",
    "messenger": "com.facebook.orca",
    "twitter": "com.twitter.android",
    "x": "com.twitter.android",
    "telegram": "org.telegram.messenger",
    "snapchat": "com.snapchat.android",
    "tiktok": "com.zhiliaoapp.musically",
    "reddit": "com.reddit.frontpage",
    "linkedin": "com.linkedin.android",
    "discord": "com.discord",
    "pinterest": "com.pinterest",
    "threads": "com.instagram.barcelona",

    # Communication
    "gmail": "com.google.android.gm",
    "email": "com.google.android.gm",
    "mail": "com.google.android.gm",
    "phone": "com.android.dialer",
    "dialer": "com.android.dialer",
    "contacts": "com.android.contacts",
    "messages": "com.google.android.apps.messaging",
    "sms": "com.google.android.apps.messaging",

    # Google Apps
    "chrome": "com.android.chrome",
    "browser": "com.android.chrome",
    "maps": "com.google.android.apps.maps",
    "google maps": "com.google.android.apps.maps",
    "youtube": "com.google.android.youtube",
    "play store": "com.android.vending",
    "google play": "com.android.vending",
    "google": "com.google.android.googlequicksearchbox",
    "drive": "com.google.android.apps.docs",
    "google drive": "com.google.android.apps.docs",
    "photos": "com.google.android.apps.photos",
    "google photos": "com.google.android.apps.photos",
    "calendar": "com.google.android.calendar",
    "translate": "com.google.android.apps.translate",
    "keep": "com.google.android.keep",
    "google keep": "com.google.android.keep",
    "meet": "com.google.android.apps.meetings",
    "google meet": "com.google.android.apps.meetings",

    # System Apps
    "settings": "com.android.settings",
    "camera": "com.android.camera",
    "clock": "com.android.deskclock",
    "alarm": "com.android.deskclock",
    "calculator": "com.android.calculator2",
    "files": "com.android.documentsui",
    "file manager": "com.android.documentsui",
    "gallery": "com.android.gallery3d",

    # Media & Entertainment
    "spotify": "com.spotify.music",
    "netflix": "com.netflix.mediaclient",
    "amazon": "com.amazon.mShop.android.shopping",
    "amazon prime": "com.amazon.avod.thirdpartyclient",

    # Productivity
    "notion": "notion.id",
    "slack": "com.Slack",
    "zoom": "us.zoom.videomeetings",
    "teams": "com.microsoft.teams",
    "microsoft teams": "com.microsoft.teams",
    "word": "com.microsoft.office.word",
    "excel": "com.microsoft.office.excel",
    "onenote": "com.microsoft.office.onenote",

    # Finance
    "gpay": "com.google.android.apps.nbu.paisa.user",
    "google pay": "com.google.android.apps.nbu.paisa.user",
    "paytm": "net.one97.paytm",
    "phonepe": "com.phonepe.app",

    # Utilities
    "notes": "com.android.notes",
    "notepad": "com.android.notes",
}


def resolve_package(app_name: str) -> Optional[str]:
    """
    Resolves a natural language app name to an Android package name.
    First checks the local lookup table, then searches installed packages on the device.

    Args:
        app_name: Natural language app name (e.g., "instagram", "WhatsApp", "camera")

    Returns:
        Android package name string, or None if unresolvable
    """
    name_lower = app_name.lower().strip()

    # Direct lookup
    if name_lower in APP_PACKAGES:
        return APP_PACKAGES[name_lower]

    # Partial match (e.g., "insta" matches "instagram")
    for key, package in APP_PACKAGES.items():
        if name_lower in key or key in name_lower:
            return package

    # Fallback: search installed packages on the device
    return _search_device_packages(name_lower)


def _search_device_packages(query: str) -> Optional[str]:
    """
    Searches installed packages on the connected device for a matching package.
    Uses `pm list packages` via ADB.
    """
    try:
        controller = ADBController()
        output = controller.shell("pm", "list", "packages")
        packages = [line.replace("package:", "").strip() for line in output.splitlines()]

        # Search for query in package names
        for pkg in packages:
            if query in pkg.lower():
                return pkg
    except Exception:
        pass

    return None


def list_known_apps() -> list:
    """Returns a sorted list of all known app names."""
    return sorted(set(APP_PACKAGES.keys()))
