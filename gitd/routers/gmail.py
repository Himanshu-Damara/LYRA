"""Google OAuth and Gmail API integration, independent of Android control."""

import base64
import html
import json
import os
import secrets
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parseaddr
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from cryptography.fernet import Fernet, InvalidToken

router = APIRouter(prefix="/api/gmail", tags=["gmail"])
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send"
_oauth_states: dict[str, float] = {}


class SendEmailRequest(BaseModel):
    to: str = Field(min_length=3, max_length=320)
    subject: str = Field(min_length=1, max_length=998)
    body: str = Field(min_length=1, max_length=100000)


class AssistantRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=10000)


def _settings():
    from gitd.config import settings
    return settings


def _configured() -> bool:
    s = _settings()
    return bool(s.google_client_id.strip() and s.google_client_secret.strip())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fernet() -> Fernet:
    """Use a local key file so refresh tokens never enter the frontend or DB plaintext."""
    from gitd.config import settings

    key_path = settings.base_dir / "data" / "gmail_token.key"
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if key_path.exists():
        key = key_path.read_bytes().strip()
    else:
        key = Fernet.generate_key()
        key_path.write_bytes(key)
    return Fernet(key)


def _connection(db):
    from gitd.models.gmail import GmailConnection
    return db.query(GmailConnection).order_by(GmailConnection.id.desc()).first()


@router.get("/status", summary="Gmail OAuth Status")
def gmail_status():
    from gitd.models.base import SessionLocal

    db = SessionLocal()
    try:
        connection = _connection(db)
        return {"configured": _configured(), "connected": connection is not None, "email": connection.email if connection else ""}
    finally:
        db.close()


@router.get("/oauth/start", summary="Start Gmail OAuth")
def gmail_oauth_start():
    if not _configured():
        raise HTTPException(status_code=503, detail="Gmail OAuth is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.")
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = time.time() + 600
    s = _settings()
    params = {
        "client_id": s.google_client_id, "redirect_uri": s.google_redirect_uri,
        "response_type": "code", "scope": GMAIL_SCOPE, "access_type": "offline",
        "prompt": "consent", "include_granted_scopes": "true", "state": state,
    }
    return {"authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)}


@router.get("/oauth/callback", response_class=HTMLResponse, summary="Complete Gmail OAuth")
def gmail_oauth_callback(code: str = Query(""), state: str = Query(""), error: str = Query("")):
    if error:
        return HTMLResponse(f"<h2>Gmail connection cancelled</h2><p>{html.escape(error)}</p><p>You can close this window.</p>", status_code=400)
    expires = _oauth_states.pop(state, 0)
    if not state or expires < time.time():
        return HTMLResponse("<h2>Gmail connection failed</h2><p>OAuth state expired. Start again from LYRA.</p>", status_code=400)
    if not code:
        return HTMLResponse("<h2>Gmail connection failed</h2><p>Google did not return an authorization code.</p>", status_code=400)
    s = _settings()
    token_response = requests.post("https://oauth2.googleapis.com/token", data={
        "code": code, "client_id": s.google_client_id, "client_secret": s.google_client_secret,
        "redirect_uri": s.google_redirect_uri, "grant_type": "authorization_code",
    }, timeout=20)
    if not token_response.ok:
        return HTMLResponse("<h2>Gmail connection failed</h2><p>Google token exchange was rejected.</p>", status_code=502)
    token = token_response.json()
    refresh_token = token.get("refresh_token")
    if not refresh_token:
        return HTMLResponse("<h2>Gmail connection failed</h2><p>Google did not return an offline refresh token. Try connecting again.</p>", status_code=502)
    profile = requests.get("https://gmail.googleapis.com/gmail/v1/users/me/profile", headers={"Authorization": f"Bearer {token.get('access_token', '')}"}, timeout=20)
    if not profile.ok:
        return HTMLResponse("<h2>Gmail connection failed</h2><p>Could not verify the Gmail account.</p>", status_code=502)
    email = profile.json().get("emailAddress", "")
    if not email:
        return HTMLResponse("<h2>Gmail connection failed</h2><p>Google returned no Gmail address.</p>", status_code=502)
    from gitd.models.base import SessionLocal
    from gitd.models.gmail import GmailConnection
    db = SessionLocal()
    try:
        connection = _connection(db) or GmailConnection(email=email, refresh_token_encrypted="", created_at=_now(), updated_at=_now())
        connection.email = email
        connection.refresh_token_encrypted = _fernet().encrypt(refresh_token.encode()).decode()
        connection.token_expiry = int(time.time()) + int(token.get("expires_in", 3600))
        connection.updated_at = _now()
        db.add(connection); db.commit()
    finally:
        db.close()
    return HTMLResponse("<h2>Gmail connected</h2><p>Your Gmail account is connected to LYRA. You may close this window.</p>")


@router.delete("/connection", summary="Disconnect Gmail")
def disconnect_gmail():
    from gitd.models.base import SessionLocal
    db = SessionLocal()
    try:
        connection = _connection(db)
        if connection:
            db.delete(connection); db.commit()
        return {"ok": True, "connected": False}
    finally:
        db.close()


def _access_token(connection) -> str:
    s = _settings()
    try:
        refresh_token = _fernet().decrypt(connection.refresh_token_encrypted.encode()).decode()
    except InvalidToken as exc:
        raise HTTPException(status_code=500, detail="Stored Gmail token cannot be decrypted; reconnect Gmail.") from exc
    response = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": s.google_client_id, "client_secret": s.google_client_secret,
        "refresh_token": refresh_token, "grant_type": "refresh_token",
    }, timeout=20)
    if not response.ok:
        raise HTTPException(status_code=401, detail="Gmail authorization expired or was revoked; reconnect Gmail.")
    return response.json().get("access_token", "")


