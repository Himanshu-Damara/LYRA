"""
router.py — Hybrid intent classifier: LLM-primary with keyword fallback.

Routes user input through two classification strategies:
  1. PRIMARY: LLM-based classification via llm_planner (understands paraphrasing,
     context, multi-step commands, ambiguous intent)
  2. FALLBACK: Keyword matching (works offline, no API required)

The router automatically falls back to keywords if the LLM API is unavailable.
"""

import re
from typing import Tuple, Dict, Any, Optional

from lyra.agent.tasks import list_tasks, TASK_REGISTRY


# ── Keyword Fallback System ──────────────────────────────────────

# Keywords that strongly indicate phone action intent
ACTION_KEYWORDS = [
    "open", "launch", "start", "tap", "click", "press", "swipe",
    "scroll", "type", "enter", "send", "like", "unlike", "take photo",
    "capture", "camera", "instagram", "story", "alarm", "clock",
    "go home", "go back", "home screen", "dm", "message", "mail", "email",
    "settings", "wifi", "bluetooth", "volume", "brightness",
    "whatsapp", "youtube", "chrome", "spotify", "maps",
    "call", "dial", "text", "search", "download", "install",
    "screenshot", "record", "play", "pause", "stop", "skip", "next",
    "set alarm", "set timer", "turn on", "turn off", "enable", "disable",
]

# Keywords that strongly indicate a question
QUESTION_KEYWORDS = [
    "what", "how", "why", "when", "where", "who", "which",
    "explain", "tell me", "describe", "define", "meaning",
    "is it", "are there", "can you", "do you",
]


def classify_intent_keyword(user_input: str) -> Tuple[str, str]:
    """
    FALLBACK: Keyword-based intent classification.
    Returns (intent_type, matched_keyword_or_task).
    """
    text = user_input.lower().strip()

    # Check if the text ends with a question mark
    is_question_form = text.endswith("?")

    # Score action keywords
    action_score = 0
    matched_action = ""
    for kw in ACTION_KEYWORDS:
        if kw in text:
            action_score += 1
            if not matched_action:
                matched_action = kw

    # Score question keywords
    question_score = 0
    matched_question = ""
    for kw in QUESTION_KEYWORDS:
        if text.startswith(kw) or f" {kw} " in f" {text} ":
            question_score += 1
            if not matched_question:
                matched_question = kw

    if is_question_form:
        question_score += 2

    # Check for direct task name match
    for task_name in list_tasks():
        if task_name.replace("_", " ") in text:
            return "ACTION", task_name

    if action_score > question_score:
        return "ACTION", matched_action
    elif question_score > 0:
        return "QUESTION", matched_question
    else:
        # Default to question if we can't determine
        return "QUESTION", "general"


def resolve_task_from_input(user_input: str) -> str:
    """
    Maps natural language action requests to task registry names.
    Returns the best matching task name or raises ValueError.
    """
    text = user_input.lower().strip()

    # Direct mappings from natural language to task names
    mappings = {
        "open instagram": "open_instagram",
        "launch instagram": "open_instagram",
        "start instagram": "open_instagram",
        "open camera": "open_camera",
        "launch camera": "open_camera",
        "take photo": "take_photo",
        "take a photo": "take_photo",
        "capture photo": "take_photo",
        "take picture": "take_photo",
        "like post": "like_post",
        "like the post": "like_post",
        "like instagram post": "like_post",
        "view story": "view_story",
        "open story": "view_story",
        "watch story": "view_story",
        "view instagram story": "view_story",
        "go home": "go_home",
        "go to home": "go_home",
        "home screen": "go_home",
    }

    for phrase, task_name in mappings.items():
        if phrase in text:
            return task_name

    # Fuzzy match: check if any task name keyword appears
    for task_name in TASK_REGISTRY:
        keywords = task_name.split("_")
        if all(kw in text for kw in keywords):
            return task_name

    raise ValueError(
        f"Could not map '{user_input}' to a known task. "
        f"Available tasks: {list_tasks()}"
    )


# ── Unified Router ───────────────────────────────────────────────

class HybridRouter:
    """
    Hybrid intent router that uses LLM when available,
    falling back to keyword matching when offline.
    """

    def __init__(self):
        self._planner = None
        self._planner_init_attempted = False

    @property
    def planner(self):
        """Lazy-load the LLM planner to avoid import cost if not needed."""
        if self._planner is None and not self._planner_init_attempted:
            self._planner_init_attempted = True
            try:
                from lyra.agent.llm_planner import LLMPlanner
                self._planner = LLMPlanner()
            except Exception:
                self._planner = None
        return self._planner

    @property
    def llm_available(self) -> bool:
        """Check if LLM routing is available."""
        return self.planner is not None and self.planner.is_available

    def classify_intent(self, user_input: str, screen_context: Optional[Dict] = None) -> Tuple[str, Any]:
        """
        Classify user intent using LLM (primary) or keywords (fallback).

        Returns:
            For LLM mode:  ("ACTION", plan_dict) or ("QUESTION", question_str)
            For keyword mode: ("ACTION", keyword_str) or ("QUESTION", keyword_str)
        """
        if self.llm_available:
            try:
                plan = self.planner.plan(user_input, screen_context)
                intent = plan.get("intent", "QUESTION")

                if intent == "ACTION":
                    return "ACTION", plan
                elif intent == "QUESTION":
                    return "QUESTION", plan.get("question", user_input)
                else:
                    return "QUESTION", user_input
            except Exception as e:
                print(f"  [ROUTER] LLM classification failed ({e}), falling back to keywords")

        # Keyword fallback
        return classify_intent_keyword(user_input)

    def clear_memory(self):
        """Clear conversation memory in the LLM planner."""
        if self.planner:
            self.planner.clear_memory()


# Keep backward-compatible function for existing code
def classify_intent(user_input: str) -> Tuple[str, str]:
    """
    Backward-compatible intent classifier.
    Uses keyword-based classification (no screen context).
    For the full LLM-powered classification, use HybridRouter.classify_intent().
    """
    return classify_intent_keyword(user_input)
