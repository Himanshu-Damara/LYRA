"""Agent chat service Ã¢â‚¬â€ manages sessions, runs the agent loop with tool execution.

Supports multiple LLM providers:
  - claude-code: Free, local, uses `claude` CLI (default)
  - anthropic: Claude API with native tool_use
  - openrouter: Any model via OpenRouter
  - grok: Normal text chat via the Groq OpenAI-compatible API
  - ollama: Local models
"""

import json
import logging
import os
import re
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from gitd.bots.common.device import is_ios_ref
from gitd.services.agent_tools import execute_tool, get_screenshot_b64, tool_prompt_list, tools_for_device
from gitd.services.device_context import get_phone_state, get_screen_tree
from gitd.services.llm_backoff import backoff_stream, effort_timeout

log = logging.getLogger(__name__)

DEFAULT_SYSTEM = """You are a mobile automation agent with full control over one connected mobile device.

You can see the screen (via screenshots and UI tree), interact with it (tap, swipe, type),
launch and control apps, navigate browser pages, and execute automation skills.

## Available tools:
{tool_list}

## How to use tools:
To call a tool, output a JSON block like this:
```tool
{{"tool": "tool_name", "args": {{"param": "value"}}}}
```

You can call multiple tools in sequence. After each tool call, I'll show you the result.

## Standard App Packages:
- WhatsApp: "com.whatsapp"
- Instagram: "com.instagram.android"
- Gmail: "com.google.android.gm"
- Chrome: "com.android.chrome"
- YouTube: "com.google.android.youtube"
- Maps: "com.google.android.apps.maps"
- Clock: "com.google.android.deskclock" (or "com.sec.android.app.clockpackage")
- Settings: "com.android.settings"
- Calculator: "com.google.android.calculator"

## Standard Workflows:

### WhatsApp - Sending a Message
Do NOT assume the contact is visible. Use the search flow:
1. launch_app with package "com.whatsapp"
2. Call get_screen_tree to find the Search button/input.
3. Tap on the search button, then type_text with contact name (e.g. "vansh cu").
4. Call get_screen_tree, tap on the matching contact name in the list.
5. type_text the message body.
6. Tap the "Send" button.

### Instagram - Liking the First Post
1. launch_app with package "com.instagram.android"
2. Call get_elements and find the current post's clickable element whose text/content description contains "Like" (not "Unlike").
3. Tap using the zero-based idx returned by get_elements; never use a number from get_screen_tree.
4. Call get_elements again and verify that the control changed to "Unlike" or shows the liked state.

## Guidelines:
- Always use get_screen_tree first to understand what's on screen before any tap
- Call get_elements before tap_element and use its JSON `idx`; get_screen_tree numbers are display-only and must not be passed to tap_element.
- After actions, verify results with get_screen_tree
- Use only the tools listed above; unavailable platform-specific tools have been filtered out
- Keep responses concise"""

ANTHROPIC_SYSTEM = """You are a mobile automation agent with full control over one connected mobile device.

You can see the screen (via screenshots and UI tree), interact with it (tap, swipe, type),
launch and control apps, navigate browser pages, and execute automation skills.

Guidelines:
- Always use get_screen_tree first to understand what's on screen before tapping
- Call get_elements before tap_element and use its JSON `idx`; get_screen_tree numbers are display-only and must not be passed to tap_element.
- After performing actions, use get_screen_tree to verify the result
- Use only the tools exposed for the current device platform
- Keep responses concise Ã¢â‚¬â€ show what you did and the result"""

MAX_TURNS = 24

PROVIDERS = {
    "claude-code": {"label": "Claude Code (free)", "models": ["sonnet", "opus", "haiku"]},
    "anthropic": {"label": "Claude API", "models": ["claude-sonnet-4-20250514", "claude-opus-4-20250514"]},
    "openrouter": {"label": "OpenRouter", "models": ["anthropic/claude-sonnet-4", "google/gemini-2.5-pro"]},
    "grok": {"label": "Grok chat (Groq API)", "models": ["grok-beta"]},
    "ollama": {
        "label": "Ollama (local)",
        "models": [
            "qwen3:8b",
            "llama3.2:3b",
            "llama3.2:1b",
            "gemma3:4b",
            "qwen3:4b",
            "phi4-mini:3.8b",
            "mistral:7b",
        ],
    },
    # On-device Ã¢â‚¬â€ runs the model in-process via MediaPipe (.task) or
    # llama.cpp JNI (.gguf). The Kotlin OnDeviceModelRegistry is the source of
    # truth for ids; we ship a default subset here and overlay live ids below.
    "on-device": {
        "label": "On-device (Gemma)",
        "models": ["gemma-3-1b-it", "gemma-2-2b-it", "gemma-4-e2b-q4km-gguf"],
    },
    # vLLM Ã¢â‚¬â€ full-precision Gemma 4 served from the GPU box,
    # routed via Mac SSH tunnel + adb reverse so the phone hits it as if it
    # were on localhost. Same OpenAI-compatible shape as openrouter; we just
    # point the client at config.vllm_base_url instead.
    "vllm": {
        "label": "vLLM (remote GPU)",
        "models": [
            "unsloth/gemma-4-E2B-it",
            "unsloth/gemma-4-E2B-it-bnb-4bit",
            "unsloth/gemma-4-E4B-it",
            "unsloth/gemma-4-E4B-it-bnb-4bit",
        ],
    },
}


@dataclass
class ChatMessage:
    role: str
    content: str
    tool_name: str = ""
    tool_args: dict = field(default_factory=dict)
    tool_id: str = ""
    image_b64: str = ""


@dataclass
class ChatSession:
    id: str
    device: str
    provider: str = "claude-code"
    model: str = "sonnet"
    messages: list = field(default_factory=list)
    api_messages: list = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    auto_screenshot: bool = True


_sessions: dict[str, ChatSession] = {}
_active_procs: dict[str, subprocess.Popen] = {}  # session_id -> running subprocess
_active_device_turns: dict[str, str] = {}  # device -> session_id
_stop_requested: set[str] = set()


def claim_device_turn(device: str, session_id: str) -> bool:
    """Allow only one live agent turn per phone.

    This protects the phone and the local LLM from duplicate requests caused
    by multiple browser tabs or repeated clicks while a turn is still running.
    """
    active = _active_device_turns.get(device)
    if active:
        return False
    _active_device_turns[device] = session_id
    return True


def release_device_turn(device: str, session_id: str) -> None:
    if _active_device_turns.get(device) == session_id:
        _active_device_turns.pop(device, None)


def stop_device_turn(device: str) -> str | None:
    """Stop the task currently controlling a device, regardless of tab/session."""
    session_id = _active_device_turns.get(device)
    if session_id:
        stop_agent(session_id)
    return session_id


def request_stop(session_id: str) -> None:
    _stop_requested.add(session_id)


def stop_requested(session_id: str) -> bool:
    return session_id in _stop_requested


def clear_stop_request(session_id: str) -> None:
    _stop_requested.discard(session_id)


def platform_context(device: str) -> str:
    if is_ios_ref(device):
        return (
            "Target platform: iOS via Appium/WebDriverAgent. Device refs look like ios:<udid>. "
            "Use iOS bundle ids with launch_app; call search_apps/list_apps if you need to discover a bundle id. "
            "Use browser tools such as open_url/extract_visible_text/extract_articles/read_news for web tasks, "
            "and avoid Android-only concepts such as ADB shell, Android intents, Portal overlay, Play Store, "
            "and Android package-manager commands."
        )
    return (
        "Target platform: Android via ADB/Portal. Device refs are Android serials. "
        "Android intents, ADB shell, app packages, Portal overlay, notifications, and package search "
        "may be available when their tools are listed."
    )