def _gmail_get(connection, path: str, params: dict | None = None) -> dict:
    token = _access_token(connection)
    response = requests.get(
        f"https://gmail.googleapis.com/gmail/v1/users/me/{path}",
        headers={"Authorization": f"Bearer {token}"}, params=params or {}, timeout=30,
    )
    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="Gmail authorization expired or was revoked; reconnect Gmail.")
    if not response.ok:
        raise HTTPException(status_code=502, detail="Gmail API request failed.")
    return response.json()


def _header(message: dict, name: str) -> str:
    for item in message.get("payload", {}).get("headers", []):
        if item.get("name", "").lower() == name.lower():
            return item.get("value", "")
    return ""


def _decode_part(part: dict) -> str:
    data = (part.get("body") or {}).get("data")
    if data:
        try:
            return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")
        except (ValueError, UnicodeDecodeError):
            return ""
    return "".join(_decode_part(child) for child in part.get("parts", []) if child.get("mimeType") == "text/plain")


def _search_mail(connection, query: str, max_results: int = 10) -> list[dict]:
    listing = _gmail_get(connection, "messages", {"q": query, "maxResults": min(max_results, 50)})
    results = []
    for item in listing.get("messages", [])[:max_results]:
        message = _gmail_get(connection, f"messages/{item['id']}", {"format": "metadata", "metadataHeaders": ["From", "To", "Subject", "Date"]})
        results.append({"id": item["id"], "thread_id": item.get("threadId", ""), "from": _header(message, "From"), "to": _header(message, "To"), "subject": _header(message, "Subject"), "date": _header(message, "Date"), "snippet": message.get("snippet", "")})
    return results


def _read_mail(connection, message_id: str) -> dict:
    message = _gmail_get(connection, f"messages/{message_id}", {"format": "full"})
    return {"id": message_id, "from": _header(message, "From"), "to": _header(message, "To"), "subject": _header(message, "Subject"), "date": _header(message, "Date"), "body": _decode_part(message.get("payload", {}))[:20000]}


@router.get("/messages", summary="Search Gmail Messages")
def search_gmail_messages(query: str = Query("", max_length=500), max_results: int = Query(10, ge=1, le=50)):
    from gitd.models.base import SessionLocal
    db = SessionLocal()
    try:
        connection = _connection(db)
        if not connection:
            raise HTTPException(status_code=401, detail="Connect a Google account before reading Gmail messages.")
        return {"messages": _search_mail(connection, query, max_results)}
    finally:
        db.close()


