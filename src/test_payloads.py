"""Test utilities for webhook simulation."""

def make_wa_test_payload(phone: str, text: str, phone_number_id: str = "100436536473788") -> dict:
    """Generate a simulated WhatsApp webhook payload."""
    import time
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "TEST",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": phone_number_id, "display_phone_number": "TEST"},
                    "messages": [{
                        "from": phone,
                        "id": f"wamid.TEST_{int(time.time())}",
                        "timestamp": str(int(time.time())),
                        "text": {"body": text},
                        "type": "text"
                    }]
                },
                "field": "messages"
            }]
        }]
    }

def make_ig_test_payload(sender_id: str, text: str, recipient_id: str = "17841404168256335") -> dict:
    """Generate a simulated Instagram webhook payload."""
    import time
    return {
        "object": "instagram",
        "entry": [{
            "id": "TEST",
            "time": int(time.time()),
            "messaging": [{
                "sender": {"id": sender_id},
                "recipient": {"id": recipient_id},
                "timestamp": int(time.time()),
                "message": {
                    "mid": f"m_TEST_{int(time.time())}",
                    "text": text
                }
            }]
        }]
    }

def make_messenger_test_payload(sender_id: str, text: str, recipient_id: str = "296373163870909") -> dict:
    """Generate a simulated Messenger webhook payload."""
    import time
    return {
        "object": "page",
        "entry": [{
            "id": "TEST",
            "time": int(time.time()),
            "messaging": [{
                "sender": {"id": sender_id},
                "recipient": {"id": recipient_id},
                "timestamp": int(time.time()),
                "message": {
                    "mid": f"m_TEST_{int(time.time())}",
                    "text": text
                }
            }]
        }]
    }

def make_wa_status_payload(message_id: str, status: str = "delivered", phone_number_id: str = "100436536473788") -> dict:
    """Generate a simulated WhatsApp status update."""
    import time
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "TEST",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": phone_number_id},
                    "statuses": [{
                        "id": message_id,
                        "status": status,
                        "timestamp": str(int(time.time())),
                        "recipient_id": "5493870000000"
                    }]
                },
                "field": "messages"
            }]
        }]
    }
