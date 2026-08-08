"""Workflow for sending one WhatsApp message."""

from gitd.skills.base import Action, EngineConfig, Workflow


class SendWhatsAppMessage(Workflow):
    name = "send_message"
    description = "Open WhatsApp, find a contact, type a message, and send it"
    # WhatsApp can be launched directly. Avoid the generic back-spam reset,
    # which can block on devices whose ADB input queue is busy.
    engine = EngineConfig(back_count=0, home_settle=0.5, launch_settle=2.0)

    def __init__(self, device, elements, *, contact: str = "", message: str = "", **kwargs):
        super().__init__(device, elements)
        self.contact = str(contact).strip()
        self.message = str(message)

    def _launch_app(self):
        """Always start from WhatsApp's conversation list, never an old chat."""
        self.device.adb("shell", "am", "force-stop", "com.whatsapp")
        super()._launch_app()

    def steps(self) -> list[Action]:
        from gitd.skills.whatsapp.actions import SearchContact, SendMessage, TypeMessage

        return [
            SearchContact(self.device, self.elements, contact=self.contact),
            TypeMessage(self.device, self.elements, message=self.message),
            SendMessage(self.device, self.elements),
        ]
