"""WhatsApp skill for sending messages on Android."""

from pathlib import Path

from gitd.skills.base import Skill

_SKILL_DIR = Path(__file__).parent


def load() -> Skill:
    """Load WhatsApp actions and workflows."""
    from gitd.skills.whatsapp.actions import SearchContact, SendMessage, TypeMessage
    from gitd.skills.whatsapp.workflows.send_message import SendWhatsAppMessage

    skill = Skill(_SKILL_DIR)
    for action in (SearchContact, TypeMessage, SendMessage):
        skill.register_action(action)
    skill.register_workflow(SendWhatsAppMessage)
    return skill
