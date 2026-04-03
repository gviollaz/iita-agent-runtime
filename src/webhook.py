"""Meta Webhook Handler — unified receiver for WhatsApp, Instagram, Messenger.

Replaces 7 Make.com INPUT scenarios with a single endpoint.

Meta sends all events (WA, IG, Messenger) to the same webhook URL.
The payload structure differs by platform but we normalize everything
into a common InboundMessage format before processing.
"""
import os
import hmac
import hashlib
from dataclasses import dataclass
from enum import Enum

META_VERIFY_TOKEN = os.environ.get("META_VERIFY_TOKEN", "iita_v4_webhook_2026")
META_APP_SECRET = os.environ.get("META_APP_SECRET", "")


class Platform(str, Enum):
    WHATSAPP = "whatsapp"
    INSTAGRAM = "instagram"
    MESSENGER = "messenger"


class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"
    STICKER = "sticker"
    LOCATION = "location"
    REACTION = "reaction"
    BUTTON_REPLY = "button_reply"
    UNKNOWN = "unknown"


@dataclass
class InboundMessage:
    """Normalized inbound message from any Meta platform."""
    platform: Platform
    sender_id: str           # WA: phone number, IG/Messenger: PSID
    recipient_id: str        # WA: phone_number_id, IG: ig_user_id, Messenger: page_id
    message_id: str          # External message ID from Meta
    message_type: MessageType
    text: str | None = None
    media_url: str | None = None
    media_mime: str | None = None
    caption: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    reaction_emoji: str | None = None
    context_message_id: str | None = None  # Reply-to
    timestamp: str | None = None
    raw_payload: dict | None = None


def verify_webhook(mode: str, token: str, challenge: str) -> str | None:
    """Verify Meta webhook subscription. Returns challenge if valid."""
    if mode == "subscribe" and token == META_VERIFY_TOKEN:
        return challenge
    return None


