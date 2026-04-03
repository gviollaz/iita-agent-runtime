"""Channel operations — complete pipeline from webhook to response.

Handles: resolve channel → find/create person → deduplicate → create interaction → send response.
"""
import os
import json
from datetime import datetime
import httpx
from src.db import v3_rpc, v3_query, v3_insert, v3_update, v4_insert, v3_available
from src.webhook import InboundMessage, Platform, MessageType

META_TOKENS = {
    10: os.environ.get("META_GRAPH_TOKEN", ""),
    5: os.environ.get("META_GRAPH_TOKEN_COEX", ""),
    4: os.environ.get("META_GRAPH_TOKEN_SL", ""),
    6: os.environ.get("META_GRAPH_TOKEN", ""),
    7: os.environ.get("META_GRAPH_TOKEN_SL", ""),
    8: os.environ.get("META_GRAPH_TOKEN", ""),
    9: os.environ.get("META_GRAPH_TOKEN_SL", ""),
}

CHANNEL_MAP = {
    "100436536473788": 10, "102522002867267": 4, "100651882782406": 5,
    "17841404168256335": 6, "17841455198100771": 7,
    "296373163870909": 8, "106307535517599": 9,
}

def resolve_channel_id(msg: InboundMessage) -> int | None:
    return CHANNEL_MAP.get(msg.recipient_id)


async def is_duplicate(message_id: str) -> bool:
    if not message_id or not v3_available():
        return False
    existing = await v3_query("interactions", "id", f"external_ref=eq.{message_id}&limit=1")
    return len(existing) > 0


async def find_or_create_person(msg: InboundMessage, channel_id: int) -> dict | None:
    if not v3_available():
        return None
    address = msg.sender_id
    pcs = await v3_query("person_conversation", "id,id_person,id_conversation,address",
                         f"address=eq.{address}")
    if pcs:
        pc = pcs[0]
        scs = await v3_query("system_conversation", "id",
                             f"id_conversation=eq.{pc['id_conversation']}&id_channel=eq.{channel_id}")
        return {
            "person_id": pc["id_person"], "conversation_id": pc["id_conversation"],
            "person_conversation_id": pc["id"],
            "system_conversation_id": scs[0]["id"] if scs else None, "is_new": False,
        }
    person = await v3_insert("persons", {
        "first_name": None,
        "phone": address if msg.platform == Platform.WHATSAPP else None,
    })
    if not person: return None
    conv = await v3_insert("conversations", {
        "start_date": datetime.utcnow().isoformat(),
        "last_activity_at": datetime.utcnow().isoformat(),
    })
    if not conv: return None
    pc = await v3_insert("person_conversation", {
        "id_person": person["id"], "id_conversation": conv["id"], "address": address,
    })
    sc = await v3_insert("system_conversation", {
        "id_conversation": conv["id"], "id_channel": channel_id,
    })
    return {
        "person_id": person["id"], "conversation_id": conv["id"],
        "person_conversation_id": pc["id"] if pc else None,
        "system_conversation_id": sc["id"] if sc else None, "is_new": True,
    }


async def create_inbound_interaction(msg: InboundMessage, conv_info: dict) -> dict | None:
    if not v3_available() or not conv_info: return None
    result = await v3_insert("interactions", {
        "id_person_conversation": conv_info["person_conversation_id"],
        "text": msg.text or f"[{msg.message_type.value}]",
        "external_ref": msg.message_id,
        "message_type": msg.message_type.value,
        "status": "preprocessed",
        "time_stamp": datetime.utcnow().isoformat(),
    })
    if result:
        await v3_update("conversations", f"id=eq.{conv_info['conversation_id']}",
            {"last_activity_at": datetime.utcnow().isoformat()})
    return result


async def create_outbound_interaction(text: str, conv_info: dict, external_ref: str = None) -> dict | None:
    if not v3_available() or not conv_info: return None
    data = {
        "id_system_conversation": conv_info["system_conversation_id"],
        "text": text, "message_type": "text", "status": "send",
        "time_stamp": datetime.utcnow().isoformat(),
    }
    if external_ref:
        data["external_ref"] = external_ref
    return await v3_insert("interactions", data)


async def update_message_status(external_ref: str, status: str) -> None:
    if not v3_available() or not external_ref: return
    new_status = {"delivered": "delivered", "read": "read", "sent": "sent"}.get(status)
    if new_status:
        await v3_update("interactions", f"external_ref=eq.{external_ref}", {"status": new_status})


async def send_whatsapp_message(phone: str, text: str, phone_number_id: str, token: str) -> dict | None:
    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    payload = {"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": text}}
    async with httpx.AsyncClient() as c:
        r = await c.post(url, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                        json=payload, timeout=15)
        return r.json() if r.status_code == 200 else {"error": r.text, "status": r.status_code}

async def send_instagram_message(recipient_id: str, text: str, token: str) -> dict | None:
    payload = {"recipient": {"id": recipient_id}, "message": {"text": text}}
    async with httpx.AsyncClient() as c:
        r = await c.post("https://graph.facebook.com/v19.0/me/messages",
                        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                        json=payload, timeout=15)
        return r.json() if r.status_code == 200 else {"error": r.text, "status": r.status_code}

async def send_messenger_message(recipient_id: str, text: str, token: str) -> dict | None:
    payload = {"recipient": {"id": recipient_id}, "message": {"text": text}}
    async with httpx.AsyncClient() as c:
        r = await c.post("https://graph.facebook.com/v19.0/me/messages",
                        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                        json=payload, timeout=15)
        return r.json() if r.status_code == 200 else {"error": r.text, "status": r.status_code}

async def send_response(msg: InboundMessage, text: str, conv_info: dict, channel_id: int) -> dict | None:
    token = META_TOKENS.get(channel_id, "")
    if not token: return {"error": f"No token for channel {channel_id}"}
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
    await v4_insert("webhook_events", {
        "platform": msg.platform.value, "event_type": "message",
        "sender_id": msg.sender_id, "channel_id": channel_id,
        "conversation_id": conv_info["conversation_id"] if conv_info else None,
        "message_type": msg.message_type.value,
        "message_preview": (msg.text or "")[:200],
        "message_id_external": msg.message_id,
        "processing_status": status, "error_detail": error, "latency_ms": latency_ms,
    })
