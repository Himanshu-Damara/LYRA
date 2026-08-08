"""
llm_planner.py — LLM-powered action planner that replaces the keyword router.

Uses the existing Groq API (LLaMA 3.3 70B) to:
  1. Understand the user's natural language command
  2. Analyze the current screen state (from accessibility + vision)
  3. Generate a structured action plan as a JSON sequence of primitives
  4. Maintain conversation memory for multi-turn interactions

This is the "brain" of the Hybrid LLM architecture.
"""

import json
import time
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field

from lyra.assistant.grok_client import GrokClient


# ── System Prompt Engineering ─────────────────────────────────────

SYSTEM_PROMPT = """You are LYRA, an AI phone assistant brain. You control an Android phone through ADB commands.

## Your Role
Given a user's command and the current state of their phone screen, you must:
1. Classify the intent as "ACTION" (phone control) or "QUESTION" (knowledge query)
2. For ACTIONs: generate a step-by-step action plan using the available primitives
3. For QUESTIONs: indicate it should be routed to the Q&A system

## Available Action Primitives
- HOME: Press the home button
- BACK: Press the back button
- LAUNCH_APP: Launch an app {"app_name": "instagram"|"whatsapp"|"gmail"|"camera"|"clock"|"contacts"|"chrome"|"settings"|"calculator"|"calendar"|"youtube"|"maps"}
- TAP: Tap a UI element by vision label {"label": "shutter_button"}
- TAP_BY_TEXT: Tap element containing text {"text": "Settings"}
- TAP_XY: Tap at coordinates {"x": 360, "y": 800}
- SWIPE: Swipe the screen {"direction": "up"|"down"|"left"|"right"}
- TYPE: Type text into focused field {"text": "hello world"}
- WAIT_FOR_TEXT: Wait for text to appear {"text": "Done", "timeout": 10}
- FIND_BY_TEXT: Find element by text {"text": "Login"}
- SCROLL_TO_FIND: Scroll until text found {"text": "About", "direction": "up"|"down"}
- VERIFY: Verify screen state {"expected_state": "HOME_SCREEN"} or {"expected_element": "post_like_liked"} or {"expected_text": "Success"}

## Known Vision Labels (LyraNet model can detect these)
app_icon_instagram, app_icon_camera, app_icon_clock, story_thumbnail,
post_like_unliked, post_like_liked, story_like_unliked, story_like_liked,
close_button, shutter_button, add_alarm_button, save_button, back_button

## Known Screen States (LyraNet model can classify these)
HOME_SCREEN, INSTAGRAM_HOME, INSTAGRAM_STORY, CAMERA_VIEWFINDER,
CLOCK_MAIN, ALARM_CREATE, UNKNOWN

## Response Format
You MUST respond with valid JSON only. No markdown, no explanation outside JSON.

For ACTION intents:
{
  "intent": "ACTION",
  "task_name": "short_snake_case_name",
  "description": "What this plan accomplishes",
  "reasoning": "Why you chose these steps",
  "steps": [
    {"action": "HOME"},
    {"action": "LAUNCH_APP", "app_name": "instagram"},
    {"action": "WAIT_FOR_TEXT", "text": "Home", "timeout": 5},
    {"action": "TAP_BY_TEXT", "text": "Search"},
    {"action": "TYPE", "text": "sunset photos"}
  ]
}

For QUESTION intents:
{
  "intent": "QUESTION",
  "question": "the user's question to forward to Q&A"
}

## Standard App Workflow Guidelines

### WhatsApp - Sending a Message
Do NOT assume the contact is already visible on the chat list. Use the Search feature to locate the contact:
1. LAUNCH_APP: {"app_name": "whatsapp"}
2. WAIT_FOR_TEXT: {"text": "Chats", "timeout": 5}
3. TAP_BY_TEXT: {"text": "Search"} or tap the search icon/input.
4. TYPE: {"text": "contact_name"} (e.g. "vansh cu")
5. WAIT_FOR_TEXT: {"text": "contact_name", "timeout": 3}
6. TAP_BY_TEXT: {"text": "contact_name"}
7. TYPE: {"text": "message_text"}
8. TAP_BY_TEXT: {"text": "Send"} or tap the send button.

### Instagram - Liking the First Post
1. LAUNCH_APP: {"app_name": "instagram"}
2. WAIT_FOR_TEXT: {"text": "Home", "timeout": 5}
3. Locate the first post's unliked button (heart icon) and tap it:
   - Use TAP: {"label": "post_like_unliked"} or TAP_XY coordinate where the heart is.
4. VERIFY: {"expected_element": "post_like_liked"}

### Gmail - Sending/Composing an Email
1. LAUNCH_APP: {"app_name": "gmail"}
2. WAIT_FOR_TEXT: {"text": "Inbox", "timeout": 5}
3. TAP_BY_TEXT: {"text": "Compose"} (or "+" button)
4. TYPE: {"text": "recipient@email.com"}
5. TAP_BY_TEXT: {"text": "Subject"} or navigate to Subject field and TYPE subject
6. TAP_BY_TEXT: {"text": "Compose email"} or navigate to Body field and TYPE body
7. TAP_BY_TEXT: {"text": "Send"} or tap the send button icon.

### Alarm - Creating a New Alarm
1. LAUNCH_APP: {"app_name": "clock"}
2. WAIT_FOR_TEXT: {"text": "Alarm", "timeout": 5}
3. TAP_BY_TEXT: {"text": "Add"} or tap the "+" button
4. Set the time and TAP_BY_TEXT: {"text": "Save"} or "OK"

## Guidelines
- Prefer LAUNCH_APP over TAP for opening apps (more reliable)
- Prefer TAP_BY_TEXT over TAP when the element has visible text
- Use TAP with vision labels for icon-only elements (hearts, shutter, etc.)
- Always include appropriate waits between actions for screen transitions
- Add VERIFY steps after critical actions
- If the user's command is ambiguous, make your best interpretation
- If screen context shows the target app is already open, skip the launch step
"""