def verify_signature(payload: bytes, signature: str) -> bool:
    """Verify webhook payload signature from Meta."""
    if not META_APP_SECRET:
        return True  # Skip verification if secret not configured
    expected = hmac.new(META_APP_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


def parse_webhook(body: dict) -> list[InboundMessage]:
    """Parse Meta webhook payload into normalized messages.
    
    Meta sends different structures for WA vs IG vs Messenger.
    This function detects the platform and extracts messages.
    """
    messages = []
    obj = body.get("object", "")

    if obj == "whatsapp_business_account":
        messages.extend(_parse_whatsapp(body))
    elif obj == "instagram":
        messages.extend(_parse_instagram(body))
    elif obj == "page":
        messages.extend(_parse_messenger(body))

    return messages


def _parse_whatsapp(body: dict) -> list[InboundMessage]:
    """Parse WhatsApp Cloud API webhook."""
    messages = []
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            phone_number_id = value.get("metadata", {}).get("phone_number_id", "")
            
            for msg in value.get("messages", []):
                sender = msg.get("from", "")
                msg_id = msg.get("id", "")
                msg_type = msg.get("type", "unknown")
                ts = msg.get("timestamp", "")
                context_id = msg.get("context", {}).get("id") if msg.get("context") else None

                im = InboundMessage(
                    platform=Platform.WHATSAPP,
                    sender_id=sender,
                    recipient_id=phone_number_id,
                    message_id=msg_id,
                    message_type=_map_wa_type(msg_type),
                    timestamp=ts,
                    context_message_id=context_id,
                    raw_payload=msg,
                )

                if msg_type == "text":
                    im.text = msg.get("text", {}).get("body", "")
                elif msg_type in ("image", "video", "audio", "document", "sticker"):
                    media = msg.get(msg_type, {})
                    im.media_url = media.get("id", "")  # Media ID, needs Graph API to download
                    im.media_mime = media.get("mime_type", "")
                    im.caption = media.get("caption", "")
                elif msg_type == "location":
                    loc = msg.get("location", {})
                    im.latitude = loc.get("latitude")
                    im.longitude = loc.get("longitude")
                elif msg_type == "reaction":
                    im.reaction_emoji = msg.get("reaction", {}).get("emoji", "")
                    im.context_message_id = msg.get("reaction", {}).get("message_id", "")
                elif msg_type == "interactive":
                    interactive = msg.get("interactive", {})
                    itype = interactive.get("type", "")
                    if itype == "button_reply":
                        im.text = interactive.get("button_reply", {}).get("title", "")
                        im.message_type = MessageType.BUTTON_REPLY
                    elif itype == "list_reply":
                        im.text = interactive.get("list_reply", {}).get("title", "")
                        im.message_type = MessageType.BUTTON_REPLY
                elif msg_type == "button":
                    im.text = msg.get("button", {}).get("text", "")
                    im.message_type = MessageType.BUTTON_REPLY

                messages.append(im)

            # Also handle status updates (delivered, read, etc.) — skip for now

    return messages


def _parse_instagram(body: dict) -> list[InboundMessage]:
    """Parse Instagram Messaging API webhook."""
    messages = []
    for entry in body.get("entry", []):
        for messaging in entry.get("messaging", []):
            sender = messaging.get("sender", {}).get("id", "")
            recipient = messaging.get("recipient", {}).get("id", "")
            ts = str(messaging.get("timestamp", ""))
            msg = messaging.get("message", {})

            if not msg:
                continue  # Skip non-message events (postback, etc.)

            msg_id = msg.get("mid", "")

            im = InboundMessage(
                platform=Platform.INSTAGRAM,
                sender_id=sender,
                recipient_id=recipient,
                message_id=msg_id,
                message_type=MessageType.TEXT,
                timestamp=ts,
                raw_payload=messaging,
            )

            if msg.get("text"):
                im.text = msg["text"]
            elif msg.get("attachments"):
                att = msg["attachments"][0]
                att_type = att.get("type", "")
                im.media_url = att.get("payload", {}).get("url", "")
                im.message_type = _map_ig_attachment(att_type)
                if att_type == "share":
                    im.text = att.get("payload", {}).get("url", "")

            # Handle reply-to
            if msg.get("reply_to"):
                im.context_message_id = msg["reply_to"].get("mid", "")

            messages.append(im)
    return messages


def _parse_messenger(body: dict) -> list[InboundMessage]:
    """Parse Facebook Messenger webhook."""
    messages = []
    for entry in body.get("entry", []):
        for messaging in entry.get("messaging", []):
            sender = messaging.get("sender", {}).get("id", "")
            recipient = messaging.get("recipient", {}).get("id", "")
            ts = str(messaging.get("timestamp", ""))
            msg = messaging.get("message", {})

            if not msg or msg.get("is_echo"):
                continue  # Skip echo and non-message events

            msg_id = msg.get("mid", "")

            im = InboundMessage(
                platform=Platform.MESSENGER,
                sender_id=sender,
                recipient_id=recipient,
                message_id=msg_id,
                message_type=MessageType.TEXT,
                timestamp=ts,
                raw_payload=messaging,
            )

            if msg.get("text"):
                im.text = msg["text"]
            elif msg.get("attachments"):
                att = msg["attachments"][0]
                att_type = att.get("type", "")
                im.media_url = att.get("payload", {}).get("url", "")
                im.message_type = _map_ig_attachment(att_type)

            if msg.get("reply_to"):
                im.context_message_id = msg["reply_to"].get("mid", "")

            messages.append(im)
    return messages


def _map_wa_type(t: str) -> MessageType:
    return {"text": MessageType.TEXT, "image": MessageType.IMAGE,
            "audio": MessageType.AUDIO, "video": MessageType.VIDEO,
            "document": MessageType.DOCUMENT, "sticker": MessageType.STICKER,
            "location": MessageType.LOCATION, "reaction": MessageType.REACTION,
            }.get(t, MessageType.UNKNOWN)

def _map_ig_attachment(t: str) -> MessageType:
    return {"image": MessageType.IMAGE, "audio": MessageType.AUDIO,
            "video": MessageType.VIDEO, "file": MessageType.DOCUMENT,
            }.get(t, MessageType.UNKNOWN)
