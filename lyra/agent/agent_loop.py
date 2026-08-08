"""
agent_loop.py — Main perception-action loop: screenshot -> perceive -> decide -> act -> verify.

Supports two execution modes:
  1. STATIC: Execute predefined TaskDefinitions (legacy, from tasks.py)
  2. DYNAMIC: Execute LLM-generated action plans (new, from llm_planner)

This is the core agent execution engine that runs task step sequences and
handles failures, retries, and logging.
"""

import time
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from lyra.inference.coordinator import ActionCoordinator
from lyra.agent.tasks import TaskDefinition, get_task, list_tasks
from lyra.agent.primitives import (
    Primitive, TapElement, PressHome, PressBack, SwipeScreen,
    TypeText, WaitForScreen, WaitForElement, VerifyAction, TapCoordinates,
    LaunchApp, FindByText, TapByText, ScrollToFind, WaitForText,
)
from lyra.config import LOGS_DIR, FAILURES_DIR


# ── Dynamic step builder: converts LLM plan JSON → Primitive objects ──

def build_primitives_from_plan(steps: List[Dict]) -> List[Primitive]:
    """
    Converts a list of LLM-generated step dicts into executable Primitive objects.

    Example input:
      [
        {"action": "HOME"},
        {"action": "LAUNCH_APP", "app_name": "instagram"},
        {"action": "TAP_BY_TEXT", "text": "Search"},
        {"action": "TYPE", "text": "sunset photos"},
      ]
    """
    primitives = []

    for step in steps:
        action = step.get("action", "").upper()

        if action == "HOME":
            primitives.append(PressHome(settle=step.get("settle", 0.5)))

        elif action == "BACK":
            primitives.append(PressBack(settle=step.get("settle", 0.5)))

        elif action == "LAUNCH_APP":
            app_name = step.get("app_name", "")
            primitives.append(LaunchApp(app_name, settle=step.get("settle", 2.0)))

        elif action == "TAP":
            label = step.get("label", "")
            index = step.get("index", 0)
            primitives.append(TapElement(label, index=index, settle=step.get("settle", 1.0)))

        elif action == "TAP_BY_TEXT":
            text = step.get("text", "")
            primitives.append(TapByText(text, settle=step.get("settle", 1.0)))

        elif action == "TAP_XY":
            x = step.get("x", 0)
            y = step.get("y", 0)
            primitives.append(TapCoordinates(x, y, settle=step.get("settle", 0.5)))

        elif action == "SWIPE":
            direction = step.get("direction", "up")
            primitives.append(SwipeScreen(direction=direction, settle=step.get("settle", 0.5)))

        elif action == "TYPE":
            text = step.get("text", "")
            primitives.append(TypeText(text, settle=step.get("settle", 0.5)))

        elif action == "WAIT_FOR_TEXT":
            text = step.get("text", "")
            timeout = step.get("timeout", 10.0)
            primitives.append(WaitForText(text, timeout=timeout))

        elif action == "WAIT_SCREEN":
            state = step.get("target_state", step.get("expected_state", ""))
            timeout = step.get("timeout", 10.0)
            primitives.append(WaitForScreen(state, timeout=timeout))

        elif action == "WAIT_ELEMENT":
            label = step.get("label", "")
            timeout = step.get("timeout", 10.0)
            primitives.append(WaitForElement(label, timeout=timeout))

        elif action == "FIND_BY_TEXT":
            text = step.get("text", "")
            primitives.append(FindByText(text, timeout=step.get("timeout", 5.0)))

        elif action == "SCROLL_TO_FIND":
            text = step.get("text", "")
            direction = step.get("direction", "up")
            primitives.append(ScrollToFind(text, direction=direction, settle=step.get("settle", 1.0)))

        elif action == "VERIFY":
            expected_state = step.get("expected_state", None)
            expected_element = step.get("expected_element", None)
            absent_element = step.get("absent_element", None)
            primitives.append(VerifyAction(
                expected_state=expected_state,
                expected_element=expected_element,
                absent_element=absent_element,
            ))

        else:
            # Unknown action — skip with a warning
            print(f"  [WARNING] Unknown action '{action}' in LLM plan, skipping.")

    return primitives