@dataclass
class ConversationTurn:
    """A single turn in the conversation history."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: float = field(default_factory=time.time)


class LLMPlanner:
    """
    LLM-powered action planner that generates structured action plans
    from natural language commands and screen context.
    """

    def __init__(self, max_memory_turns: int = 10):
        self.client = GrokClient(backend="ollama")
        self.memory: List[ConversationTurn] = []
        self.max_memory_turns = max_memory_turns

    @property
    def is_available(self) -> bool:
        """Check if the LLM API is available."""
        return self.client.enabled

    def plan(
        self,
        user_command: str,
        screen_context: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Generate an action plan for the given user command.

        Args:
            user_command: The user's natural language input
            screen_context: Current screen perception data (optional)

        Returns:
            Parsed plan dict with 'intent', 'steps', etc.
        """
        # Build the context-aware user message
        user_message = self._build_user_message(user_command, screen_context)

        # Build conversation messages with memory
        messages = self._build_messages(user_message)

        # Call the LLM
        try:
            response_text = self._call_llm(messages)
            plan = self._parse_response(response_text)
        except Exception as e:
            plan = {
                "intent": "ERROR",
                "error": str(e),
                "raw_response": getattr(e, 'response_text', ''),
            }

        # Update memory
        self.memory.append(ConversationTurn(role="user", content=user_command))
        if plan.get("intent") != "ERROR":
            self.memory.append(ConversationTurn(
                role="assistant",
                content=json.dumps(plan, indent=2) if isinstance(plan, dict) else str(plan)
            ))

        # Trim memory to window size
        while len(self.memory) > self.max_memory_turns * 2:
            self.memory.pop(0)

        return plan

    def classify_intent(self, user_command: str) -> Tuple[str, str]:
        """
        Quick intent classification. Returns (intent_type, detail).
        Uses the full planner for classification to get LLM-quality NLU.
        """
        plan = self.plan(user_command)
        intent = plan.get("intent", "QUESTION")

        if intent == "ACTION":
            return "ACTION", plan.get("task_name", "dynamic_task")
        elif intent == "QUESTION":
            return "QUESTION", plan.get("question", user_command)
        else:
            return "QUESTION", user_command

    def _build_user_message(self, command: str, screen_context: Optional[Dict]) -> str:
        """Build the user message with optional screen context."""
        parts = [f"User command: \"{command}\""]

        if screen_context:
            parts.append("\n--- Current Screen State ---")

            # Screen classification
            state = screen_context.get("screen_state", "UNKNOWN")
            conf = screen_context.get("screen_confidence", 0.0)
            parts.append(f"Screen: {state} ({conf:.0%} confidence)")

            # Vision detections
            dets = screen_context.get("detections", [])
            if dets:
                parts.append(f"Vision detections ({len(dets)}):")
                for d in dets[:8]:
                    parts.append(
                        f"  - {d['label']} ({d['confidence']:.0%}) "
                        f"at [{d['bbox_original'][0]},{d['bbox_original'][1]},"
                        f"{d['bbox_original'][2]},{d['bbox_original'][3]}]"
                    )

            # Accessibility tree elements
            a11y = screen_context.get("accessibility_elements", [])
            if a11y:
                parts.append(f"Accessibility elements ({len(a11y)}):")
                for elem in a11y[:15]:
                    text = elem.get("text", "")
                    desc = elem.get("content_desc", "")
                    clickable = elem.get("clickable", False)
                    bounds = elem.get("bounds", [])
                    display = text or desc or "(no text)"
                    click_str = " [clickable]" if clickable else ""
                    bounds_str = f" at {bounds}" if bounds else ""
                    parts.append(f"  - \"{display}\"{click_str}{bounds_str}")

            resolution = screen_context.get("screen_resolution", (0, 0))
            parts.append(f"Screen resolution: {resolution[0]}x{resolution[1]}")

        return "\n".join(parts)

    def _build_messages(self, user_message: str) -> List[Dict[str, str]]:
        """Build the full message list with system prompt + memory + current message."""
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Add conversation memory
        for turn in self.memory[-self.max_memory_turns * 2:]:
            messages.append({"role": turn.role, "content": turn.content})

        # Add current message
        messages.append({"role": "user", "content": user_message})

        return messages

    def _call_llm(self, messages: List[Dict[str, str]]) -> str:
        """Call the LLM API (Ollama or cloud) with the given messages."""
        import requests
        import re

        headers = {
            "Authorization": f"Bearer {self.client.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.client.model,
            "messages": messages,
            "temperature": 0.3,  # Low temperature for structured output
            "max_tokens": 1200,
        }

        # Only add response_format for non-Ollama backends (Ollama doesn't
        # support it reliably, especially with thinking models like Qwen3)
        is_ollama = "localhost:11434" in self.client.api_url
        if not is_ollama:
            payload["response_format"] = {"type": "json_object"}

        try:
            response = requests.post(
                self.client.api_url, headers=headers, json=payload, timeout=120
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"].get("content", "").strip()

            # Qwen3 thinking models may wrap output in <think>...</think> tags
            # before the actual JSON. Strip the thinking block.
            if "<think>" in content:
                # Extract everything after the closing </think> tag
                parts = content.split("</think>")
                if len(parts) > 1:
                    content = parts[-1].strip()
                else:
                    # No closing tag — try to find JSON after the think block
                    content = re.sub(r"<think>.*", "", content, flags=re.DOTALL).strip()

            return content
        except Exception as e:
            raise RuntimeError(f"LLM API call failed: {e}") from e

    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse the LLM's JSON response into a structured plan."""
        try:
            plan = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0].strip()
                plan = json.loads(json_str)
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0].strip()
                plan = json.loads(json_str)
            else:
                raise ValueError(f"Could not parse LLM response as JSON: {response_text[:200]}")

        # Validate required fields
        if "intent" not in plan:
            plan["intent"] = "QUESTION"

        if plan["intent"] == "ACTION" and "steps" not in plan:
            raise ValueError(f"ACTION plan missing 'steps' field: {plan}")

        return plan

    def clear_memory(self):
        """Clear conversation memory."""
        self.memory.clear()
