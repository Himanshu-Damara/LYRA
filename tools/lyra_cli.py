"""
lyra_cli.py — Main LYRA Agent CLI application.

Interactive command-line interface that accepts user commands,
routes them through the Hybrid Router (LLM-primary, keyword-fallback),
and displays results.

Supports:
  - Natural language phone actions (e.g., 'open instagram', 'send a message')
  - LLM-generated dynamic action plans (any command the LLM can understand)
  - Hardcoded task shortcuts (legacy TaskDefinition system)
  - Knowledge questions routed to Grok Q&A
  - Screen status inspection
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lyra.agent.router import HybridRouter, resolve_task_from_input
from lyra.agent.agent_loop import AgentLoop
from lyra.agent.tasks import list_tasks
from lyra.assistant.responder import Responder


def print_banner():
    print()
    print("  ╔══════════════════════════════════════╗")
    print("  ║   LYRA — AI Phone Assistant Agent    ║")
    print("  ║   Hybrid LLM + Vision Architecture   ║")
    print("  ╚══════════════════════════════════════╝")
    print()
    print("  Commands:")
    print("    - Type any phone action in natural language")
    print("      (e.g., 'open instagram', 'take a photo', 'open settings')")
    print("    - Ask a question (e.g., 'what is machine learning?')")
    print("    - Type 'tasks' to see built-in phone tasks")
    print("    - Type 'status' to see current phone screen state")
    print("    - Type 'mode' to see current routing mode (LLM or keyword)")
    print("    - Type 'clear' to clear conversation memory")
    print("    - Type 'quit' or 'exit' to stop")
    print()


def main():
    print_banner()

    agent = AgentLoop()
    responder = Responder()
    router = HybridRouter()

    # Show which mode is active
    if router.llm_available:
        print("  ✓ LLM Brain active (Groq API connected)")
        print("    → Full natural language understanding enabled")
    else:
        print("  ⚠ LLM Brain unavailable — using keyword fallback mode")
        print("    → Set GROK_API_KEY in .env to enable LLM routing")
    print()

    while True:
        try:
            user_input = input("  LYRA> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Goodbye!")
            break

        if not user_input:
            continue

        lower = user_input.lower()

        if lower in ("quit", "exit", "q"):
            print("  Goodbye!")
            break

        if lower == "tasks":
            print("\n  Built-in tasks:")
            for t in list_tasks():
                print(f"    - {t}")
            print()
            continue

        if lower == "status":
            try:
                perception = agent.coordinator.perceive()
                print()
                print(f"  {responder.format_perception(perception)}")

                # Also show accessibility data if available
                a11y = perception.get("accessibility_elements", [])
                if a11y:
                    print(f"\n  Accessibility elements ({len(a11y)}):")
                    for elem in a11y[:10]:
                        text = elem.get("text", "")
                        desc = elem.get("content_desc", "")
                        display = text or desc or "(no text)"
                        click = " [clickable]" if elem.get("clickable") else ""
                        print(f"    - \"{display}\"{click}")
                    if len(a11y) > 10:
                        print(f"    ... and {len(a11y) - 10} more")
                print()
            except Exception as e:
                print(f"\n  [ERROR] Could not read phone screen: {e}\n")
            continue

        if lower == "mode":
            mode = "LLM Brain (Groq API)" if router.llm_available else "Keyword Fallback"
            print(f"\n  Current routing mode: {mode}\n")
            continue

        if lower == "clear":
            router.clear_memory()
            print("\n  Conversation memory cleared.\n")
            continue

        # Get screen context for LLM routing (if LLM is available)
        screen_context = None
        if router.llm_available:
            try:
                screen_context = agent.coordinator.perceive()
            except Exception:
                pass  # Will work without screen context

        # Classify user intent via Hybrid Router
        intent_type, payload = router.classify_intent(user_input, screen_context)

        if intent_type == "ACTION":
            if isinstance(payload, dict) and "steps" in payload:
                # LLM-generated dynamic plan
                task_name = payload.get("task_name", "dynamic_task")
                reasoning = payload.get("reasoning", "")
                steps = payload.get("steps", [])

                print(f"\n  [LLM PLAN] {task_name}: {reasoning}")
                print(f"  Steps: {len(steps)}")
                for i, s in enumerate(steps):
                    action = s.get("action", "?")
                    detail = {k: v for k, v in s.items() if k != "action"}
                    detail_str = f" {detail}" if detail else ""
                    print(f"    {i+1}. {action}{detail_str}")
                print()

                result = agent.run_dynamic_plan(payload)
                print(f"\n  {responder.format_action_result(result)}\n")
            else:
                # Keyword-mode: try to resolve to a known task
                try:
                    task_name = resolve_task_from_input(user_input)
                    result = agent.run_task(task_name)
                    print(f"\n  {responder.format_action_result(result)}\n")
                except ValueError as e:
                    print(f"\n  [UNKNOWN TASK] {e}\n")
                except Exception as e:
                    print(f"\n  [ERROR] Action failed: {e}\n")

        elif intent_type == "QUESTION":
            answer = responder.answer_question(user_input)
            print(f"\n  LYRA: {answer}\n")


if __name__ == "__main__":
    main()
