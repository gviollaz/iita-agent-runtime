"""Channel operations — resolve person/conversation, create interactions, send responses.

Bridges the webhook handler to the v3 CRM database.
During transition: writes to v3 DB. After migration: writes to v4.
"""
import json
from src.db import v3_rpc, v3_query, v3_available
from src.webhook import InboundMessage, Platform

# Channel mapping: recipient_id (phone_number_id or page/ig ID) → channel_id in v3
# This maps Meta's identifiers to our channel IDs
CHANNEL_MAP = {
    # WhatsApp Cloud API
    "100436536473788": 10,    # ch10 Chatbot Cloud API
    # WhatsApp Coexistence
    "102522002867267": 4,     # ch4 San Lorenzo
    "100651882782406": 5,     # ch5 IITA Cursos
    # Instagram
    "17841404168256335": 6,   # ch6 IG Salta
    "17841455198100771": 7,   # ch7 IG San Lorenzo
    # Messenger
    "296373163870909": 8,     # ch8 Messenger Salta
    "106307535517599": 9,     # ch9 Messenger San Lorenzo
}

# Phone number to channel for WA Cloud API (sender matching)
PHONE_CHANNEL_MAP = {
    "111869345312688": 10,    # WA Cloud API phone
    "5493876844174": 4,       # WA San Lorenzo
    "5493875809351": 5,       # WA Cursos
}


def resolve_channel_id(msg: InboundMessage) -> int | None:
    """Resolve v3 channel_id from the inbound message."""
    # Try recipient_id first (phone_number_id for WA, page/ig_id for IG/Messenger)
    ch = CHANNEL_MAP.get(msg.recipient_id)
    if ch:
        return ch
    # For WA, also try matching by known phone numbers in address field
    if msg.platform == Platform.WHATSAPP:
        ch = PHONE_CHANNEL_MAP.get(msg.recipient_id)
        if ch:
            return ch
    return None


async def find_or_create_person(msg: InboundMessage, channel_id: int) -> dict | None:
    """Find existing person by sender address, or create new one.
    
    Returns dict with person_id, conversation_id, person_conversation_id, system_conversation_id.
    """
    if not v3_available():
        return None

    address = msg.sender_id

    # Check if person_conversation exists for this address + channel
    pcs = await v3_query(
        "person_conversation",
        "id,id_person,id_conversation,address",
        f"address=eq.{address}"
    )

    if pcs:
        pc = pcs[0]
        # Get system_conversation for this conversation + channel
        scs = await v3_query(
            "system_conversation", "id",
            f"id_conversation=eq.{pc['id_conversation']}&id_channel=eq.{channel_id}"
        )
        return {
            "person_id": pc["id_person"],
            "conversation_id": pc["id_conversation"],
            "person_conversation_id": pc["id"],
            "system_conversation_id": scs[0]["id"] if scs else None,
            "is_new": False,
        }

    # Person not found — create via RPC
    # For now, return None and let the caller handle creation
    # Full creation logic will be added when we go live
    return None


async def create_inbound_interaction(msg: InboundMessage, conv_info: dict) -> dict | None:
    """Create an inbound interaction in v3 DB."""
    if not v3_available() or not conv_info:
        return None

    # Build interaction data
    interaction = {
        "id_person_conversation": conv_info["person_conversation_id"],
        "text": msg.text or f"[{msg.message_type.value}]",
        "external_ref": msg.message_id,
        "message_type": msg.message_type.value,
        "status": "preprocessed",
    }

    # Insert via REST
    from src.db import v4_insert  # Reuse insert pattern
    # Actually we need v3_insert — TODO: add to db.py
    # For now, use v3_rpc if available

    return interaction  # Placeholder


async def send_whatsapp_message(phone: str, text: str, phone_number_id: str, token: str) -> dict | None:
    """Send a WhatsApp message via Graph API (replaces Make.com OUT scenarios)."""
    import httpx
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


async def send_instagram_message(recipient_id: str, text: str, page_token: str) -> dict | None:
    """Send an Instagram DM via Graph API."""
    import httpx
    url = f"https://graph.facebook.com/v19.0/me/messages"
    headers = {"Authorization": f"Bearer {page_token}", "Content-Type": "application/json"}
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text}
    }
    async with httpx.AsyncClient() as c:
        r = await c.post(url, headers=headers, json=payload, timeout=15)
        return r.json() if r.status_code == 200 else {"error": r.text, "status": r.status_code}