class AgentLoop:
    """
    Executes task definitions step-by-step with perception, action, and verification.
    Logs all actions and captures failure screenshots for later retraining.

    Supports both static TaskDefinitions and dynamic LLM-generated plans.
    """

    def __init__(self, conf_threshold: float = 0.3, max_retries: int = 2):
        self.coordinator = ActionCoordinator(conf_threshold=conf_threshold)
        self.max_retries = max_retries
        self.action_log: List[Dict[str, Any]] = []

    def run_task(self, task_name: str) -> Dict[str, Any]:
        """
        Executes a registered task by name (static mode).
        Returns a summary dict with success status and step results.
        """
        task = get_task(task_name)
        return self.execute_task(task)

    def run_dynamic_plan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes a dynamic LLM-generated action plan.

        Args:
            plan: Dict with 'task_name', 'description', 'steps' (list of step dicts)

        Returns:
            A summary dict with success status and step results.
        """
        task_name = plan.get("task_name", "dynamic_task")
        description = plan.get("description", "LLM-generated action plan")
        steps_data = plan.get("steps", [])

        # Convert LLM plan steps to Primitive objects
        primitives = build_primitives_from_plan(steps_data)

        if not primitives:
            return {
                "task_name": task_name,
                "started_at": datetime.now().isoformat(),
                "finished_at": datetime.now().isoformat(),
                "steps": [],
                "success": False,
                "error": "No executable steps in plan.",
            }

        # Wrap as a TaskDefinition for uniform execution
        task = TaskDefinition(
            name=task_name,
            description=description,
            steps=primitives,
        )
        return self.execute_task(task)

    def execute_task(self, task: TaskDefinition) -> Dict[str, Any]:
        """
        Executes a TaskDefinition step-by-step.
        Returns a summary dict with success status and step results.
        """
        print(f"\n{'='*55}")
        print(f"  LYRA AGENT: Executing task '{task.name}'")
        print(f"  {task.description}")
        print(f"{'='*55}\n")

        task_result = {
            "task_name": task.name,
            "started_at": datetime.now().isoformat(),
            "steps": [],
            "success": True,
        }

        for i, step in enumerate(task.steps):
            step_label = f"Step {i+1}/{len(task.steps)}: {step.name}"
            target = getattr(step, 'label', getattr(step, 'target_state', getattr(step, 'text', '')))
            print(f"  [{step_label}] target={target} ...", end=" ")

            result = None
            for attempt in range(self.max_retries + 1):
                try:
                    result = step.execute(self.coordinator)
                except Exception as e:
                    result = {
                        "action": step.name,
                        "success": False,
                        "error": str(e),
                    }

                if result.get("success", False):
                    break

                if attempt < self.max_retries:
                    print(f"RETRY({attempt+1}) ...", end=" ")
                    time.sleep(1.0)

            success = result.get("success", False)
            print("OK" if success else "FAILED")

            step_entry = {
                "step_index": i,
                "primitive": step.name,
                "target": target,
                "success": success,
                "timestamp": datetime.now().isoformat(),
            }

            if not success:
                step_entry["error"] = result.get("error", "Action failed")
                task_result["success"] = False

                # Capture failure screenshot for retraining
                self._record_failure(task.name, step.name, target, result)

            task_result["steps"].append(step_entry)
            self.action_log.append(step_entry)

            # If a step fails and it's critical (not VERIFY), stop the task
            if not success and step.name not in ("VERIFY",):
                print(f"\n  [ABORT] Task '{task.name}' aborted at step {i+1}")
                break

        task_result["finished_at"] = datetime.now().isoformat()

        # Log the task result
        self._save_task_log(task_result)

        status = "COMPLETED" if task_result["success"] else "FAILED"
        print(f"\n  Task '{task.name}': {status}")
        print(f"{'='*55}\n")

        return task_result

    def _record_failure(self, task_name: str, step_name: str, target: str, result: Dict):
        """Captures a failure screenshot and saves metadata for retraining."""
        try:
            FAILURES_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            fname = f"fail_{task_name}_{step_name}_{ts}"

            # Save screenshot
            if self.coordinator._last_screenshot is not None:
                import cv2
                cv2.imwrite(
                    str(FAILURES_DIR / f"{fname}.png"),
                    self.coordinator._last_screenshot
                )

            # Save metadata
            meta = {
                "task": task_name,
                "step": step_name,
                "target": target,
                "error": result.get("error", "unknown"),
                "timestamp": ts,
            }
            with open(FAILURES_DIR / f"{fname}.json", "w") as f:
                json.dump(meta, f, indent=2)

        except Exception:
            pass  # Don't let failure recording crash the agent

    def _save_task_log(self, task_result: Dict):
        """Saves the task execution log to the logs directory."""
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = LOGS_DIR / f"task_{task_result['task_name']}_{ts}.json"
        with open(log_path, "w") as f:
            json.dump(task_result, f, indent=2)

    def get_available_tasks(self) -> List[str]:
        """Returns a list of all registered task names."""
        return list_tasks()


if __name__ == "__main__":
    import sys
    agent = AgentLoop()

    if len(sys.argv) > 1:
        task_name = sys.argv[1]
        agent.run_task(task_name)
    else:
        print("Available tasks:")
        for t in agent.get_available_tasks():
            print(f"  - {t}")
        print("\nUsage: python -m lyra.agent.agent_loop <task_name>")
