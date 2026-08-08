"""Atomic WhatsApp actions using Android UIAutomator and ADB."""

from __future__ import annotations

import time
import re

from gitd.bots.common.adb import input_text_arg
from gitd.skills.base import Action, ActionResult

WHATSAPP_PACKAGE = "com.whatsapp"


def _tap_first(device, xml: str, *locators: tuple[str, str]) -> tuple[int, int] | None:
    """Find and tap the first matching (attribute, value) locator."""
    for attribute, value in locators:
        bounds = device.find_bounds(xml, **{attribute: value})
        if bounds:
            pos = device.bounds_center(bounds)
            device.tap(*pos)
            return pos
    return None


def _find_text_bounds(device, xml: str, wanted: str) -> str | None:
    """Find a visible text node case-insensitively."""
    wanted = wanted.casefold()
    for node in re.finditer(r'<node[^>]*text="([^"]*)"[^>]*bounds="([^"]+)"[^>]*>', xml or ""):
        if node.group(1).casefold() == wanted:
            return node.group(2)
    return None


class SearchContact(Action):
    name = "search_contact"
    description = "Search WhatsApp for a contact and open the matching chat"

    def __init__(self, device, elements, *, contact: str = "", **kwargs):
        super().__init__(device, elements)
        self.contact = str(contact).strip()

    def execute(self) -> ActionResult:
        if not self.contact:
            return ActionResult(success=False, error="No WhatsApp contact provided")

        xml = self.device.dump_xml()
        pos = _tap_first(
            self.device,
            xml,
            ("content_desc", "Search"),
            ("content_desc", "Ask Meta AI or Search"),
            ("resource_id", f"{WHATSAPP_PACKAGE}:id/search_bar_inner_layout"),
            ("resource_id", f"{WHATSAPP_PACKAGE}:id/menuitem_search"),
        )
        if not pos:
            return ActionResult(success=False, error="WhatsApp search button not found")
        time.sleep(0.8)

        xml = self.device.dump_xml()
        input_pos = _tap_first(
            self.device,
            xml,
            ("resource_id", f"{WHATSAPP_PACKAGE}:id/search_input"),
            ("resource_id", f"{WHATSAPP_PACKAGE}:id/search_src_text"),
            ("content_desc", "Search"),
        )
        if not input_pos:
            return ActionResult(success=False, error="WhatsApp contact search field not found")

        self.device.adb("shell", "input", "text", input_text_arg(self.contact))
        time.sleep(1.2)
        xml = self.device.dump_xml()
        contact_bounds = _find_text_bounds(self.device, xml, self.contact)
        if not contact_bounds:
            return ActionResult(success=False, error=f"WhatsApp contact not found: {self.contact}")

        pos = self.device.bounds_center(contact_bounds)
        self.device.tap(*pos)
        time.sleep(1.2)
        return ActionResult(success=True, data={"contact": self.contact, "position": pos})


class TypeMessage(Action):
    name = "type_message"
    description = "Type a message into the open WhatsApp chat"

    def __init__(self, device, elements, *, message: str = "", **kwargs):
        super().__init__(device, elements)
        self.message = str(message)

    def execute(self) -> ActionResult:
        if not self.message:
            return ActionResult(success=False, error="No WhatsApp message provided")
        xml = self.device.dump_xml()
        pos = _tap_first(
            self.device,
            xml,
            ("resource_id", f"{WHATSAPP_PACKAGE}:id/entry"),
            ("content_desc", "Type a message"),
        )
        if not pos:
            return ActionResult(success=False, error="WhatsApp message field not found")

        try:
            if self.message.isascii():
                self.device.adb("shell", "input", "text", input_text_arg(self.message))
            else:
                self.device.type_unicode(self.message)
        except Exception:
            fallback = self.message.encode("ascii", "ignore").decode()
            self.device.adb("shell", "input", "text", input_text_arg(fallback))
        time.sleep(0.5)
        return ActionResult(success=True, data={"message_length": len(self.message)})


class SendMessage(Action):
    name = "send_message"
    description = "Tap WhatsApp's Send button"
    max_retries = 1

    def execute(self) -> ActionResult:
        xml = self.device.dump_xml()
        pos = _tap_first(
            self.device,
            xml,
            ("content_desc", "Send"),
            ("resource_id", f"{WHATSAPP_PACKAGE}:id/send"),
        )
        if not pos:
            return ActionResult(success=False, error="WhatsApp Send button not found")
        time.sleep(1)
        return ActionResult(success=True, data={"sent": True, "position": pos})
