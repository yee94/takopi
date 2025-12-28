from __future__ import annotations

import requests


class TelegramClient:
    """
    Minimal Telegram Bot API client.
    """

    def __init__(self, token: str, timeout_s: float = 120) -> None:
        if not token:
            raise ValueError("Telegram token is empty")
        self._base = f"https://api.telegram.org/bot{token}"
        self._timeout_s = timeout_s

    def _call(self, method: str, params: dict) -> object:
        resp = requests.post(
            f"{self._base}/{method}",
            json=params,
            timeout=self._timeout_s,
        )
        resp.raise_for_status()
        payload = resp.json()
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram API error: {payload}")
        return payload["result"]

    def get_updates(
        self,
        offset: int | None,
        timeout_s: int = 50,
        allowed_updates: list[str] | None = None,
    ) -> list[dict]:
        params: dict = {"timeout": timeout_s}
        if offset is not None:
            params["offset"] = offset
        if allowed_updates is not None:
            params["allowed_updates"] = allowed_updates
        return self._call("getUpdates", params)  # type: ignore[return-value]

    def send_message(
        self,
        chat_id: int,
        text: str,
        reply_to_message_id: int | None = None,
        disable_notification: bool | None = False,
        entities: list[dict] | None = None,
    ) -> dict:
        params: dict = {
            "chat_id": chat_id,
            "text": text,
        }
        if disable_notification is not None:
            params["disable_notification"] = disable_notification
        if reply_to_message_id is not None:
            params["reply_to_message_id"] = reply_to_message_id
        if entities is not None:
            params["entities"] = entities
        return self._call("sendMessage", params)  # type: ignore[return-value]

    def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        entities: list[dict] | None = None,
    ) -> dict:
        params: dict = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
        }
        if entities is not None:
            params["entities"] = entities
        return self._call("editMessageText", params)  # type: ignore[return-value]

    def delete_message(self, chat_id: int, message_id: int) -> bool:
        res = self._call(
            "deleteMessage",
            {
                "chat_id": chat_id,
                "message_id": message_id,
            },
        )
        return bool(res)