def system_prompt_for_device(device: str, base: str = ANTHROPIC_SYSTEM) -> str:
    return f"{base}\n\n{platform_context(device)}"


def openai_tools_for_device(device: str) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]},
        }
        for t in tools_for_device(device)
    ]


def stop_agent(session_id: str):
    """Kill the running agent subprocess AND all its children Ã¢â‚¬â€ THIS session only.

    chat_claude_code launches claude with start_new_session=True, so claude and
    its node + MCP-tool children share one process group (pgid == the claude
    pid). Killing that group through the proc handle registered in
    _active_procs[session_id] is a complete, session-scoped stop: SIGTERM the
    group, then SIGKILL if it doesn't exit within 2s. A re-exec (execve) keeps
    the same pgid, so a changed PID doesn't escape this.

    We deliberately do NOT fall back to `pkill -f claude...stream-json`: that
    pattern matches EVERY claude stream-json process on the box, so stopping
    session A would reap session B mid-tap. Worse, the router calls stop_agent
    in the finally of every stream (including non-claude providers that never
    register a proc), so a normal completion on one session would nuke every
    other live agent. Multi-session is a headline capability Ã¢â‚¬â€ keep stops
    isolated to their own process group.
    """
    request_stop(session_id)
    import os as _os
    import signal as _sig

    proc = _active_procs.pop(session_id, None)
    if proc is None:
        # No process for this session (e.g. anthropic/ollama providers, or
        # already stopped). Nothing to kill Ã¢â‚¬â€ and crucially, no global sweep.
        return
    try:
        pgid = _os.getpgid(proc.pid)
        _os.killpg(pgid, _sig.SIGTERM)
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            _os.killpg(pgid, _sig.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    except Exception:
        # pgid lookup failed (proc already reaped) Ã¢â‚¬â€ best-effort plain kill.
        try:
            pgid = _os.getpgid(proc.pid)
            _os.killpg(pgid, _sig.SIGTERM)
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                _os.killpg(pgid, _sig.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    log.info("Stopped agent for session %s", session_id)


def create_session(device: str, provider: str = "", model: str = "", system_prompt: str = "") -> ChatSession:
    sid = str(uuid.uuid4())[:8]
    clear_stop_request(sid)
    if not provider:
        # Honor the configured default (set by `android-agent login`).
        from gitd.config import settings

        provider = settings.default_provider or "claude-code"
    default_model = PROVIDERS.get(provider, {}).get("models", ["sonnet"])[0] if not model else model
    session = ChatSession(id=sid, device=device, provider=provider, model=default_model or "sonnet")
    _sessions[sid] = session
    return session


def get_session(sid: str) -> ChatSession | None:
    return _sessions.get(sid)


def list_sessions() -> list[dict]:
    return [
        {"id": s.id, "device": s.device, "provider": s.provider, "model": s.model, "messages": len(s.messages)}
        for s in _sessions.values()
    ]


def delete_session(sid: str):
    _sessions.pop(sid, None)
    clear_stop_request(sid)


# Ã¢â€â‚¬Ã¢â€â‚¬ Persistence (DB) Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def save_session_to_db(session: ChatSession):
    """Persist a ChatSession to the database (upsert conversation + append new messages)."""
    from gitd.models.base import SessionLocal
    from gitd.models.chat import ChatConversation, ChatMessageRow

    db = SessionLocal()
    try:
        conv = db.query(ChatConversation).filter_by(id=session.id).first()
        now = _utcnow_iso()

        if not conv:
            # Auto-generate title from first user message
            title = ""
            for msg in session.messages:
                if msg.role == "user" and msg.content:
                    title = msg.content[:50]
                    break
            conv = ChatConversation(
                id=session.id,
                device=session.device,
                provider=session.provider,
                model=session.model,
                title=title,
                created_at=now,
                updated_at=now,
                message_count=0,
            )
            db.add(conv)

        conv.updated_at = now
        conv.message_count = len(session.messages)

        # Only insert messages that haven't been saved yet
        existing_count = db.query(ChatMessageRow).filter_by(conversation_id=session.id).count()
        for msg in session.messages[existing_count:]:
            db.add(
                ChatMessageRow(
                    conversation_id=session.id,
                    role=msg.role,
                    content=msg.content or "",
                    tool_name=msg.tool_name or "",
                    tool_args=json.dumps(msg.tool_args) if msg.tool_args else "{}",
                    tool_id=msg.tool_id or "",
                    created_at=now,
                )
            )

        db.commit()
    except Exception:
        db.rollback()
        log.exception("Failed to save session %s to DB", session.id)
    finally:
        db.close()


def list_conversations(device: str | None = None) -> list[dict]:
    """Return saved conversations, newest first."""
    from gitd.models.base import SessionLocal
    from gitd.models.chat import ChatConversation

    db = SessionLocal()
    try:
        q = db.query(ChatConversation)
        if device:
            q = q.filter_by(device=device)
        rows = q.order_by(ChatConversation.updated_at.desc()).all()
        return [
            {
                "id": r.id,
                "device": r.device,
                "provider": r.provider,
                "model": r.model,ó¯v¶‰žËkºwµçY••É•ÍÕ±Ð‰…¬Ñ¼Ñ¡”µ½‘•°™½ÈÑ¡”¹•áÐÑÕÉ¸¸4(€€€€€€€€€€€µ•ÍÍ…•Ì¹…ÁÁ•¹ 4(€€€€€€€€€€€€€€€ì4(€€€€€€€€€€€€€€€€€€€€‰É½±”ˆè€‰Ñ½½°ˆ°4(€€€€€€€€€€€€€€€€€€€€‰Ñ½½±}…±±}¥ˆèÑŒ¹¥°4(€€€€€€€€€€€€€€€€€€€€‰¹…µ”ˆèÑ½½±}¹…µ”°4(€€€€€€€€€€€€€€€€€€€€‰½¹Ñ•¹ÐˆèÉ•ÍÕ±ÑlèÄÔÀÁt°4(€€€€€€€€€€€€€€€ô4(€€€€€€€€€€€€¤4(4(€€€å¥•±ì‰ÑåÁ”ˆè€‰‘½¹”‰ô4(4(4(Œƒ‹ŠwŠ
³‹ŠwŠ
°Q½½°µ…±°Á…ÉÍ¥¹œ€¬=±±…µ„ƒ‹ŠwŠ
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
°4(4(4)‘•˜}Á…ÉÍ•}Ñ½½±}…±±Ì¡Ñ•áÐèÍÑÈ¤€´ø±¥ÍÑm‘¥Ñtè4(€€€€ˆˆ‰áÑÉ…ÐÑ½½°…±±Ì™É½´114½ÕÑÁÕÐ¸4(4(€€€!…¹‘±•Ì„™…¥È…µ½Õ¹Ð½˜Í±½À‰•…ÕÍ”Íµ…±°µ½‘•±Ìƒ‹Š
³Št•ÍÁ•¥…±±äÉ…Ü•µµ„€Ðƒ‹Š
³Št4(€€€•µ¥Ð˜µÍÑÉ¥¹œµÍÑå±”‘½Õ‰±•‰É…•Ì°¡…±˜µÅÕ½Ñ•­•åÌ°ÑÉ…¥±¥¹œ€°€ˆ€‰€4(€€€©Õ¹¬°µ¥ÍÍ¥¹œ½•áÑÉ„±½Í¥¹œ‰É…•Ì°…¹Í¥µ¥±…È¹•…Èµµ¥ÍÍ•Ì¸4(4(€€€•ÁÑ•Í¡…Á•Ìè4(€€€€€€´ì‰Ñ½½°ˆè€‰`ˆ°€‰…ÉÌˆèì¸¸¹õô€€€€€€€€€€€¡…¹½¹¥…°¤4(€€€€€€´ì‰Ñ½½°ˆè€‰`ˆ°€‰­Ý…ÉœÄˆè€¸¸¸°€¸¸¹ô€€€€€€¡™±…Ðƒ‹Š
³Št”¹œ¸¡½ÍÐµ•µµ„ÑÉ…¥¹•¤4(€€€€€€´ì‰…Ñ¥½¹}ÑåÁ”ˆè€‰`ˆ°€¸¸¹ô€€€€€€€€€€€€€€¡…Ñ¥½¸µÍ¡•µ„ƒ‹Š
³ŠtÑÉ…¹Í±…Ñ•Ñ¼Ñ½½°¤4(€€€€ˆˆˆ4(€€€¥µÁ½ÉÐÉ”4(4(€€€¥˜¹½ÐÑ•áÐè4(€€€€€€€É•ÑÕÉ¸mt4(4(€€€…±±Ìè±¥ÍÑm‘¥Ñt€ômt4(4(€€€€Œ5…À™É½´…Ñ¥½¸µÍ¡•µ„€‰…Ñ¥½¹}ÑåÁ”ˆƒ‹ŠƒŠd€ ‰Ñ½½°ˆ°…Éœµ­•äµÉ•ÝÉ¥Ñ•Ì¤¸½ÈÉ…Ü4(€€€€Œ•µµ„€Ð•µ¥ÑÑ¥¹œÑ¡”…Ñ¥½¸Í¡•µ„Ý”ÑÉ…¥¹•½¸°Ñ¡¥Ì±•ÑÌÑ¡”‘¥ÍÁ…Ñ¡•È4(€€€€ŒÍ•”…¹½¹¥…°Ñ½½°…±±ÌÝ¥Ñ¡½ÕÐÉ•ÑÉ…¥¹¥¹œÑ¡”Á…ÉÍ•ÈÍ¥‘”¸4(€€€…Ñ¥½¹}Ñ½}Ñ½½°€ôì4(€€€€€€€€‰½Á•¹}…ÁÀˆè€ ‰±…Õ¹¡}…ÁÀˆ°ì‰…ÁÁ}¹…µ”ˆè€‰Á…­…”‰ô¤°4(€€€€€€€€‰±¥¬ˆè€ ‰Ñ…Àˆ°ì‰àˆè€‰àˆ°€‰äˆè€‰ä‰ô¤°4(€€€€€€€€‰Ñ…Àˆè€ ‰Ñ…Àˆ°íô¤°4(€€€€€€€€‰±½¹}ÁÉ•ÍÌˆè€ ‰±½¹}ÁÉ•ÍÌˆ°íô¤°4(€€€€€€€€‰ÑåÁ•}Ñ•áÐˆè€ ‰¥¹ÁÕÑ}Ñ•áÐˆ°ì‰Ñ•áÐˆè€‰Ñ•áÐ‰ô¤°4(€€€€€€€€‰¥¹ÁÕÑ}Ñ•áÐˆè€ ‰¥¹ÁÕÑ}Ñ•áÐˆ°íô¤°4(€€€€€€€€‰ÍÝ¥Á”ˆè€ ‰ÍÝ¥Á”ˆ°íô¤°4(€€€€€€€€‰­•å}•Ù•¹Ðˆè€ ‰­•å}•Ù•¹Ðˆ°ì‰­•äˆè€‰­•ä‰ô¤°4(€€€€€€€€‰ÍÉ••¹Í¡½Ðˆè€ ‰ÍÉ••¹Í¡½Ðˆ°íô¤°4(€€€€€€€€‰Ý…¥Ðˆè€ ‰Ý…¥Ðˆ°ì‰‘ÕÉ…Ñ¥½¹}µÌˆè€‰µÌ‰ô¤°4(€€€€€€€€‰™½É•}ÍÑ½Àˆè€ ‰™½É•}ÍÑ½Àˆ°íô¤°4(€€€ô4(4(€€€‘•˜}½•É•}…Ñ¥½¸¡è‘¥Ð¤€´ø‘¥Ðð9½¹”è4(€€€€€€€…Ñ¥½¸€ô¹•Ð ‰…Ñ¥½¹}ÑåÁ”ˆ¤4(€€€€€€€¥˜¹½Ð¥Í¥¹ÍÑ…¹”¡…Ñ¥½¸°ÍÑÈ¤è4(€€€€€€€€€€€É•ÑÕÉ¸9½¹”4(€€€€€€€µ…ÁÁ¥¹œ€ô…Ñ¥½¹}Ñ½}Ñ½½°¹•Ð¡…Ñ¥½¸¤4(€€€€€€€¥˜¹½Ðµ…ÁÁ¥¹œè4(€€€€€€€€€€€É•ÑÕÉ¸9½¹”4(€€€€€€€Ñ½½±}¹…µ”°­•å}µ…À€ôµ…ÁÁ¥¹œ4(€€€€€€€…ÉÌ€ôíô4(€€€€€€€™½È¬°Ø¥¸¹¥Ñ•µÌ ¤è4(€€€€€€€€€€€¥˜¬€ôô€‰…Ñ¥½¹}ÑåÁ”ˆè4(€€€€€€€€€€€€€€€½¹Ñ¥¹Õ”4(€€€€€€€€€€€…ÉÍm­•å}µ…À¹•Ð¡¬°¬¥t€ôØ4(€€€€€€€É•ÑÕÉ¸ì‰Ñ½½°ˆèÑ½½±}¹…µ”°€‰…ÉÌˆè…ÉÍô4(4(€€€‘•˜}ÑÉå}‘¥Ð¡è½‰©•Ð¤€´ø‰½½°è4(€€€€€€€¥˜¹½Ð¥Í¥¹ÍÑ…¹”¡°‘¥Ð¤è4(€€€€€€€€€€€É•ÑÕÉ¸…±Í”4(€€€€€€€¥˜€‰Ñ½½°ˆ¥¸è4(€€€€€€€€€€€…±±Ì¹…ÁÁ•¹¡¤4(€€€€€€€€€€€É•ÑÕÉ¸QÉÕ”4(€€€€€€€½•É•€ô}½•É•}…Ñ¥½¸¡¤4(€€€€€€€¥˜½•É•è4(€€€€€€€€€€€…±±Ì¹…ÁÁ•¹¡½•É•¤4(€€€€€€€€€€€É•ÑÕÉ¸QÉÕ”4(€€€€€€€É•ÑÕÉ¸…±Í”4(4(€€€‘•˜}ÑÉå}±½…‘Ì¡É…ÜèÍÑÈ¤€´ø‰½½°è4(€€€€€€€ÑÉäè4(€€€€€€€€€€€É•ÑÕÉ¸}ÑÉå}‘¥Ð¡©Í½¸¹±½…‘Ì¡É…Ü¤¤4(€€€€€€€•á•ÁÐ€¡Y…±Õ•ÉÉ½È°QåÁ•ÉÉ½È¤è4(€€€€€€€€€€€É•ÑÕÉ¸…±Í”4(4(€€€‘•˜}…ÑÑ•µÁÑ}É•Á…¥ÉÌ¡É…ÜèÍÑÈ¤€´ø‰½½°è4(€€€€€€€€ˆˆ‰IÕ¸„¡…¥¸½˜±•…¹ÕÁÌ°É•ÑÉå¥¹œ©Í½¸¹±½…‘Ì…Ð•Ù•Éä¡•­Á½¥¹Ð¸ˆˆˆ4(€€€€€€€…¹‘¥‘…Ñ”€ôÉ…Ü4(4(€€€€€€€€Œ½Õ‰±•‰É…•Ì€¡•µµ„˜µÍÑÉ¥¹œ…ÉÑ•™…Ð¤ƒ‹ŠƒŠdÍ¥¹±•Ì¸=¹±äÉÕ¸Ý¡•¸…Ð4(€€€€€€€€Œ±•…ÍÐ½¹”íí€¥ÌÁÉ•Í•¹Ðƒ‹Š
³Št½Ñ¡•ÉÝ¥Í”Ý”½ÉÉÕÁÐÙ…±¥)M=8±¥­”4(€€€€€€€€Œì‰„ˆéì‰ˆˆèÅõõ€Ý¡¥ ¡…ÌÑÉ…¥±¥¹œõõ€™½È¹•ÍÑ•±½Í•Ì¸4(€€€€€€€€Œ¼¥Ð=9½¹±äì¥Ñ•É…Ñ¥¹œ½±±…ÁÍ•Ì±•¥Ñ¥µ…Ñ”ÑÉ¥Á±•Ì±¥­”õõõ€4(€€€€€€€€Œ€¡Ý¡¥ ¥Ìõõ€€¬õ€¥¸Ñ¡”‘½Õ‰±•½¹Ù•¹Ñ¥½¸¤Á…ÍÐÑ¡”É¥¡Ð4(€€€€€€€€ŒÍ¡…Á”¸4(€€€€€€€¥˜€‰íìˆ¥¸…¹‘¥‘…Ñ”è4(€€€€€€€€€€€¹•Ü€ô…¹‘¥‘…Ñ”¹É•Á±…” ‰íìˆ°€‰ìˆ¤¹É•Á±…” ‰õôˆ°€‰ôˆ¤4(€€€€€€€€€€€¥˜¹•Ü€„ô…¹‘¥‘…Ñ”è4(€€€€€€€€€€€€€€€…¹‘¥‘…Ñ”€ô¹•Ü4(€€€€€€€€€€€€€€€¥˜}ÑÉå}±½…‘Ì¡…¹‘¥‘…Ñ”¤è4(€€€€€€€€€€€€€€€€€€€É•ÑÕÉ¸QÉÕ”4(4(€€€€€€€€ŒMÑÉ¥À‘…¹±¥¹œµ½µµ„€‰©Õ¹¬Á…¥ÉÌˆ±¥­”€°€ˆ€‰€½È€°€ˆ‰€Ñ¡…ÐÍ½µ”4(€€€€€€€€Œµ½‘•±ÌÑ…¬½¸‰•™½É”„±½Í¥¹œ‰É…”¸4(€€€€€€€±•…¹•€ôÉ”¹ÍÕˆ¡Èœ±qÌ¨‰mx‰t¨‰qÌ¨ üõl±õt¤œ°€ˆˆ°…¹‘¥‘…Ñ”¤4(€€€€€€€¥˜±•…¹•€„ô…¹‘¥‘…Ñ”è4(€€€€€€€€€€€…¹‘¥‘…Ñ”€ô±•…¹•4(€€€€€€€€€€€¥˜}ÑÉå}±½…‘Ì¡…¹‘¥‘…Ñ”¤è4(€€€€€€€€€€€€€€€É•ÑÕÉ¸QÉÕ”4(4(€€€€€€€€ŒÉ½ÀÑÉ…¥±¥¹œ€±€‰•™½É”õ€€¼u€¸4(€€€€€€€±•…¹•€ôÉ”¹ÍÕˆ¡Èˆ±qÌ¨¡mõqut¤ˆ°È‰pÄˆ°…¹‘¥‘…Ñ”¤4(€€€€€€€¥˜±•…¹•€„ô…¹‘¥‘…Ñ”è4(€€€€€€€€€€€…¹‘¥‘…Ñ”€ô±•…¹•4(€€€€€€€€€€€¥˜}ÑÉå}±½…‘Ì¡…¹‘¥‘…Ñ”¤è4(€€€€€€€€€€€€€€€É•ÑÕÉ¸QÉÕ”4(4(€€€€€€€€ŒQÉÕ¹…Ñ”Ñ¼Ñ¡”™¥ÉÍÐ‰…±…¹•‰É…”ÍÁ…¸ƒ‹Š
³Št¡…¹‘±•ÌÑÉ…¥±¥¹œÁÉ½Í”4(€€€€€€€€Œ½È•áÑÉ„±½Í¥¹œ‰É…•Ì¸4(€€€€€€€‘•ÁÑ €ô€À4(€€€€€€€ÍÑ…ÉÐ€ô…¹‘¥‘…Ñ”¹™¥¹ ‰ìˆ¤4(€€€€€€€¥˜ÍÑ…ÉÐ€øô€Àè4(€€€€€€€€€€€™½È¤¥¸É…¹”¡ÍÑ…ÉÐ°±•¸¡…¹‘¥‘…Ñ”¤¤è4(€€€€€€€€€€€€€€€ €ô…¹‘¥‘…Ñ•m¥t4(€€€€€€€€€€€€€€€¥˜ €ôô€‰ìˆè4(€€€€€€€€€€€€€€€€€€€‘•ÁÑ €¬ô€Ä4(€€€€€€€€€€€€€€€•±¥˜ €ôô€‰ôˆè4(€€€€€€€€€€€€€€€€€€€‘•ÁÑ €´ô€Ä4(€€€€€€€€€€€€€€€€€€€¥˜‘•ÁÑ €ôô€Àè4(€€€€€€€€€€€€€€€€€€€€€€€¥˜}ÑÉå}±½…‘Ì¡…¹‘¥‘…Ñ•mÍÑ…ÉÐ€è¤€¬€Åt¤è4(€€€€€€€€€€€€€€€€€€€€€€€€€€€É•ÑÕÉ¸QÉÕ”4(€€€€€€€€€€€€€€€€€€€€€€€‰É•…¬4(4(€€€€€€€É•ÑÕÉ¸…±Í”4(4(€€€€Œ€Ä¤Ñ½½°€¼©Í½¸™•¹•‰±½­Ì€¡ÁÉ½µÁÐ…Í­Ì™½ÈÑ¡•Í”¤4(€€€™½Èµ…Ñ ¥¸É”¹™¥¹‘¥Ñ•È¡È‰€ üéÑ½½±ñ©Í½¸¤ýqÌ©q¸ü ¸¨ü¥q¸ý€ˆ°Ñ•áÐ°É”¹=Q10¤è4(€€€€€€€É…Ü€ôµ…Ñ ¹É½ÕÀ Ä¤¹ÍÑÉ¥À ¤4(€€€€€€€¥˜¹½ÐÉ…Üè4(€€€€€€€€€€€½¹Ñ¥¹Õ”4(€€€€€€€¥˜}ÑÉå}±½…‘Ì¡É…Ü¤è4(€€€€€€€€€€€½¹Ñ¥¹Õ”4(€€€€€€€}…ÑÑ•µÁÑ}É•Á…¥ÉÌ¡É…Ü¤4(4(€€€¥˜…±±Ìè4(€€€€€€€É•ÑÕÉ¸…±±Ì4(4(€€€€Œ€È¤9¼™•¹•Ìƒ‹Š
³ŠtÍ…¸™½È¥¹±¥¹”)M=8½‰©•ÑÌµ•¹Ñ¥½¹¥¹œ€‰Ñ½½°ˆ½È4(€€€€Œ€€€€‰…Ñ¥½¹}ÑåÁ”ˆ¸É••‘äèµ…Ñ •Ù•Éäì¸¸¹ô…¹ÑÉä•… ¸4(€€€™½Èµ…Ñ ¥¸É”¹™¥¹‘¥Ñ•È¡È‰qímyíõt¨ üéqímyíõt©qõmyíõt¨¤©qôˆ°Ñ•áÐ°É”¹=Q10¤è4(€€€€€€€É…Ü€ôµ…Ñ ¹É½ÕÀ À¤4(€€€€€€€¥˜€œ‰Ñ½½°ˆœ¹½Ð¥¸É…Ü…¹€œ‰…Ñ¥½¹}ÑåÁ”ˆœ¹½Ð¥¸É…Üè4(€€€€€€€€€€€½¹Ñ¥¹Õ”4(€€€€€€€¥˜}ÑÉå}±½…‘Ì¡É…Ü¤è4(€€€€€€€€€€€½¹Ñ¥¹Õ”4(€€€€€€€}…ÑÑ•µÁÑ}É•Á…¥ÉÌ¡É…Ü¤4(4(€€€¥˜…±±Ìè4(€€€€€€€É•ÑÕÉ¸…±±Ì4(4(€€€€Œ€Ì¤1…ÍÐµ‘¥Ñ ™…±±‰…¬ƒ‹Š
³Št•µµ„…ÐÑ•µÀ€ÀÉ½ÕÑ¥¹•±ä•µ¥ÑÌ¥¹±¥¹”‘½Õ‰±•4(€€€€Œ€€€‰É…•ÌÝ¥Ñ „µ¥Íµ…Ñ¡•½Õ¹Ð½˜±½Í¥¹œõ€€¡”¹œ¸™¥Ù”õ€™½ÈÑÝ¼4(€€€€Œ€€€íí€¤¸Q¡”ÍÑ•À´ÈÉ••à…‰½Ù”…¸Ðµ…Ñ „íí€ÍÑ…ÉÐ‰•…ÕÍ”¥Ð4(€€€€Œ€€€•áÁ•ÑÌ„¹½¸µ‰É…”¡…É…Ñ•È…™Ñ•ÈÑ¡”™¥ÉÍÐí€¸½±±…ÁÍ”‘½Õ‰±•4(€€€€Œ€€€‰É…•Ì½Ù•ÈÑ¡”Ý¡½±”Ñ•áÐ…¹ÑÉäÑ¡”Í…µ”Í…¸……¥¸¸4(€€€¥˜€‰íìˆ¥¸Ñ•áÐ½È€‰õôˆ¥¸Ñ•áÐè4(€€€€€€€™±…ÑÑ•¹•€ôÑ•áÐ¹É•Á±…” ‰íìˆ°€‰ìˆ¤¹É•Á±…” ‰õôˆ°€‰ôˆ¤4(€€€€€€€™½Èµ…Ñ ¥¸É”¹™¥¹‘¥Ñ•È¡È‰qímyíõt¨ üéqímyíõt©qõmyíõt¨¤©qôˆ°™±…ÑÑ•¹•°É”¹=Q10¤è4(€€€€€€€€€€€É…Ü€ôµ…Ñ ¹É½ÕÀ À¤4(€€€€€€€€€€€¥˜€œ‰Ñ½½°ˆœ¹½Ð¥¸É…Ü…¹€œ‰…Ñ¥½¹}ÑåÁ”ˆœ¹½Ð¥¸É…Üè4(€€€€€€€€€€€€€€€½¹Ñ¥¹Õ”4(€€€€€€€€€€€¥˜}ÑÉå}±½…‘Ì¡É…Ü¤è4(€€€€€€€€€€€€€€€½¹Ñ¥¹Õ”4(€€€€€€€€€€€}…ÑÑ•µÁÑ}É•Á…¥ÉÌ¡É…Ü¤4(4(€€€É•ÑÕÉ¸…±±Ì4(4(4)‘•˜¹½Éµ…±¥é•}Ñ½½±}…±°¡…±°è‘¥Ð¤€´øÑÕÁ±•mÍÑÈ°‘¥Ñtè4(€€€€ˆˆ‰MÁ±¥Ð„Á…ÉÍ•Ñ½½°…±°¥¹Ñ¼€¡Ñ½½±}¹…µ”°…ÉÌ¥€¸4(4(€€€QÝ¼Í¡…Á•Ì…É”Í••¸¥¸Ñ¡”Ý¥±…¹•Ù•ÉäÁÉ½Ù¥‘•ÈµÕÍÐ…•ÁÐ‰½Ñ è4(€€€€€€´ì‰Ñ½½°ˆè€‰`ˆ°€‰…ÉÌˆèì¸¸¹õõ€€€€€€€€€€€¡•µµ„´Ðµ”Éˆ°±±…µ„°…¹½¹¥…°¤4(€€€€€€´ì‰Ñ½½°ˆè€‰`ˆ°€‰Á…­…”ˆè€ˆ¸¸¸ˆ°€¸¸¹õ€€€€¡¡½ÍÐµ•µµ„ÑÉ…¥¹•°ÅÝ•¸ƒ‹Š
³Št™±…Ð¤4(4(€€€AÉ•™•ÈÑ¡”¹•ÍÑ•…ÉÍ€‘¥Ðì½Ñ¡•ÉÝ¥Í”ÑÉ•…ÐÑ¡”É•ÍÐ½˜Ñ¡”‘¥Ð4(€€€€¡•Ù•Éä­•ä•á•ÁÐÑ½½±€¤…Ì­Ý…ÉÌ¸I•ÑÕÉ¹Ì„™É•Í ‘¥ÐÑ¡”…±±•È4(€€€…¸µÕÑ…Ñ”€¡”¹œ¸Í•Ñ‘•™…Õ±Ð ‰‘•Ù¥”ˆ°€¸¸¸¥€¤Ý¥Ñ¡½ÕÐÑ½Õ¡¥¹œ…±±€¸4(€€€€ˆˆˆ4(€€€Ñ½½±}¹…µ”€ô…±°¹•Ð ‰Ñ½½°ˆ°€ˆˆ¤4(€€€É…Ý}…ÉÌ€ô…±°¹•Ð ‰…ÉÌˆ¤4(€€€¥˜¥Í¥¹ÍÑ…¹”¡É…Ý}…ÉÌ°‘¥Ð¤è4(€€€€€€€…ÉÌ€ô‘¥Ð¡É…Ý}…ÉÌ¤4(€€€•±Í”è4(€€€€€€€…ÉÌ€ôí¬èØ™½È¬°Ø¥¸…±°¹¥Ñ•µÌ ¤¥˜¬€„ô€‰Ñ½½°‰ô4(€€€É•ÑÕÉ¸Ñ½½±}¹…µ”°…ÉÌ4(4(4)‘•˜}¡…Ñ}½±±…µ„¡Í•ÍÍ¥½¸è¡…ÑM•ÍÍ¥½¸°ÕÍ•É}µ•ÍÍ…”èÍÑÈ¤è(€€€€ˆˆ‰UÍ”±½…°=±±…µ„µ½‘•°Ý¥Ñ µÕ±Ñ¤µÑÕÉ¸Ñ½½°•á•ÕÑ¥½¸±½½À¸ˆˆˆ(€€€¥µÁ½ÉÐÉ•ÅÕ•ÍÑÌ((€€€Í•ÍÍ¥½¸¹µ•ÍÍ…•Ì¹…ÁÁ•¹¡¡…Ñ5•ÍÍ…”¡É½±”ô‰ÕÍ•Èˆ°½¹Ñ•¹ÐõÕÍ•É}µ•ÍÍ…”¤¤(€€€¥˜ÍÑ½Á}É•ÅÕ•ÍÑ•¡Í•ÍÍ¥½¸¹¥¤è(€€€€€€€å¥•±ì‰ÑåÁ”ˆè€‰‘½¹”‰ô(€€€€€€€É•ÑÕÉ¸(€€€å¥•±ì‰ÑåÁ”ˆè€‰…Ñ¥Ù¥Ñäˆ°€‰½¹Ñ•¹Ðˆè€‹ÃãŠs
ÄI•…‘¥¹œÍÉ••¸¸¸¸‰ô((€€€€Œ	Õ¥±ÍÉ••¸½¹Ñ•áÐ(€€€½¹Ñ•áÐ€ô€ˆˆ(€€€ÑÉäè(€€€€€€€ÑÉ•”€ô•Ñ}ÍÉ••¹}ÑÉ•”¡Í•ÍÍ¥½¸¹‘•Ù¥”¤(€€€€€€€ÍÑ…Ñ”€ô•Ñ}Á¡½¹•}ÍÑ…Ñ”¡Í•ÍÍ¥½¸¹‘•Ù¥”¤(€€€€€€€½¹Ñ•áÐ€ô˜‰mMÉ••¹uq¹íÑÉ••lèÄÔÀÁuõq¹mÁÀèíÍÑ…Ñ”¹•Ð ÕÉÉ•¹ÑÁÀœ°€œüœ¥õuq¹q¸ˆ(€€€•á•ÁÐá•ÁÑ¥½¸…Ì•áŒè(€€€€€€€€ŒÍÉ••¸É•…Í¡½Õ±¹½ÐÁÉ•Ù•¹Ð=±±…µ„™É½´É•ÍÁ½¹‘¥¹œ¸Q¡”µ½‘•°(€€€€€€€€Œ…¸ÍÑ¥±°±…Õ¹ …¸…ÁÀ½ÈÉ•Á½ÉÐÑ¡…ÐÑ¡”‘•Ù¥”¥ÌÕ¹…Ù…¥±…‰±”¸(€€€€€€€å¥•±ì‰ÑåÁ”ˆè€‰…Ñ¥Ù¥Ñäˆ°€‰½¹Ñ•¹Ðˆè˜‹‹‡
ƒ¿
ã
<MÉ••¸É•…Õ¹…Ù…¥±…‰±”ì½¹Ñ¥¹Õ¥¹œ€¡íÍÑÈ¡•áŒ¥lèÄÀÁuô¤‰ô((€€€¥˜ÍÑ½Á}É•ÅÕ•ÍÑ•¡Í•ÍÍ¥½¸¹¥¤è(€€€€€€€å¥•±ì‰ÑåÁ”ˆè€‰‘½¹”‰ô(€€€€€€€É•ÑÕÉ¸(4(€€€€Œ	Õ¥±Ñ½½°±¥ÍÐÝ¥Ñ Á…É…´¹…µ•ÌÍ¼Ñ¡”114­¹½ÝÌÝ¡…Ð…ÉÌÑ¼Í•¹4(€€€ÍåÍÑ•´€ôU1Q}MeMQ4¹É•Á±…” ‰íÑ½½±}±¥ÍÑôˆ°Ñ½½±}ÁÉ½µÁÑ}±¥ÍÐ¡Ñ½½±Í}™½É}‘•Ù¥”¡Í•ÍÍ¥½¸¹‘•Ù¥”¤¤¤4(€€€ÍåÍÑ•´€ôÍåÍÑ•µ}ÁÉ½µÁÑ}™½É}‘•Ù¥”¡Í•ÍÍ¥½¸¹‘•Ù¥”°ÍåÍÑ•´¤4(4(€€€µ•ÍÍ…•Ì€ôl4(€€€€€€€ì‰É½±”ˆè€‰ÍåÍÑ•´ˆ°€‰½¹Ñ•¹ÐˆèÍåÍÑ•µô°4(€€€€€€€ì‰É½±”ˆè€‰ÕÍ•Èˆ°€‰½¹Ñ•¹Ðˆè˜‰í½¹Ñ•áÑõ•Ù¥”èíÍ•ÍÍ¥½¸¹‘•Ù¥•õq¹q¹íÕÍ•É}µ•ÍÍ…•ô‰ô°4(€€€t4(4(€€€µ½‘•°€ôÍ•ÍÍ¥½¸¹µ½‘•°½È€‰±±…µ„Ì¸ÈèÍˆˆ4(4(€€€€Œ•µµ„€Ð€¡…¹½Ñ¡•ÈÉ•…Í½¹¥¹œµ½‘•±Ì¤•µ¥Ð¡…¥¸µ½˜µÑ¡½Õ¡Ð¥¹Ñ¼„4(€€€€ŒÍ•Á…É…Ñ”Ñ¡¥¹­¥¹€™¥•±¸Q¡”…•¹Ð±½½ÀÝ…¹ÑÌ‘¥É•Ð)M=8Ñ½½°…±±Ì°4(€€€€ŒÍ¼‘¥Í…‰±”Ñ¡¥¹­¥¹œ™½ÈÑ¡”…Ñ¥½¸±½½À¸MÕÉ™…”…¹äÑ¡¥¹­¥¹œÑ¡…Ð‘½•Ì4(€€€€Œ…ÉÉ¥Ù”…Ì„Ñ¡¥¹­¥¹€•Ù•¹ÐÍ¼Ñ¡”U$…¸Í¡½Ü¥Ð¸4(€€€¥Í}Ñ¡¥¹­¥¹}µ½‘•°€ô…¹ä¡Ð¥¸µ½‘•°¹±½Ý•È ¤™½ÈÐ¥¸€ ‰•µµ„´Ðˆ°€‰•µµ„Ðˆ°€‰¡½ÍÐµ•µµ„ˆ°€‰ÅÝ•¸Ìˆ°€‰‘••ÁÍ••¬µÈÄˆ¤¤4(4(€€€™½ÈÑÕÉ¸¥¸É…¹”¡5a}QUI9L¤è(€€€€€€€¥˜ÍÑ½Á}É•ÅÕ•ÍÑ•¡Í•ÍÍ¥½¸¹¥¤è(€€€€€€€€€€€å¥•±ì‰ÑåÁ”ˆè€‰…Ñ¥Ù¥Ñäˆ°€‰½¹Ñ•¹Ðˆè€‰MÑ½ÁÁ•‰äÕÍ•È‰ô(€€€€€€€€€€€É•ÑÕÉ¸(€€€€€€€ÑÉäè(€€€€€€€€€€€Á…å±½…€ôì4(€€€€€€€€€€€€€€€€‰µ½‘•°ˆèµ½‘•°°4(€€€€€€€€€€€€€€€€‰µ•ÍÍ…•Ìˆèµ•ÍÍ…•Ì°4(€€€€€€€€€€€€€€€€‰ÍÑÉ•…´ˆè…±Í”°4(€€€€€€€€€€€€€€€€‰½ÁÑ¥½¹Ìˆèì‰¹Õµ}Ñàˆè€ÐÀäØ°€‰¹Õµ}ÁÉ•‘¥Ðˆè€ÔÄÉô°4(€€€€€€€€€€€ô4(€€€€€€€€€€€¥˜¥Í}Ñ¡¥¹­¥¹}µ½‘•°è4(€€€€€€€€€€€€€€€Á…å±½…‘l‰Ñ¡¥¹¬‰t€ô…±Í”4(€€€€€€€€€€€È€ôÉ•ÅÕ•ÍÑÌ¹Á½ÍÐ 4(€€€€€€€€€€€€€€€€‰¡ÑÑÀè¼½±½…±¡½ÍÐèÄÄÐÌÐ½…Á¤½¡…Ðˆ°4(€€€€€€€€€€€€€€€©Í½¸õÁ…å±½…°4(€€€€€€€€€€€€€€€Ñ¥µ•½ÕÐôÄÈÀ°4(€€€€€€€€€€€€¤4(€€€€€€€€€€€‘…Ñ„€ôÈ¹©Í½¸ ¤4(€€€€€€€€€€€¥˜È¹ÍÑ…ÑÕÍ}½‘”€„ô€ÈÀÀè4(€€€€€€€€€€€€€€€•ÉÉ½È€ô‘…Ñ„¹•Ð ‰•ÉÉ½Èˆ°È¹Ñ•áÑlèÈÀÁt¤4(€€€€€€€€€€€€€€€¥˜€‰¹½Ð™½Õ¹ˆ¥¸•ÉÉ½È¹±½Ý•È ¤è4(€€€€€€€€€€€€€€€€€€€å¥•±ì4(€€€€€€€€€€€€€€€€€€€€€€€€‰ÑåÁ”ˆè€‰•ÉÉ½Èˆ°4(€€€€€€€€€€€€€€€€€€€€€€€€‰½¹Ñ•¹Ðˆè˜‰5½‘•°€íµ½‘•±ôœ¹½Ð™½Õ¹¸AÕ±°¥Ð™¥ÉÍÐè½±±…µ„ÁÕ±°íµ½‘•±ôˆ°4(€€€€€€€€€€€€€€€€€€€ô4(€€€€€€€€€€€€€€€•±Í”è4(€€€€€€€€€€€€€€€€€€€å¥•±ì‰ÑåÁ”ˆè€‰•ÉÉ½Èˆ°€‰½¹Ñ•¹Ðˆè˜‰=±±…µ„•ÉÉ½Èèí•ÉÉ½Éô‰ô4(€€€€€€€€€€€€€€€É•ÑÕÉ¸4(€€€€€€€€€€€µÍœ€ô‘…Ñ„¹•Ð ‰µ•ÍÍ…”ˆ°íô¤½Èíô4(€€€€€€€€€€€É•Á±ä€ôµÍœ¹•Ð ‰½¹Ñ•¹Ðˆ°€ˆˆ¤½È€ˆˆ4(€€€€€€€€€€€Ñ¡¥¹­¥¹œ€ôµÍœ¹•Ð ‰Ñ¡¥¹­¥¹œˆ°€ˆˆ¤½È€ˆˆ4(€€€€€€€€€€€¥˜Ñ¡¥¹­¥¹œè4(€€€€€€€€€€€€€€€å¥•±ì‰ÑåÁ”ˆè€‰Ñ¡¥¹­¥¹œˆ°€‰½¹Ñ•¹ÐˆèÑ¡¥¹­¥¹ô4(€€€€€€€€€€€€Œ…±±‰…¬è¥˜Ñ¡¥¹¬é™…±Í”Ý…Ì¥¹½É•…¹½¹Ñ•¹Ð¥Ì•µÁÑä‰ÕÐÑ¡¥¹­¥¹œ¡…ÌÑ¡”…¹ÍÝ•È4(€€€€€€€€€€€¥˜¹½ÐÉ•Á±ä…¹Ñ¡¥¹­¥¹œè4(€€€€€€€€€€€€€€€É•Á±ä€ôÑ¡¥¹­¥¹œ4(€€€€€€€•á•ÁÐÉ•ÅÕ•ÍÑÌ¹½¹¹•Ñ¥½¹ÉÉ½Èè4(€€€€€€€€€€€å¥•±ì4(€€€€€€€€€€€€€€€€‰ÑåÁ”ˆè€‰•ÉÉ½Èˆ°4(€€€€€€€€€€€€€€€€‰½¹Ñ•¹Ðˆè€‰=±±…µ„¹½ÐÉ•…¡…‰±”…Ð±½…±¡½ÍÐèÄÄÐÌÐ¸MÑ…ÉÐ¥Ðè½±±…µ„Í•ÉÙ”ˆ°4(€€€€€€€€€€€ô4(€€€€€€€€€€€É•ÑÕÉ¸4(€€€€€€€•á•ÁÐá•ÁÑ¥½¸…Ì”è4(€€€€€€€€€€€å¥•±ì‰ÑåÁ”ˆè€‰•ÉÉ½Èˆ°€‰½¹Ñ•¹ÐˆèÍÑÈ¡”¥ô4(€€€€€€€€€€€É•ÑÕÉ¸4(4(€€€€€€€¥˜¹½ÐÉ•Á±äè4(€€€€€€€€€€€‰É•…¬4(4(€€€€€€€Í•ÍÍ¥½¸¹µ•ÍÍ…•Ì¹…ÁÁ•¹¡¡…Ñ5•ÍÍ…”¡É½±”ô‰…ÍÍ¥ÍÑ…¹Ðˆ°½¹Ñ•¹ÐõÉ•Á±ä¤¤4(€€€€€€€å¥•±ì‰ÑåÁ”ˆè€‰Ñ•áÐˆ°€‰½¹Ñ•¹ÐˆèÉ•Á±åô4(€€€€€€€µ•ÍÍ…•Ì¹…ÁÁ•¹¡ì‰É½±”ˆè€‰…ÍÍ¥ÍÑ…¹Ðˆ°€‰½¹Ñ•¹ÐˆèÉ•Á±åô¤4(4(€€€€€€€€ŒA…ÉÍ”…¹•á•ÕÑ”Ñ½½°…±±Ì4(€€€€€€€Ñ½½±}…±±Ì€ô}Á…ÉÍ•}Ñ½½±}…±±Ì¡É•Á±ä¤4(€€€€€€€¥˜¹½ÐÑ½½±}…±±Ìè4(€€€€€€€€€€€‰É•…¬€€Œ9¼Ñ½½±ÌÉ•ÅÕ•ÍÑ•ƒ‹Š
³Št‘½¹”4(4(€€€€€€€Ñ½½±}É•ÍÕ±ÑÌ€ômt(€€€€€€€™½È…±°¥¸Ñ½½±}…±±Ìè(€€€€€€€€€€€¥˜ÍÑ½Á}É•ÅÕ•ÍÑ•¡Í•ÍÍ¥½¸¹¥¤è(€€€€€€€€€€€€€€€å¥•±ì‰ÑåÁ”ˆè€‰…Ñ¥Ù¥Ñäˆ°€‰½¹Ñ•¹Ðˆè€‰MÑ½ÁÁ•‰äÕÍ•È‰ô(€€€€€€€€€€€€€€€É•ÑÕÉ¸(€€€€€€€€€€€Ñ½½±}¹…µ”°Ñ½½±}…ÉÌ€ô¹½Éµ…±¥é•}Ñ½½±}…±°¡…±°¤(€€€€€€€€€€€Ñ½½±}…ÉÌ¹Í•Ñ‘•™…Õ±Ð ‰‘•Ù¥”ˆ°Í•ÍÍ¥½¸¹‘•Ù¥”¤4(4(€€€€€€€€€€€Í•ÍÍ¥½¸¹µ•ÍÍ…•Ì¹…ÁÁ•¹¡¡…Ñ5•ÍÍ…”¡É½±”ô‰Ñ½½±}…±°ˆ°Ñ½½±}¹…µ”õÑ½½±}¹…µ”°Ñ½½±}…ÉÌõÑ½½±}…ÉÌ°½¹Ñ•¹Ðôˆˆ¤¤4(€€€€€€€€€€€å¥•±ì‰ÑåÁ”ˆè€‰Ñ½½±}…±°ˆ°€‰¹…µ”ˆèÑ½½±}¹…µ”°€‰…ÉÌˆèÑ½½±}…ÉÍô4(4(€€€€€€€€€€€ÑÉäè4(€€€€€€€€€€€€€€€É•ÍÕ±Ð€ô}‘¥ÍÁ…Ñ¡}Ñ½½°¡Í•ÍÍ¥½¸°Ñ½½±}¹…µ”°Ñ½½±}…ÉÌ¤4(€€€€€€€€€€€€€€€Í•ÍÍ¥½¸¹µ•ÍÍ…•Ì¹…ÁÁ•¹¡¡…Ñ5•ÍÍ…”¡É½±”ô‰Ñ½½±}É•ÍÕ±Ðˆ°½¹Ñ•¹ÐõÉ•ÍÕ±ÑlèÔÀÁt°Ñ½½±}¹…µ”õÑ½½±}¹…µ”¤¤4(€€€€€€€€€€€€€€€å¥•±ì‰ÑåÁ”ˆè€‰Ñ½½±}É•ÍÕ±Ðˆ°€‰¹…µ”ˆèÑ½½±}¹…µ”°€‰É•ÍÕ±ÐˆèÉ•ÍÕ±ÑlèÔÀÁuô4(€€€€€€€€€€€€€€€Ñ½½±}É•ÍÕ±ÑÌ¹…ÁÁ•¹¡˜‰míÑ½½±}¹…µ•õtíÉ•ÍÕ±ÑlèàÀÁuôˆ¤4(€€€€€€€€€€€•á•ÁÐá•ÁÑ¥½¸…Ì”è4(€€€€€€€€€€€€€€€•ÉÈ€ô˜‰Q½½°•ÉÉ½Èèí•ôˆ4(€€€€€€€€€€€€€€€Í•ÍÍ¥½¸¹µ•ÍÍ…•Ì¹…ÁÁ•¹¡¡…Ñ5•ÍÍ…”¡É½±”ô‰Ñ½½±}É•ÍÕ±Ðˆ°½¹Ñ•¹Ðõ•ÉÈ°Ñ½½±}¹…µ”õÑ½½±}¹…µ”¤¤4(€€€€€€€€€€€€€€€å¥•±ì‰ÑåÁ”ˆè€‰Ñ½½±}É•ÍÕ±Ðˆ°€‰¹…µ”ˆèÑ½½±}¹…µ”°€‰É•ÍÕ±Ðˆè•ÉÉô4(€€€€€€€€€€€€€€€Ñ½½±}É•ÍÕ±ÑÌ¹…ÁÁ•¹¡˜‰míÑ½½±}¹…µ•õtII=Hèí•ÉÉôˆ¤4(4(€€€€€€€€Œ••Ñ½½°É•ÍÕ±ÑÌ‰…¬™½È¹•áÐÑÕÉ¸4(€€€€€€€µ•ÍÍ…•Ì¹…ÁÁ•¹¡ì‰É½±”ˆè€‰ÕÍ•Èˆ°€‰½¹Ñ•¹Ðˆè€‰Q½½°É•ÍÕ±ÑÌéq¸ˆ€¬€‰q¸ˆ¹©½¥¸¡Ñ½½±}É•ÍÕ±ÑÌ¥ô¤4(4(€€€å¥•±ì‰ÑåÁ”ˆè€‰‘½¹”‰ô4(4(4(Œƒ‹ŠwŠ
³‹ŠwŠ
°!•±Á•ÉÌƒ‹ŠwŠ
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
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
³‹ŠwŠ
°4(4(4)‘•˜}‰Õ¥±‘}Ù¥Í¥½¹}½¹Ñ•¹Ð¡Í•ÍÍ¥½¸è¡…ÑM•ÍÍ¥½¸°Ñ•áÐèÍÑÈ¤€´ø±¥ÍÐè4(€€€€ˆˆ‰	Õ¥±ÕÍ•È½¹Ñ•¹ÐÝ¥Ñ ÍÉ••¹Í¡½Ð™½ÈÙ¥Í¥½¸µ…Á…‰±”ÁÉ½Ù¥‘•ÉÌ¸ˆˆˆ4(€€€½¹Ñ•¹Ð€ômt4(€€€¥˜Í•ÍÍ¥½¸¹…ÕÑ½}ÍÉ••¹Í¡½Ð…¹Í•ÍÍ¥½¸¹‘•Ù¥”è4(€€€€€€€ÑÉäè4(€€€€€€€€€€€ÑÉ•”€ô•Ñ}ÍÉ••¹}ÑÉ•”¡Í•ÍÍ¥½¸¹‘•Ù¥”¤4(€€€€€€€€€€€¥˜ÑÉ•”…¹ÑÉ•”€„ô€ˆ¡•µÁÑäÍÉ••¸¤ˆè4(€€€€€€€€€€€€€€€½¹Ñ•¹Ð¹…ÁÁ•¹¡ì‰ÑåÁ”ˆè€‰Ñ•áÐˆ°€‰Ñ•áÐˆè˜‰mÕÉÉ•¹ÐÍÉ••¹uq¹íÑÉ••lèÈÀÀÁuô‰ô¤4(€€€€€€€•á•ÁÐá•ÁÑ¥½¸è4(€€€€€€€€€€€Á…ÍÌ4(€€€€€€€ÑÉäè4(€€€€€€€€€€€ÍÑ…Ñ”€ô•Ñ}Á¡½¹•}ÍÑ…Ñ”¡Í•ÍÍ¥½¸¹‘•Ù¥”¤4(€€€€€€€€€€€¥˜ÍÑ…Ñ”è4(€€€€€€€€€€€€€€€½¹Ñ•¹Ð¹…ÁÁ•¹ 4(€€€€€€€€€€€€€€€€€€€ì‰ÑåÁ”ˆè€‰Ñ•áÐˆ°€‰Ñ•áÐˆè˜‰mÁÀèíÍÑ…Ñ”¹•Ð ÕÉÉ•¹ÑÁÀœ°€œœ¥ô€¡íÍÑ…Ñ”¹•Ð Á…­…•9…µ”œ°€œœ¥ô¥t‰ô4(€€€€€€€€€€€€€€€€¤4(€€€€€€€•á•ÁÐá•ÁÑ¥½¸è4(€€€€€€€€€€€Á…ÍÌ4(€€€€€€€ÑÉäè4(€€€€€€€€€€€¥µœ€ô•Ñ}ÍÉ••¹Í¡½Ñ}ˆØÐ¡Í•ÍÍ¥½¸¹‘•Ù¥”¤4(€€€€€€€€€€€¥˜¥µœè4(€€€€€€€€€€€€€€€½¹Ñ•¹Ð¹…ÁÁ•¹¡ì‰ÑåÁ”ˆè€‰¥µ…”ˆ°€‰Í½ÕÉ”ˆèì‰ÑåÁ”ˆè€‰‰…Í”ØÐˆ°€‰µ•‘¥…}ÑåÁ”ˆè€‰¥µ…”½©Á•œˆ°€‰‘…Ñ„ˆè¥µõô¤4(€€€€€€€•á•ÁÐá•ÁÑ¥½¸è4(€€€€€€€€€€€Á…ÍÌ4(€€€½¹Ñ•¹Ð¹…ÁÁ•¹¡ì‰ÑåÁ”ˆè€‰Ñ•áÐˆ°€‰Ñ•áÐˆèÑ•áÑô¤4(€€€É•ÑÕÉ¸½¹Ñ•¹Ð4(