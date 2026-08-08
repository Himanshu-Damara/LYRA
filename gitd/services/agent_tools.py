"""Agent tool definitions Ã¢â‚¬â€ maps tool names to device_context functions.

Used by the agent chat service to execute LLM tool calls.
Tool schemas are in Anthropic's tool format and auto-converted for other providers.
"""

import json
import sys

from gitd.bots.common.device import get_device, is_ios_ref
from gitd.services import device_context as ctx
from gitd.services.tool_platforms import platform_error_text, supports_platform
from gitd.skills.platforms import skill_platform_error_text, skill_supports_device

# Ã¢â€â‚¬Ã¢â€â‚¬ Tool registry Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

TOOLS = [
    {
        "name": "list_devices",
        "description": "List connected Android ADB device refs and configured iOS Appium device refs.",
        "input_schema": {"type": "object", "properties": {}},
    },
    # Screen reading
    {
        "name": "screenshot",
        "description": "Take a screenshot of the device screen. Returns base64 JPEG. Use this to SEE what's on screen.",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "screenshot_annotated",
        "description": "Screenshot with numbered element labels overlaid. Numbers match get_elements indices.",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "screenshot_cropped",
        "description": "Screenshot a specific screen region. Use to zoom into an area.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "x1": {"type": "integer"},
                "y1": {"type": "integer"},
                "x2": {"type": "integer"},
                "y2": {"type": "integer"},
            },
            "required": ["device", "x1", "y1", "x2", "y2"],
        },
    },
    {
        "name": "start_screen_recording",
        "description": "Start recording the device screen. iOS uses WDA MJPEG through ffmpeg; Android uses adb screenrecord.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "filename": {"type": "string", "description": "Optional MP4 filename."},
            },
            "required": ["device"],
        },
    },
    {
        "name": "stop_screen_recording",
        "description": "Stop a running device screen recording and return the saved MP4 path/URL.",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "screen_recording_status",
        "description": "Return active screen recording status for a device.",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "get_stream_info",
        "description": (
            "Return platform-aware stream metadata without opening the stream. "
            "iOS reports WDA MJPEG URL/settings and unsupported Portal/WebRTC actions; "
            "Android reports Portal/H264/screencap mode metadata."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "mode": {
                    "type": "string",
                    "description": "Requested mode, e.g. mjpeg, wda-mjpeg, portal, h264, screencap.",
                },
                "fps": {"type": "integer", "default": 5},
                "quality": {"type": "integer", "default": 8},
            },
            "required": ["device"],
        },
    },
    {
        "name": "get_screen_tree",
        "description": 'Get LLM-readable indented UI hierarchy. Each node: [idx] Class "label" [clickable] [bounds]. Use this to understand screen layout before acting.',
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "get_screen_xml",
        "description": "Get the raw normalized UI XML dump. Prefer get_screen_tree unless exact attributes are needed.",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "get_elements",
        "description": "Get interactive UI elements as JSON with idx, text, bounds, center. You MUST call this before tap_element; use its zero-based idx, not the numbers displayed by get_screen_tree.",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "get_phone_state",
        "description": "Get current app, activity, keyboard state. Quick check what's on screen.",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "device_health",
        "description": "Run a comprehensive device health check. On iOS, includes Appium/WDA status and recovery steps.",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "fix_device_health",
        "description": (
            "Apply a recovery action returned by device_health.recommended_fix. "
            "On iOS this can reset stale Appium/WDA sessions or restart a user-owned RemoteXPC tunnel."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "issue": {"type": "string", "description": "Recovery code from device_health.recommended_fix."},
            },
            "required": ["device", "issue"],
        },
    },
    {
        "name": "classify_screen",
        "description": "Classify screen type: home, search, profile, dialog, error, loading.",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "find_on_screen",
        "description": "Find specific text on screen, return its location. Searches XML first, OCR fallback.",
        "input_schema": {
            "type": "object",
            "properties": {"device": {"type": "string"}, "text": {"type": "string"}},
            "required": ["device", "text"],
        },
    },
    {
        "name": "ocr_screen",
        "description": "OCR the entire screen. Use when UI elements are rendered as images (analytics, games, WebViews).",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "ocr_region",
        "description": "OCR a specific screen region. More accurate for targeted text extraction.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "x1": {"type": "integer"},
                "y1": {"type": "integer"},
                "x2": {"type": "integer"},
                "y2": {"type": "integer"},
            },
            "required": ["device", "x1", "y1", "x2", "y2"],
        },
    },
    # Input
    {
        "name": "tap",
        "description": "Tap at exact pixel coordinates (x, y) on the device screen.",
        "input_schema": {
            "type": "object",
            "properties": {"device": {"type": "string"}, "x": {"type": "integer"}, "y": {"type": "integer"}},
            "required": ["device", "x", "y"],
        },
    },
    {
        "name": "tap_element",
        "description": "Tap a UI element by its index from get_elements(). Call get_elements first.",
        "input_schema": {
            "type": "object",
            "properties": {"device": {"type": "string"}, "idx": {"type": "integer"}},
            "required": ["device", "idx"],
        },
    },
    {
        "name": "swipe",
        "description": "Swipe from (x1,y1) to (x2,y2). Scroll down: swipe(540,1400,540,600).",
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "x1": {"type": "integer"},
                "y1": {"type": "integer"},
                "x2": {"type": "integer"},
                "y2": {"type": "integer"},
                "duration_ms": {"type": "integer", "default": 500},
            },
            "required": ["device", "x1", "y1", "x2", "y2"],
        },
    },
    {
        "name": "type_text",
        "description": "Type text into the currently focused input field.",
        "input_schema": {
            "type": "object",
            "properties": {"device": {"type": "string"}, "text": {"type": "string"}},
            "required": ["device", "text"],
        },
    },
    {
        "name": "type_unicode",
        "description": "Type unicode text into the focused field. Use for emoji, CJK, accented characters, and other non-ASCII input.",
        "input_schema": {
            "type": "object",
            "properties": {"device": {"type": "string"}, "text": {"type": "string"}},
            "required": ["device", "text"],
        },
    },
    {
        "name": "press_back",
        "description": "Press the platform Back/navigation-back control.",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "press_home",
        "description": "Press the platform Home button.",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "press_key",
        "description": "Press a key: BACK, HOME, ENTER, TAB, POWER, VOLUME_UP, VOLUME_DOWN, APP_SWITCH.",
        "input_schema": {
            "type": "object",
            "properties": {"device": {"type": "string"}, "key": {"type": "string"}},
            "required": ["device", "key"],
        },
    },
    {
        "name": "long_press",
        "description": "Long press at coordinates. For context menus, drag initiation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "duration_ms": {"type": "integer", "default": 1000},
            },
            "required": ["device", "x", "y"],
        },
    },
    # App management
    {
        "name": "launch_app",
        "description": (
            "Launch an app by Android package name or iOS bundle id. "
            "Use search_apps to find the package or bundle id. "
            "Set fresh=true to force-stop first (cold start, clears state Ã¢â‚¬â€ use for benchmarks "
            "or when prior app state would interfere). Default is warm start (resumes prior state)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "package": {"type": "string"},
                "fresh": {"type": "boolean", "description": "Force-stop first for a clean state. Default false."},
            },
            "required": ["device", "package"],
        },
    },
    {
        "name": "launch_intent",
        "description": "Launch a full Android intent with optional action, data URI, package/component, and extras. Android-only.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "action": {"type": "string"},
                "data": {"type": "string"},
                "package": {"type": "string"},
                "component": {"type": "string"},
                "extras": {"type": "object"},
            },
            "required": ["device"],
        },
    },
    {
        "name": "open_camera",
        "description": (
            "Open the platform camera app in a specific mode. "
            "On Android this uses launcher/UI automation; on iOS this uses the Camera bundle and WDA UI controls. "
            "Modes: 'photo' (default rear photo), 'video' (rear video), "
            "'selfie' (front photo), 'selfie_video' (front video). "
            "Set timer_s=3 or timer_s=10 to activate the self-timer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "mode": {"type": "string", "enum": ["photo", "video", "selfie", "selfie_video"], "default": "photo"},
                "timer_s": {
                    "type": "integer",
                    "enum": [0, 3, 10],
                    "description": "Self-timer delay. 0 = off.",
                    "default": 0,
                },
            },
            "required": ["device"],
        },
    },
    {
        "name": "speak_text",
        "description": (
            "Make the phone speak text aloud using its built-in TTS engine. "
            "Works from PC and on-device Ã¢â‚¬â€ always emits audio on the phone. "
            "Requires Ghost portal app to be running. "
            "Use for audio feedback, accessibility, or voice responses."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "text": {"type": "string", "description": "Text to speak aloud."},
                "rate": {
                    "type": "number",
                    "description": "Speed: 0.5=slow, 1.0=normal, 1.5=fast. Default 1.0.",
                    "default": 1.0,
                },
            },
            "required": ["device", "text"],
        },
    },
    {
        "name": "toggle_overlay",
        "description": "Toggle Portal numbered element overlay on/off. Android-only.",
        "input_schema": {
            "type": "object",
            "properties": {"device": {"type": "string"}, "visible": {"type": "boolean", "default": True}},
            "required": ["device"],
        },
    },
    {
        "name": "force_stop",
        "description": "Force-stop an app.",
   ×Í¶òÚ$z{-®éÜj×&WGW&âGV×2€Ğ¢öW‡G&7E÷f—6–&ÆU÷FW‡B€Ğ¢FWf–6RÀĞ¢Ö…öÆ–æW3Ö–çB†&w2ævWB‚&Ö…öÆ–æW2"Â#’’ÀĞ¢–æ6ÇVFUö6öçG&öÇ3Ö&ööÂ†&w2ævWB‚&–æ6ÇVFUö6öçG&öÇ2"ÂfÇ6R’’ÀĞ¢Ğ¢Ğ¢VÆ–bæÖRÓÒ&W‡G&7Eö'F–6ÆW2# Ğ¢g&öÒv—FBç6W'f–6W2æ'&÷w6W"–×÷'BGV×0Ğ¢g&öÒv—FBç6W'f–6W2æ'&÷w6W"–×÷'BW‡G&7Eö'F–6ÆW22öW‡G&7Eö'F–6ÆW0Ğ Ğ¢&WGW&âGV×2…öW‡G&7Eö'F–6ÆW2†FWf–6RÂÖ…ö—FV×3Ö–çB†&w2ævWB‚&Ö…ö—FV×2"ÂR’’’Ğ¢VÆ–bæÖRÓÒ'&VEöæWw2# Ğ¢g&öÒv—FBç6W'f–6W2æ'&÷w6W"–×÷'BGV×0Ğ¢g&öÒv—FBç6W'f–6W2æ'&÷w6W"–×÷'B&VEöæWw22÷&VEöæWw0Ğ Ğ¢&WGW&âGV×2€Ğ¢÷&VEöæWw2€Ğ¢FWf–6RÀĞ¢&w2ævWB‚'W&Â"Â&‡GG3¢ò÷FW‡Bæç"æ÷&rò"’ÀĞ¢Ö…ö†VFÆ–æW3Ö–çB†&w2ævWB‚&Ö…ö†VFÆ–æW2"ÂR’’ÀĞ¢Ö…ö'F–6ÆW3Ö–çB†&w2ævWB‚&Ö…ö'F–6ÆW2"Â2’’ÀĞ¢'VæFÆUö–CÖ&w2ævWB‚&'VæFÆUö–B"’÷"æöæRÀĞ¢v—E÷3ÖfÆöB†&w2ævWB‚'v—E÷2"Â"ã’’ÀĞ¢6fU÷67&VVç6†÷G3Ö&ööÂ†&w2ævWB‚'6fU÷67&VVç6†÷G2"ÂfÇ6R’’ÀĞ¢Ğ¢Ğ¢VÆ–bæÖRÓÒ&Æ—7Eö2"÷"æÖRÓÒ'6V&6…ö2# Ğ¢VW'’Ò&w2ævWB‚'VW'’"Â""’–bæÖRÓÒ'6V&6…ö2"VÇ6R" Ğ¢&WGW&â§6öâæGV×2†7G‚æÆ—7Eö2†FWf–6RÂVW'“×VW'’’Â–æFVçCÓ"Ğ¢VÆ–bæÖRÓÒ&Æ—7E÷6¶vW2# Ğ¢&WGW&â§6öâæGV×2†7G‚æÆ—7E÷6¶vW2†FWf–6R•³£SÒÂ–æFVçCÓ"Ğ¢VÆ–bæÖRÓÒ&W‡Æ÷&Uö# Ğ¢g&öÒF†Æ–"–×÷'BF€Ğ Ğ¢6¶vRÒ&w5²'6¶vR%ĞĞ¢67&—BÒF‚…õöf–ÆUõò’ç&W6öÇfR‚’ç&VçG5³Òò'6¶–ÆÇ2"ò&WFõö7&VF÷"ç’ Ğ¢&ö¦V7EöF—"ÒF‚…õöf–ÆUõò’ç&W6öÇfR‚’ç&VçG5³%ĞĞ¢Ö…öFWF‚Ò–çB†&w2ævWB‚&Ö…öFWF‚"Â"’Ğ¢Ö…÷7FFW2Ò–çB†&w2ævWB‚&Ö…÷7FFW2"Â’Ğ¢&W7VÇBÒ7V'&ö6W72ç'Vâ€Ğ¢°Ğ¢7—2æW†V7WF&ÆRÀĞ¢"×R"ÀĞ¢7G"‡67&—B’ÀĞ¢"Ò×6¶vR"ÀĞ¢6¶vRÀĞ¢"ÒÖFWf–6R"ÀĞ¢FWf–6RÀĞ¢"ÒÖÖ‚ÖFWF‚"ÀĞ¢7G"†Ö…öFWF‚’ÀĞ¢"ÒÖÖ‚×7FFW2"ÀĞ¢7G"†Ö…÷7FFW2’ÀĞ¢ÒÀĞ¢6GW&Uö÷WGWCÕG'VRÀĞ¢FW‡CÕG'VRÀĞ¢F–ÖV÷WCÓ3ÀĞ¢7vC×7G"‡&ö¦V7EöF—"’ÀĞ¢Ğ¢w&…÷F‚Ò&ö¦V7EöF—"ò&FF"ò&öW‡Æ÷&W""ò6¶vRò'7FFUöw&‚æ§6öâ Ğ¢–bw&…÷F‚æW†—7G2‚“ Ğ¢&WGW&âw&…÷F‚ç&VE÷FW‡B‚•³£ĞĞ¢÷WGWBÒ&W7VÇBç7FF÷WE²Ó¥ĞĞ¢–b&W7VÇBç&WGW&æ6öFRÒæB&W7VÇBç7FFW'# Ğ¢÷WGWB³Òb%Æå5DDU%#¥Æç·&W7VÇBç7FFW'%²Ó¥×Ò Ğ¢&WGW&âb$W‡Æ÷&F–öâf–æ—6†VBâ÷WGWC¥Æç¶÷WGWGÒ Ğ¢VÆ–bæÖRÓÒ'6†VÆÂ# Ğ¢÷WBÒFWf–6R†FWf–6R’æF"‚'6†VÆÂ"Â¦&w5²&6öÖÖæB%Òç7Æ—B‚’ÂF–ÖV÷WCÓRĞ¢&WGW&â÷WE³£3ĞĞ¢VÆ–bæÖRÓÒ'7FU÷FW‡B# Ğ¢–b—5ö–÷5÷&Vb†FWf–6R“ Ğ¢vWEöFWf–6R†FWf–6R’ç7FU÷FW‡B†&w5²'FW‡B%ÒĞ¢BÒ&w5²'FW‡B%ĞĞ¢&WGW&âb$–ç6W'FVBFW‡Böâ”õ3¢·E³£c××²râââr–bÆVâ‡B’âcVÇ6RrwÒ Ğ¢g&öÒv—FBæ&÷G2æ6öÖÖöâæF"–×÷'BFWf–6R2ôFW`Ğ Ğ¢7G‚æ6Æ—&ö&E÷6WB†FWf–6RÂ&w5²'FW‡B%ÒĞ¢ôFWb†FWf–6R’æF"‚'6†VÆÂ"Â&–çWB"Â&¶W–WfVçB"Â$´U”4ôDUõ5DR"Ğ¢BÒ&w5²'FW‡B%ĞĞ¢&WGW&âb%7FVC¢·E³£c××²|:.(*Ì*br–bÆVâ‡B’âcVÇ6RrwÒ Ğ¢VÆ–bæÖRÓÒ&6Æ—&ö&EövWB# Ğ¢&WGW&â7G‚æ6Æ—&ö&EövWB†FWf–6R’÷""†V×G’’ Ğ¢VÆ–bæÖRÓÒ&6Æ—&ö&E÷6WB# Ğ¢7G‚æ6Æ—&ö&E÷6WB†FWf–6RÂ&w5²'FW‡B%ÒĞ¢&WGW&â$6Æ—&ö&B6WB Ğ¢VÆ–bæÖRÓÒ&vWEöæ÷F–f–6F–öç2# Ğ¢&WGW&â§6öâæGV×2†7G‚ævWEöæ÷F–f–6F–öç2†FWf–6R’Â–æFVçCÓ"Ğ¢VÆ–bæÖRÓÒ&÷Våöæ÷F–f–6F–öç2# Ğ¢–bæ÷B7G‚æ÷Våöæ÷F–f–6F–öç2†FWf–6R“ Ğ¢&WGW&â$f–ÆVB Ğ¢&WGW&â$æ÷F–f–6F–öâ6VçFW"÷VæVB"–b—5ö–÷5÷&Vb†FWf–6R’VÇ6R$æ÷F–f–6F–öâ6†FR÷VæVB Ğ¢VÆ–bæÖRÓÒ&6ÆV%öæ÷F–f–6F–öç2# Ğ¢&WGW&â$æ÷F–f–6F–öç26ÆV&VB"–b7G‚æ6ÆV%öæ÷F–f–6F–öç2†FWf–6R’VÇ6R$f–ÆVB Ğ¢VÆ–bæÖRÓÒ&Æ—7E÷6¶–ÆÇ2# Ğ¢g&öÒv—FBç&÷WFW'2ç6¶–ÆÇ2–×÷'BöÆöEöÆÅ÷6¶–ÆÇ2ÂöÆöE÷6¶–ÆÀĞ Ğ¢6¶–ÆÇ2ÒöÆöEöÆÅ÷6¶–ÆÇ2‚Ğ¢&W7VÇBÒµĞĞ¢F&vWEöFWf–6RÒ&w2ævWB‚&FWf–6R"’÷"FWf–6PĞ¢7W÷'FVEööæÇ’Ò&ööÂ†&w2ævWB‚'7W÷'FVEööæÇ’"’Ğ¢f÷"6æÖRÂ–æfò–â6¶–ÆÇ2æ—FV×2‚“ Ğ¢7W÷'FVBÒ6¶–ÆÅ÷7W÷'G5öFWf–6R†–æfòævWB‚&ÖWFFF"’÷"·ÒÂF&vWEöFWf–6R’–bF&vWEöFWf–6RVÇ6RæöæPĞ¢–b7W÷'FVEööæÇ’æB7W÷'FVB—2fÇ6S Ğ¢6öçF–çVPĞ¢2ÒöÆöE÷6¶–ÆÂ‡6æÖRĞ¢VçG'’Ò°Ğ¢&æÖR#¢–æfõ²&æÖR%ÒÀĞ¢&FW67&—F–öâ#¢–æfòævWB‚&FW67&—F–öâ"Â""’ÀĞ¢&¶–æB#¢–æfòævWB‚&¶–æB"Â&†&B"’ÀĞ¢&wV–Fæ6Uöf–Æ&ÆR#¢–æfòævWB‚&†5öwV–Fæ6R"ÂfÇ6R’ÀĞ¢&÷6¶vR#¢–æfòævWB‚&÷6¶vR"Â""’ÀĞ¢&æG&ö–E÷6¶vR#¢–æfòævWB‚&æG&ö–E÷6¶vR"Â""’ÀĞ¢&–÷5ö'VæFÆUö–B#¢–æfòævWB‚&–÷5ö'VæFÆUö–B"Â""’ÀĞ¢'ÆFf÷&×2#¢–æfòævWB‚'ÆFf÷&×2"ÂµÒ’ÀĞ¢'7W÷'G5öæG&ö–B#¢–æfòævWB‚'7W÷'G5öæG&ö–B"ÂfÇ6R’ÀĞ¢'7W÷'G5ö–÷2#¢–æfòævWB‚'7W÷'G5ö–÷2"ÂfÇ6R’ÀĞ¢'ÆFf÷&ÕöÆ–Ö—FF–öç2#¢–æfòævWB‚'ÆFf÷&ÕöÆ–Ö—FF–öç2"Â·Ò’ÀĞ¢&FVfVÇE÷&×2#¢–æfòævWB‚&FVfVÇE÷&×2"Â·Ò’ÀĞ¢ĞĞ¢–b7W÷'FVB—2æ÷BæöæS Ğ¢VçG'•²'7W÷'FVEööåöFWf–6R%ÒÒ7W÷'FV@Ğ¢–b2æBæ÷B—6–ç7Fæ6R‡2ÂF–7B“ Ğ¢VçG'•²'v÷&¶fÆ÷w2%ÒÒ2æÆ—7E÷v÷&¶fÆ÷w2‚Ğ¢VçG'•²&7F–öç2%ÒÒ2æÆ—7Eö7F–öç2‚Ğ¢&W7VÇBæVæB†VçG'’Ğ¢&WGW&â§6öâæGV×2‡&W7VÇBÂ–æFVçCÓ"Ğ¢VÆ–bæÖR–â²''Vå÷6¶–ÆÂ"Â''Vå÷v÷&¶fÆ÷r"Â''Våö7F–öâ'Ó Ğ¢g&öÒv—FBç&÷WFW'2ç6¶–ÆÇ2–×÷'BöÆöEöÆÅ÷6¶–ÆÇ0Ğ Ğ¢6¶–ÆÇ2ÒöÆöEöÆÅ÷6¶–ÆÇ2‚Ğ¢6¶–ÆÅö–æfòÒ6¶–ÆÇ2ævWB†&w5²'6¶–ÆÂ%ÒĞ¢–b6¶–ÆÅö–æfòæBæ÷B6¶–ÆÅ÷7W÷'G5öFWf–6R‡6¶–ÆÅö–æfòævWB‚&ÖWFFF"’÷"·ÒÂFWf–6R“ Ğ¢&WGW&â6¶–ÆÅ÷ÆFf÷&ÕöW'&÷%÷FW‡B†&w5²'6¶–ÆÂ%ÒÂ6¶–ÆÅö–æfòævWB‚&ÖWFFF"’÷"·ÒÂFWf–6RĞ¢24ôeB6¶–ÆÇ26''’wV–Fæ6RÂæ÷B'Vææ&ÆR7FW2:.(*Î(	Ò&WGW&âF†RFW‡BöâFVÖæBàĞ¢–b6¶–ÆÅö–æfòæB6¶–ÆÅö–æfòævWB‚&¶–æB"’ÓÒ'6ögB# Ğ¢g&öÒv—FBç&÷WFW'2ç6¶–ÆÇ2–×÷'Bõ4´”ÄÅ5ôD• Ğ Ğ¢wF‚Òõ4´”ÄÅ5ôD•"ò&w5²'6¶–ÆÂ%Òò&wV–Fæ6RæÖB Ğ¢–bwF‚æW†—7G2‚“ Ğ¢&WGW&âb%·6ögB6¶–ÆÂw¶&w5²w6¶–ÆÂu×Òr:.(*Î(	ÒwV–Fæ6UÕÆåÆç¶wF‚ç&VE÷FW‡B‚—Ò Ğ¢&WGW&âb%6ögB6¶–ÆÂw¶&w5²w6¶–ÆÂu×Òr†2æòwV–Fæ6RFW‡Bâ Ğ¢'VææW"Òõö–×÷'Eõò‚'F†Æ–""’åF‚…õöf–ÆUõò’ç&VçBç&VçBò'6¶–ÆÇ2"ò%÷'Vå÷6¶–ÆÂç’ Ğ¢&×2Ò§6öâæGV×2†&w2ævWB‚'&×2"Â·Ò’Ğ¢ÖöFUö&rÒ"ÒÖ7F–öâ"–bæÖRÓÒ''Våö7F–öâ"VÇ6R"Ò×v÷&¶fÆ÷r Ğ¢F&vWBÒ&w5²&7F–öâ%Ò–bæÖRÓÒ''Våö7F–öâ"VÇ6R&w5²'v÷&¶fÆ÷r%ĞĞ¢"Ò7V'&ö6W72ç'Vâ€Ğ¢°Ğ¢7—2æW†V7WF&ÆRÀĞ¢"×R"ÀĞ¢7G"‡'VææW"’ÀĞ¢"Ò×6¶–ÆÂ"ÀĞ¢&w5²'6¶–ÆÂ%ÒÀĞ¢ÖöFUö&rÀĞ¢F&vWBÀĞ¢"ÒÖFWf–6R"ÀĞ¢FWf–6RÀĞ¢"Ò×&×2"ÀĞ¢&×2ÀĞ¢ÒÀĞ¢6GW&Uö÷WGWCÕG'VRÀĞ¢FW‡CÕG'VRÀĞ¢F–ÖV÷WCÓ#ÀĞ¢7vC×7G"…õö–×÷'Eõò‚'F†Æ–""’åF‚…õöf–ÆUõò’ç&VçBç&VçBç&VçB’ÀĞ¢Ğ¢&WGW&â"ç7FF÷WE²Ó#¥Ò–b"ç&WGW&æ6öFRÓÒVÇ6Rb$d”ÄTC¢·"ç7FF÷WE²Ó¥×ÕÆç·"ç7FFW'%²ÓS¥×Ò Ğ¢VÆ–bæÖRÓÒ&7&VFU÷6¶–ÆÂ# Ğ¢g&öÒv—FBç6W'f–6W2ç6¶–ÆÅö7&VF–öâ–×÷'B7&VFU÷&V6÷&FVE÷6¶–ÆÀĞ Ğ¢&W7VÇBÒ7&VFU÷&V6÷&FVE÷6¶–ÆÂ€Ğ¢æÖSÖ&w5²&æÖR%ÒÀĞ¢÷6¶vSÖ&w2ævWB‚&÷6¶vR"Â""’ÀĞ¢7FW3Ö&w2ævWB‚'7FW2"ÂµÒ’ÀĞ¢ÆFf÷&×3Ö&w2ævWB‚'ÆFf÷&×2"ÂµÒ’ÀĞ¢–÷5ö'VæFÆUö–CÖ&w2ævWB‚&–÷5ö'VæFÆUö–B"Â""’ÀĞ¢VÆVÖVçG5ö–÷3Ö&w2ævWB‚&VÆVÖVçG5ö–÷2"’–b&VÆVÖVçG5ö–÷2"–â&w2VÇ6RæöæRÀĞ¢VÆVÖVçG5öæG&ö–CÖ&w2ævWB‚&VÆVÖVçG5öæG&ö–B"’–b&VÆVÖVçG5öæG&ö–B"–â&w2VÇ6RæöæRÀĞ¢Ğ¢&WGW&â§6öâæGV×2€Ğ¢°Ğ¢&ö²#¢G'VRÀĞ¢'6¶–ÆÂ#¢&W7VÇE²'6¶–ÆÂ%ÒÀĞ¢'7FW2#¢&W7VÇE²'7FW2%ÒÀĞ¢&F—"#¢&W7VÇE²&F—"%ÒÀĞ¢'ÆFf÷&×2#¢&W7VÇE²'ÆFf÷&×2%ÒÀĞ¢&ÖWFFF#¢&W7VÇE²&ÖWFFF%ÒÀĞ¢ÒÀĞ¢–æFVçCÓ"ÀĞ¢Ğ¢VÆ–bæÖRÓÒ&Æöö·WöÆVB# Ğ¢g&öÒv—FBç6W'f–6W2æÖ&¶WF–æuöÆöö·W–×÷'BÆöö·WöÆV@Ğ Ğ¢&WGW&âÆöö·WöÆVB†&w5²&†æFÆR%ÒĞ¢VÆ–bæÖRÓÒ&Æ—7E÷Vç&VEöÆVG2# Ğ¢g&öÒv—FBç6W'f–6W2æÖ&¶WF–æuöÆöö·W–×÷'BÆ—7E÷Vç&VEöÆVG0Ğ Ğ¢&WGW&âÆ—7E÷Vç&VEöÆVG2‚Ğ¢VÆ–bæÖRÓÒ&7&ÕöÆöö·Wö6öçF7B# Ğ¢g&öÒv—FBç6W'f–6W2æ7&ÕöÆöö·W–×÷'B7&ÕöÆöö·Wö6öçF7@Ğ Ğ¢&WGW&â7&ÕöÆöö·Wö6öçF7B†&w5²&†æFÆR%ÒĞ¢VÆ–bæÖRÓÒ&7&ÕöÆ—7E÷Vç&VEöÖW76vW2# Ğ¢g&öÒv—FBç6W'f–6W2æ7&ÕöÆöö·W–×÷'B7&ÕöÆ—7E÷Vç&VEöÖW76vW0Ğ Ğ¢&WGW&â7&ÕöÆ—7E÷Vç&VEöÖW76vW2‚Ğ¢VÆ–bæÖRÓÒ'67&VVç6†÷E÷6WVVæ6R# Ğ¢&WGW&âö6GW&U÷6WVVæ6R†FWf–6RÂ&w2Ğ¢VÆ–bæÖRÓÒ'7V%övVçB# Ğ¢&WGW&â÷'Vå÷7V%övVçE÷FööÂ†FWf–6RÂ&w2Ğ¢VÆ–bæÖRÓÒ'v—B# Ğ¢F–ÖRç6ÆVW†&w2ævWB‚'6V6öæG2"Â"’Ğ¢&WGW&âb%v—FVB¶&w2ævWB‚w6V6öæG2rÂ"—×2 Ğ¢VÆ–bæÖRÓÒ&6†–â# Ğ¢&WGW&âöW†V7WFUö6†–â†FWf–6RÂ&w2Ğ¢VÇ6S Ğ¢&WGW&âb%Væ¶æ÷vâFööÃ¢¶æÖWÒ Ğ¢W†6WBW†6WF–öâ2S Ğ¢&WGW&âb$W'&÷#¢¶WÒ Ğ Ğ Ğ¢26öâ7V"Ö7F–öç2W"6†–â:.(*Î(	Ò&F6‚F†B&–r—2ÆÖ÷7B6W'F–æÇ’Ğ¢2'Væv“²&÷VæB—B6òöæR6†–â6ÆÂ6âwBÖöæ÷öÆ—6RF†RFWf–6RàĞ¥ô4„”åôÔ…ô5D”ôå2ÒPĞ¥ô4„”åôÔ…ôDTÄ•õ2Ò2ã Ğ¥ô4„”åõ5D$”Ä•¤Uõ2Òã`Ğ Ğ Ğ¦FVböW†V7WFUö6†–â†FWf–6S¢7G"Â&w3¢F–7B’Óâ7G# Ğ¢""%'Vâ6WVVæ6Röb7V"Ö7F–öç2–âöæR7FWÂ6WGFÆ–ær&WGvVVâV6‚àĞ Ğ¢f–ÂÖ6Æ÷6VBÆ–¶R'VåöfÆ÷s¢WfW'’7V"Ö7F–öâw2FööÂ×W7B&RöàĞ¢4dUôDUd”4UõDôôÅ2ÂæB6†–âÖ’æ÷BæW7Bæ÷F†W"6†–â:.(*Î(	Ò&F6‚—0Ğ¢W†7FÇ’v†W&Râ–æ¦V7FVB–ç7G'V7F–öâv÷VÆBG'’Fò6×VvvÆRâW†V2FööÂÂ6ğĞ¢F†Rv†öÆR6†–â—2&VgW6VB&Vf÷&Rç’7V"Ö7F–öâ'Vç2–bç’7FWæÖW2Ğ¢æöâÖÆÆ÷vVBFööÂâ7V"Ö7F–öç2F—7F6‚f–öW†V7WFU÷FööÅö–ææW"†æğĞ¢W"Ö7F–öâ67&VVâ×G&VRVæB“²vR6WGFÆR&WGvVVâF†VÒ–ç7FVBàĞ¢"" Ğ¢–×÷'BF–ÖPĞ Ğ¢7V'2Ò&w2ævWB‚&7F–öç2"Ğ¢–bæ÷B—6–ç7Fæ6R‡7V'2ÂÆ—7B’÷"æ÷B7V'3 Ğ¢&WGW&â&6†–ã¢v7F–öç2r×W7B&RæöâÖV×G’Æ—7Böb·FööÂÂ&w7Ò Ğ¢–bÆVâ‡7V'2’âô4„”åôÔ…ô5D”ôå3 Ğ¢&WGW&âb&6†–ã¢FöòÖç’7F–öç2‡¶ÆVâ‡7V'2—Òâµô4„”åôÔ…ô5D”ôå7Ò’ Ğ Ğ¢2fÆ–FFRF†Rt„ôÄR&F6‚&Vf÷&R'Vææ–ærå’öb—BÂ6ò6†–âF†B†–FW2Ğ¢2F—6ÆÆ÷vVB7F–öâgFW"6öÖR&Væ–vâ7FW2W†V7WFW2æ÷F†–æràĞ¢f÷"’Â7V"–âVçVÖW&FR‡7V'2“ Ğ¢–bæ÷B—6–ç7Fæ6R‡7V"ÂF–7B’÷"'FööÂ"æ÷B–â7V# Ğ¢&WGW&âb&6†–ã¢7FW¶—Ò×W7B&Râö&¦V7Bv—F‚wFööÂrf–VÆB Ğ¢FööÂÒ7V%²'FööÂ%ĞĞ¢–bFööÂÓÒ&6†–â# Ğ¢&WGW&âb&6†–ã¢7FW¶—ÒÖ’æ÷BæW7Bæ÷F†W"6†–â Ğ¢–bFööÂæ÷B–â4dUôDUd”4UõDôôÅ3 Ğ¢&WGW&âb&6†–ã¢7FW¶—ÒFööÂw·FööÇÒr—2æ÷BÆÆ÷vVB–ç6–FR6†–â†öæÇ’&VBõT’FööÇ2’ Ğ Ğ¢6WGFÆRÒ&w2ævWB‚'6WGFÆR"Â'7F&–Æ—¦R"Ğ¢FVÆ•÷2ÒÖ–â†Ö‚†–çB†&w2ævWB‚&FVÆ•ö×2"Âc’’Â’òÂô4„”åôÔ…ôDTÄ•õ2Ğ Ğ¢–æf÷3¢Æ—7E·7G%ÒÒµĞĞ¢f÷"’Â7V"–âVçVÖW&FR‡7V'2“ Ğ¢FööÂÒ7V%²'FööÂ%ĞĞ¢7V%ö&w2ÒF–7B‡7V"ævWB‚&&w2"’÷"·ÒĞ¢7V%ö&w2ç6WFFVfVÇB‚&FWf–6R"ÂFWf–6RĞ¢G'“ Ğ¢÷WBÒöW†V7WFU÷FööÅö–ææW"‡FööÂÂ7V%ö&w2Ğ¢–æf÷2æVæB†b'·FööÇÓ¢·7G"†÷WB•³£ƒ×Ò"Ğ¢W†6WBW†6WF–öâ2S Ğ¢–æf÷2æVæB†b'·FööÇÓ¢W'#§¶WÒ"Ğ¢'&V²2&÷'BF†R&W7BöbF†R6†–âöâF†Rf—'7B†&Bf–ÇW&PĞ¢–b’ÂÆVâ‡7V'2’Ò Ğ¢F–ÖRç6ÆVW†FVÆ•÷2–b6WGFÆRÓÒ&FVÆ’"VÇ6Rô4„”åõ5D$”Ä•¤Uõ2Ğ Ğ¢&WGW&âb&6†–å·¶ÆVâ†–æf÷2—Ò÷¶ÆVâ‡7V'2—ÕÓ¢"²"â"æ¦ö–â†–æf÷2Ğ Ğ Ğ¢2W"ÖFWf–6R'W'7Böbg&ÖW26GW&VB'’67&VVç6†÷E÷6WVVæ6RÂ&VB'’7V%övVçBàĞ¢2ÖöGVÆRÖÆWfVÂ6ò—B7W'f—fW27&÷72FööÂ6ÆÇ2†æBv÷&·2–ç6–FR6†–â7FW’àĞ¥õ4Uôe$ÔU3¢F–7E·7G"ÂÆ—7E·7G%ÕÒÒ·ĞĞ Ğ¥õ4UôÔ…ôEU$D”ôåõ2Òƒ Ğ¥õ4UôÔ…ôe2ÒBã Ğ Ğ Ğ¦FVbö6GW&U÷6WVVæ6R†FWf–6S¢7G"Â&w3¢F–7B’Óâ7G# Ğ¢""%öÆÂW"Ög&ÖR67&VVç6†÷G2÷fW"v–æF÷rÂ66†–ærF†VÒf÷"7V%övVçBàĞ Ğ¢W6W2F†Ræ÷&ÖÂ67&VVç6†÷BF‚‡67&VVæ6öâæG&ö–BòtDöâ”õ2’&F†W"F†àĞ¢f–FVò&V6÷&FW#¢&V6÷&FW"6âg&VW¦RöâÆ––ær7W&f6Uf–WrÂ'WBW"Ög&ÖPĞ¢67&VVç6†÷G26GW&RÆ––ær6öçFVçBf–æRâg&ÖW2&R66†VB„äõB&WGW&æVB’6ğĞ¢F†W’æWfW"&ÆöBF†RÖ7FW"vVçBw26öçFW‡B:.(*Î(	Ò7V%övVçB&VG2F†VÒàĞ¢"" Ğ¢–×÷'BF–ÖR2÷@Ğ Ğ¢GW"ÒÖ‚ƒ"ÂÖ–â†–çB†&w2ævWB‚&GW&F–öå÷6V6öæG2"Â&w2ævWB‚'6V6öæG2"ÂB’’’Âõ4UôÔ…ôEU$D”ôåõ2’Ğ¢g2ÒÖ‚ƒãÂÖ–â†fÆöB†&w2ævWB‚&g2"Âã’’Âõ4UôÔ…ôe2’Ğ¢–çFW'fÂÒãòg0Ğ¢âÒÖ‚ƒÂ–çB†GW"¢g2’Ğ¢g&ÖW3¢Æ—7E·7G%ÒÒµĞĞ¢f÷"’–â&ævR†â“ Ğ¢6†÷BÒvWE÷67&VVç6†÷Eö#cB†FWf–6RĞ¢–b6†÷C Ğ¢g&ÖW2æVæB‡6†÷BĞ¢–b’ÂâÒ Ğ¢÷Bç6ÆVW†–çFW'fÂĞ¢õ4Uôe$ÔU5¶FWf–6UÒÒg&ÖW0Ğ¢&WGW&âb'67&VVç6†÷E÷6WVVæ6S¢6GW&VB¶ÆVâ†g&ÖW2—Òg&ÖW2÷fW"¶GW'×2¶g7Ög2†66†VBf÷"7V%övVçB’ Ğ Ğ Ğ¦FVb÷'Vå÷7V%övVçE÷FööÂ†FWf–6S¢7G"Â&w3¢F–7B’Óâ7G# Ğ¢""$†æBF†R66†VBg&ÖW2f÷"F†—2FWf–6RFòF†Rf—6–öâ7V"ÖvVçC²&WGW&â—G2FW‡Bâ"" Ğ¢g&öÒv—FBç6W'f–6W2ç7V%övVçB–×÷'B'Vå÷7V%övVç@Ğ Ğ¢F6²Ò&w2ævWB‚'F6²"Â""’÷"&w2ævWB‚'&ö×B"Â""Ğ¢g&ÖW2Òõ4Uôe$ÔU2ævWB†FWf–6R’÷"µĞĞ¢&W7VÇBÒ'Vå÷7V%övVçB‡F6²Âg&ÖW2ÂÖ…ög&ÖW3Ö–çB†&w2ævWB‚&Ö…ög&ÖW2"Âc’’Ğ¢–bg&ÖW2æBæ÷B&W7VÇBç7F'G7v—F‚‚‚'7V%övVçB"Â%5T%ôtTåB"’“ Ğ¢&WGW&âb%5T%ôtTåB$U5TÅB‡¶ÆVâ†g&ÖW2—Òg&ÖW2“¢·&W7VÇGÒ Ğ¢&WGW&â&W7VÇ@Ğ Ğ Ğ¦FVbvWE÷67&VVç6†÷Eö#cB†FWf–6S¢7G"’Óâ7G"ÂæöæS Ğ¢""$vWB&r&6ScB67&VVç6†÷Bf÷"f—6–öâ6öçFW‡B–æ¦V7F–öââ"" Ğ¢G'“ Ğ¢"Ò7G‚ç67&VVç6†÷B†FWf–6RĞ¢&WGW&â"ævWB‚&–ÖvR"Ğ¢W†6WBW†6WF–öã Ğ¢&WGW&âæöæPĞ