"""Channel operations — complete pipeline from webhook to response.

Handles: resolve channel → find/create person → create interaction → send response.
During transition: writes to v3 DB. After full migration: writes to v4.
"""
import os
import json
from datetime import datetime
import httpx
from src.db import v3_rpc, v3_query, v3_insert, v3_update, v4_insert, v3_available
from src.webhook import InboundMessage, Platform, MessageType

# Meta Graph API tokens by channel
META_TOKENS = {
    10: os.environ.get("META_GRAPH_TOKEN", ""),           # WA Cloud API (ch10)
    5: os.environ.get("META_GRAPH_TOKEN_COEX", ""),       # WA Cursos Coex (ch5)
    4: os.environ.get("META_GRAPH_TOKEN_SL", ""),         # WA San Lorenzo (ch4)
    6: os.environ.get("META_GRAPH_TOKEN", ""),             # IG Salta (uses same token)
    7: os.environ.get("META_GRAPH_TOKEN_SL", ""),         # IG San Lorenzo
    8: os.environ.get("META_GRAPH_TOKEN", ""),             # Messenger Salta
    9: os.environ.get("META_GRAPH_TOKEN_SL", ""),         # Messenger San Lorenzo
}

# Channel mapping: Meta recipient_id → v3 channel_id
# WhatsApp uses phone_number_id, IG uses ig_user_id, Messenger uses page_id
CHANNEL_MAP = {
    "100436536473788": 10,    # ch10 Chatbot Cloud API
    "102522002867267": 4,     # ch4 San Lorenzo (Coex)
    "100651882782406": 5,     # ch5 IITA Cursos (Coex)
    "17841404168256335": 6,   # ch6 IG Salta
    "17841455198100771": 7,   # ch7 IG San Lorenzo
    "296373163870909": 8,     # ch8 Messenger Salta
    "106307535517599": 9,     # ch9 Messenger San Lorenzo
}


def resolve_channel_id(msg: InboundMessage) -> int | None:
    """Resolve v3 channel_id from the inbound message."""
    return CHANNEL_MAP.get(msg.recipient_id)


async def find_or_create_person(msg: InboundMessage, channel_id: int) -> dict | None:
    """Find existing person/conversation or create new ones.
    
    Returns dict with: person_id, conversation_id, person_conversation_id, 
                       system_conversation_id, is_new
    """
    if not v3_available():
        return None

    address = msg.sender_id

    # 1. Look for existing person_conversation by address
    pcs = await v3_query("person_conversation", "id,id_person,id_conversation,address",
                         f"address=eq.{address}")
    
    if pcs:
        pc = pcs[0]
        # Get system_conversation for this channel
        scs = await v3_query("system_conversation", "id",
                             f"id_conversation=eq.{pc['id_conversation']}&id_channel=eq.{channel_id}")
        return {
            "person_id": pc["id_person"],
            "conversation_id": pc["id_conversation"],
            "person_conversation_id": pc["id"],
            "system_conversation_id": scs[0]["id"] if scs else None,
            "is_new": False,
        }

    # 2. Create new person + conversation + person_conversation + system_conversation
    # Create person
    person = await v3_insert("persons", {
        "first_name": None,  # Will be enriched later
        "phone": address if msg.platform == Platform.WHATSAPP else None,
    })
    if not person:
        return None
    
    person_id = person["id"]

    # Create conversation
    conv = await v3_insert("conversations", {
        "start_date": datetime.utcnow().isoformat(),
        "last_activity_at": datetime.utcnow().isoformat(),
    })
    if not conv:
        return None
    
    conv_id = conv["id"]

    # Create person_conversation
    pc = await v3_insert("person_conversation", {
        "id_person": person_id,
        "id_conversation": conv_id,
        "address": address,
    })

    # Create system_conversation
    sc = await v3_insert("system_conversation", {
        "id_conversation": conv_id,
        "id_channel": channel_id,
    })

    return {
        "person_id": person_id,
        "conversation_id": conv_id,
        "person_conversation_id": pc["id"] if pc else None,
        "system_conversation_id": sc["id"] if sc else None,
        "is_new": True,
    }


