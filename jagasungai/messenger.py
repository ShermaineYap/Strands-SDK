"""Delivery channels behind one interface.

* ConsoleMessenger  - prints and records an outbox (local runs, tests, demo)
* WhatsAppMessenger - AWS End User Messaging Social (SendWhatsAppMessage)
* TelegramMessenger - Bot API fallback if a WhatsApp Business Account is not approved
"""

from __future__ import annotations

import json
import os
from typing import Protocol


class Messenger(Protocol):
    name: str

    def send(self, recipient: str, text: str) -> str: ...


class ConsoleMessenger:
    name = "console"

    def __init__(self, echo: bool = True) -> None:
        self.outbox: list[tuple[str, str]] = []
        self.echo = echo

    def send(self, recipient: str, text: str) -> str:
        self.outbox.append((recipient, text))
        if self.echo:
            print(f"\n----- to {recipient} -----\n{text}\n------------------------")
        return f"console-{len(self.outbox)}"


class WhatsAppMessenger:  # pragma: no cover - needs AWS + an approved WABA
    """Text message through AWS End User Messaging Social.

    Requires a linked WhatsApp Business Account and a phone number ID
    (``phone-number-id-...``). Regions include ap-southeast-1 and ap-southeast-5.
    Free-form text can only be sent inside the 24h customer-service window;
    outside it Meta requires an approved template (see docs/DEPLOY.md).
    """

    name = "whatsapp"

    def __init__(self, phone_number_id: str | None = None, region: str | None = None,
                 meta_api_version: str = "v20.0") -> None:
        import boto3

        self.client = boto3.client("socialmessaging", region_name=region or os.environ.get("JAGASUNGAI_WA_REGION"))
        self.phone_number_id = phone_number_id or os.environ["JAGASUNGAI_WA_PHONE_NUMBER_ID"]
        self.meta_api_version = meta_api_version

    def send(self, recipient: str, text: str) -> str:
        body = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "text",
            "text": {"preview_url": False, "body": text[:4096]},
        }
        resp = self.client.send_whatsapp_message(
            originationPhoneNumberId=self.phone_number_id,
            message=json.dumps(body).encode(),
            metaApiVersion=self.meta_api_version,
        )
        return resp.get("messageId", "")


class TelegramMessenger:  # pragma: no cover - needs a bot token
    name = "telegram"

    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.environ["JAGASUNGAI_TELEGRAM_TOKEN"]

    def send(self, recipient: str, text: str) -> str:
        import requests

        r = requests.post(f"https://api.telegram.org/bot{self.token}/sendMessage",
                          json={"chat_id": recipient, "text": text[:4096]}, timeout=20)
        r.raise_for_status()
        return str(r.json()["result"]["message_id"])


def messenger_from_env() -> Messenger:
    kind = os.environ.get("JAGASUNGAI_CHANNEL", "console")
    if kind == "whatsapp":
        return WhatsAppMessenger()
    if kind == "telegram":
        return TelegramMessenger()
    return ConsoleMessenger()