@router.post("/assistant", summary="Use AI With Gmail")
def gmail_assistant(request: AssistantRequest):
    """Let Grok search/read mail and prepare a draft, without sending it."""
    from openai import OpenAI
    from gitd.config import settings
    from gitd.models.base import SessionLocal

    db = SessionLocal()
    try:
        connection = _connection(db)
        if not connection:
            raise HTTPException(status_code=401, detail="Connect a Google account before using the Gmail assistant.")
        api_key = os.environ.get("GROK_API_KEY") or os.environ.get("GROQ_API_KEY") or settings.grok_api_key
        if not api_key:
            raise HTTPException(status_code=503, detail="Grok is not configured on the server.")
        client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        messages = [
            {"role": "system", "content": "You are LYRA's Gmail assistant. You may search and read the user's Gmail to answer requests. When asked to write an email, use gmail_prepare_draft. Never send an email and never delete or modify mail."},
            {"role": "user", "content": request.prompt},
        ]
        tools = [
            {"type": "function", "function": {"name": "gmail_search", "description": "Search Gmail using Gmail search syntax. Empty query returns recent messages.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "max_results": {"type": "integer", "minimum": 1, "maximum": 20}}, "required": ["query"]}}},
            {"type": "function", "function": {"name": "gmail_read", "description": "Read one Gmail message by id returned by gmail_search.", "parameters": {"type": "object", "properties": {"message_id": {"type": "string"}}, "required": ["message_id"]}}},
            {"type": "function", "function": {"name": "gmail_prepare_draft", "description": "Prepare an email draft for the user to review. This never sends it.", "parameters": {"type": "object", "properties": {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}}, "required": ["to", "subject", "body"]}}},
        ]
        draft = None
        for _ in range(8):
            response = client.chat.completions.create(model=settings.grok_model, messages=messages, tools=tools, tool_choice="auto", max_tokens=2500, timeout=120)
            message = response.choices[0].message
            calls = getattr(message, "tool_calls", None) or []
            if not calls:
                return {"reply": message.content or "", "draft": draft}
            messages.append({"role": "assistant", "content": message.content or "", "tool_calls": [{"id": call.id, "type": "function", "function": {"name": call.function.name, "arguments": call.function.arguments}} for call in calls]})
            for call in calls:
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                if call.function.name == "gmail_search":
                    result = _search_mail(connection, str(args.get("query", "")), int(args.get("max_results", 10)))
                elif call.function.name == "gmail_read":
                    result = _read_mail(connection, str(args.get("message_id", "")))
                elif call.function.name == "gmail_prepare_draft":
                    draft = {"to": str(args.get("to", "")), "subject": str(args.get("subject", "")), "body": str(args.get("body", ""))}
                    result = {"draft_prepared": True, "to": draft["to"], "subject": draft["subject"]}
                else:
                    result = {"error": "Unknown Gmail tool"}
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)[:20000]})
        raise HTTPException(status_code=502, detail="Gmail assistant reached its tool-call limit.")
    finally:
        db.close()


@router.post("/send", summary="Send Gmail Message")
def send_gmail_message(request: SendEmailRequest):
    from gitd.models.base import SessionLocal

    db = SessionLocal()
    try:
        connection = _connection(db)
        if not connection:
            raise HTTPException(status_code=401, detail="Connect a Google account before sending Gmail messages.")
        parsed_address = parseaddr(request.to)[1]
        if parsed_address != request.to.strip() or "@" not in parsed_address or parsed_address.startswith("@") or parsed_address.endswith("@"):
            raise HTTPException(status_code=422, detail="to must be a valid email address")
        token = _access_token(connection)
        message = EmailMessage()
        message["To"] = str(request.to)
        message["Subject"] = request.subject
        message.set_content(request.body)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode().rstrip("=")
        response = requests.post("https://gmail.googleapis.com/gmail/v1/users/me/messages/send", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, json={"raw": raw}, timeout=30)
        if response.status_code == 401:
            raise HTTPException(status_code=401, detail="Gmail authorization expired or was revoked; reconnect Gmail.")
        if not response.ok:
            raise HTTPException(status_code=502, detail="Gmail rejected the message.")
        return {"ok": True, "message_id": response.json().get("id", ""), "to": str(request.to)}
    finally:
        db.close()