async def create_inbound_interaction(msg: InboundMessage, conv_info: dict) -> dict | None:
    """Create an inbound interaction in v3 DB (same format as Make.com)."""
    if not v3_available() or not conv_info:
        return None

    data = {
        "id_person_conversation": conv_info["person_conversation_id"],
        "text": msg.text or f"[{msg.message_type.value}]",
        "external_ref": msg.message_id,
        "message_type": msg.message_type.value,
        "status": "preprocessed",
        "time_stamp": datetime.utcnow().isoformat(),
    }
    
    result = await v3_insert("interactions", data)
    
    # Update conversation last_activity
    if result:
        await v3_update("conversations",
            f"id=eq.{conv_info['conversation_id']}",
            {"last_activity_at": datetime.utcnow().isoformat()})
    
    return result


async def create_outbound_interaction(text: str, conv_info: dict) -> dict | None:
    """Create an outbound interaction in v3 DB (status=send triggers Make.com OUT)."""
    if not v3_available() or not conv_info:
        return None

    data = {
        "id_system_conversation": conv_info["system_conversation_id"],
        "text": text,
        "message_type": "text",
        "status": "send",  # Make.com OUT scenario picks this up
        "time_stamp": datetime.utcnow().isoformat(),
    }
    
    return await v3_insert("interactions", data)


async def send_whatsapp_message(phone: str, text: str, phone_number_id: str, token: str) -> dict | None:
    """Send WhatsApp message via Graph API directly (bypasses Make.com OUT)."""
    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": text}
    }
    async with httpx.AsyncClient() as c:
        r = await c.post(url, headers=headers, json=payload, timeout=15)
        return r.json() if r.status_code == 200 else {"error": r.text, "status": r.status_code}


async def send_instagram_message(recipient_id: str, text: str, token: str) -> dict | None:
    """Send Instagram DM via Graph API."""
    url = "https://graph.facebook.com/v19.0/me/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"recipient": {"id": recipient_id}, "message": {"text": text}}
    async with httpx.AsyncClient() as c:
        r = await c.post(url, headers=headers, json=payload, timeout=15)
        return r.json() if r.status_code == 200 else {"error": r.text, "status": r.status_code}


async def send_messenger_message(recipient_id: str, text: str, token: str) -> dict | None:
    """Send Messenger message via Graph API."""
    url = "https://graph.facebook.com/v19.0/me/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"recipient": {"id": recipient_id}, "message": {"text": text}}
    async with httpx.AsyncClient() as c:
        r = await c.post(url, headers=headers, json=payload, timeout=15)
        return r.json() if r.status_code == 200 else {"error": r.text, "status": r.status_code}


async def send_response(msg: InboundMessage, text: str, conv_info: dict, channel_id: int) -> dict | None:
    """Send a response via the appropriate channel's Graph API."""
    token = META_TOKENS.get(channel_id, "")
    if not token:
        return {"error": f"No token configured for channel {channel_id}"}
    
    if msg.platform == Platform.WHATSAPP:
        return await send_whatsapp_message(msg.sender_id, text, msg.recipient_id, token)
    elif msg.platform == Platform.INSTAGRAM:
        return await send_instagram_message(msg.sender_id, text, token)
    elif msg.platform == Platform.MESSENGER:
        return await send_messenger_message(msg.sender_id, text, token)
    return None


async def log_webhook_event(msg: InboundMessage, channel_id: int | None,
                           conv_info: dict | None, status: str = "received",
                           error: str | None = None, latency_ms: int = 0) -> None:
    """Log webhook event to v4 DB for monitoring."""
    await v4_insert("webhook_events", {
        "platform": msg.platform.value,
        "event_type": "message",
        "sender_id": msg.sender_id,
        "channel_id": channel_id,
        "conversation_id": conv_info["conversation_id"] if conv_info else None,
        "message_type": msg.message_type.value,
        "message_preview": (msg.text or "")[:200],
        "message_id_external": msg.message_id,
        "processing_status": status,
        "error_detail": error,
        "latency_ms": latency_ms,
    })
