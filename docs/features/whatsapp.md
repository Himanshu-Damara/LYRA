# WhatsApp skill

The built-in `whatsapp` Android skill sends a message to a contact through the
normal WhatsApp UI. It does not use WhatsApp's private APIs.

## Workflow

`send_message` launches WhatsApp through the standard skill engine, searches for
the requested contact, opens the chat, types the message, and taps Send.

Example parameters:

```json
{
  "contact": "John",
  "message": "Hello, I will call you later."
}
```

Requirements: WhatsApp must be installed and logged in, the contact must be
searchable, and the Android device must be connected through ADB.
