"""
responder.py — Generate human-readable text responses for actions and questions.

Formats action results and Q&A responses into clean text for the user.
"""

from typing import Dict, Any, Optional
from lyra.assistant.grok_client import grok


class Responder:
    """Generates human-readable responses for the LYRA agent."""

    def format_action_result(self, task_result: Dict[str, Any]) -> str:
        """Formats a task execution result into a readable summary."""
        task_name = task_result.get("task_name", "unknown")
        success = task_result.get("success", False)
        steps = task_result.get("steps", [])

        if success:
            lines = [f"Done! Task '{task_name}' completed successfully."]
        else:
            lines = [f"Task '{task_name}' encountered issues."]

        passed = sum(1 for s in steps if s.get("success"))
        total = len(steps)
        lines.append(f"  Steps completed: {passed}/{total}")

        for step in steps:
            status = "OK" if step.get("success") else "FAILED"
            lines.append(f"  - {step.get('primitive', '?')} -> {step.get('target', '?')}: {status}")

            if not step.get("success") and step.get("error"):
                lines.append(f"    Error: {step['error']}")

        return "\n".join(lines)

    def answer_question(self, question: str) -> str:
        """Routes a question to the Grok API and returns the response."""
        return grok.ask(question)

    def format_perception(self, perception: Dict) -> str:
        """Formats a perception result into readable text."""
        state = perception.get("screen_state", "UNKNOWN")
        conf = perception.get("screen_confidence", 0.0)
        dets = perception.get("detections", [])

        lines = [
            f"Current Screen: {state} ({conf:.0%} confidence)",
            f"UI Elements Detected: {len(dets)}",
        ]

        for d in dets[:10]:
            lines.append(
                f"  - {d['label']} ({d['confidence']:.0%}) "
                f"at [{d['bbox_original'][0]},{d['bbox_original'][1]},"
                f"{d['bbox_original'][2]},{d['bbox_original'][3]}]"
            )

        if len(dets) > 10:
            lines.append(f"  ... and {len(dets) - 10} more")

        return "\n".join(lines)
