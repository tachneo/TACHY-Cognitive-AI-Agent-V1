"""TODY API client — authenticated connection to the live TODY backend.

Base: https://api.tody.in/api  (PHP REST). Auth is email+password → bearer
access_token (1h) + refresh_token. The client caches tokens in memory and
auto-refreshes (then re-logs-in) on expiry/401.

Read methods (me/conversations/contacts) are safe. Write methods (send_message,
create_post) are exposed but the *agent/route* layer gates them behind the
approval workflow — the client itself stays a thin transport.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import httpx
from urllib.parse import urljoin, urlparse

from app.config import get_settings

class TodyError(RuntimeError):
    pass


class TodyClient:
    def __init__(self) -> None:
        s = get_settings()
        self._base = s.tody_api_base.rstrip("/")
        self._email = s.tody_email
        self._password = s.tody_password
        self._access: str | None = None
        self._refresh: str | None = None
        self._expires_at: float = 0.0
        # Persist tokens so service restarts do not create fresh login attempts.
        self._token_path = Path(s.tody_token_path)
        self._last_token_save_error: str | None = None
        self._load_tokens()

    # ── auth ────────────────────────────────────────────────────
    def _post(self, path: str, json: dict, auth: bool = True) -> dict:
        headers = {"content-type": "application/json"}
        if auth:
            headers["Authorization"] = f"Bearer {self._token()}"
        r = httpx.post(f"{self._base}{path}", json=json, headers=headers, timeout=30)
        if r.status_code == 401 and auth:
            self._access = None  # force refresh/re-login then retry once
            headers["Authorization"] = f"Bearer {self._token()}"
            r = httpx.post(f"{self._base}{path}", json=json, headers=headers, timeout=30)
        return self._envelope(r)

    def _get(self, path: str, params: dict | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self._token()}"}
        r = httpx.get(f"{self._base}{path}", params=params or {}, headers=headers, timeout=30)
        if r.status_code == 401:
            self._access = None
            headers["Authorization"] = f"Bearer {self._token()}"
            r = httpx.get(f"{self._base}{path}", params=params or {}, headers=headers, timeout=30)
        return self._envelope(r)

    @staticmethod
    def _envelope(r: httpx.Response) -> dict:
        try:
            data = r.json()
        except Exception:
            raise TodyError(f"non-JSON response ({r.status_code})")
        if not data.get("ok", False):
            raise TodyError(data.get("message", f"TODY error ({r.status_code})"))
        return data.get("data", {})

    def login(self) -> dict:
        if not self._email or not self._password:
            raise TodyError("TODY_EMAIL / TODY_PASSWORD not configured in .env")
        r = httpx.post(
            f"{self._base}/v1/auth/login_password.php",
            json={"email": self._email, "password": self._password},
            headers={"content-type": "application/json"}, timeout=30,
        )
        data = self._envelope(r)
        self._store_tokens(data.get("tokens", data))
        return data.get("user", {})

    def _token(self) -> str:
        if self._access and time.time() < self._expires_at - 30:
            return self._access
        if self._refresh:
            try:
                r = httpx.post(
                    f"{self._base}/v1/auth/refresh_token.php",
                    json={"refresh_token": self._refresh},
                    headers={"content-type": "application/json"}, timeout=30,
                )
                self._store_tokens(self._envelope(r))
                return self._access  # type: ignore[return-value]
            except TodyError:
                pass
        self.login()
        return self._access  # type: ignore[return-value]

    def _store_tokens(self, tokens: dict) -> None:
        self._access = tokens.get("access_token")
        self._refresh = tokens.get("refresh_token", self._refresh)
        self._expires_at = time.time() + int(tokens.get("expires_in", 3600))
        self._save_tokens()

    def _save_tokens(self) -> None:
        try:
            self._token_path.parent.mkdir(parents=True, exist_ok=True)
            self._token_path.write_text(json.dumps({
                "access": self._access, "refresh": self._refresh,
                "expires_at": self._expires_at, "email": self._email,
            }), encoding="utf-8")
            self._last_token_save_error = None
        except OSError as exc:
            self._last_token_save_error = f"{type(exc).__name__}: {exc}"

    def _load_tokens(self) -> None:
        try:
            data = json.loads(self._token_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        # Ignore a cache saved for a different account.
        if data.get("email") and data["email"] != self._email:
            return
        self._access = data.get("access")
        self._refresh = data.get("refresh")
        self._expires_at = float(data.get("expires_at", 0.0))

    # ── read ────────────────────────────────────────────────────
    def me(self) -> dict:
        return self._get("/v1/auth/me.php").get("user", {})

    def conversations(self, limit: int = 20) -> dict:
        return self._get("/v1/chat/conversations.php", {"limit": limit})

    def archived_conversations(self) -> dict:
        return self._get("/v1/chat/archived.php")

    def messages(self, conversation_id: int, limit: int = 30) -> dict:
        return self._get("/v1/chat/messages.php",
                         {"conversation_id": conversation_id, "limit": limit})

    def contacts(self) -> dict:
        return self._get("/v1/contacts/list.php")

    def poll(self, after_id: int = 0, *, wait: bool = False) -> dict:
        params = {"after_id": int(after_id)}
        if wait:
            params["wait"] = "1"
        return self._get("/v1/chat/poll.php", params)

    def presence_heartbeat(self) -> dict:
        """Refresh TODY last_seen/online state without fetching chat history.

        chat-tachy's poll endpoint debounces `last_seen_at` updates and is the
        source of online/last-seen status. A very high `after_id` avoids the
        expensive initial message load while still touching presence.
        """
        return self.poll(after_id=2_147_483_647)

    # ── write (gated by the agent/approval layer) ───────────────
    def start_direct(self, user_uuid: str) -> dict:
        return self._post("/v1/chat/start_direct.php", {"user_uuid": user_uuid})

    def start_secret(self, user_uuid: str) -> dict:
        return self._post("/v1/chat/start_secret.php", {"user_uuid": user_uuid})

    def start_group(self, group_id: int) -> dict:
        return self._post("/v1/chat/start_group.php", {"group_id": group_id})

    def send_message(self, conversation_id: int, body: str, *,
                     reply_to_message_id: int | None = None,
                     attachment_id: int | None = None,
                     message_type: str = "text",
                     forwarded_from_message_id: int | None = None,
                     view_once: bool = False) -> dict:
        if not body.strip() and attachment_id is None:
            raise TodyError("message body or attachment is required")
        payload = {
            "conversation_id": conversation_id, "body": body,
            "client_nonce": uuid.uuid4().hex, "message_type": message_type,
        }
        if reply_to_message_id is not None: payload["reply_to_message_id"] = reply_to_message_id
        if attachment_id is not None: payload["attachment_id"] = attachment_id
        if forwarded_from_message_id is not None: payload["forwarded_from_message_id"] = forwarded_from_message_id
        if view_once: payload["view_once"] = True
        return self._post("/v1/chat/send.php", {
            **payload,
        })

    def edit_message(self, message_id: int, body: str) -> dict:
        return self._post("/v1/chat/edit_message.php", {"message_id": message_id, "body": body})

    def reply(self, conversation_id: int, message_id: int, body: str) -> dict:
        return self.send_message(conversation_id, body, reply_to_message_id=message_id)

    def delete_message(self, message_id: int, mode: str = "everyone") -> dict:
        if mode not in {"everyone", "self"}: raise TodyError("invalid delete mode")
        return self._post("/v1/chat/delete_message.php", {"message_id": message_id, "mode": mode})

    def forward_message(self, message_id: int, conversation_id: int) -> dict:
        return self._post("/v1/chat/forward.php", {"message_id": message_id, "conversation_id": conversation_id})

    def mark_delivered(self, message_id: int) -> dict:
        return self._post("/v1/chat/mark_delivered.php", {"message_id": message_id})

    def mark_read(self, conversation_id: int) -> dict:
        return self._post("/v1/chat/mark_read.php", {"conversation_id": conversation_id})

    def message_info(self, message_id: int) -> dict:
        return self._get("/v1/chat/message_info.php", {"message_id": message_id})

    def archive(self, conversation_id: int, archive: bool = True) -> dict:
        return self._post("/v1/chat/archive.php", {"conversation_id": conversation_id, "archive": archive})

    def delete_conversation(self, conversation_id: int) -> dict:
        return self._post("/v1/chat/delete_conversation.php", {"conversation_id": conversation_id})

    def clear_chat(self, conversation_id: int, for_everyone: bool = False) -> dict:
        return self._post("/v1/chat/clear_chat.php", {"conversation_id": conversation_id, "for_everyone": for_everyone})

    def mute(self, conversation_id: int, duration_minutes: int | None = None) -> dict:
        payload = {"conversation_id": conversation_id}
        if duration_minutes is not None: payload["duration_minutes"] = duration_minutes
        return self._post("/v1/chat/mute.php", payload)

    def pin_conversation(self, conversation_id: int, pin: bool = True) -> dict:
        return self._post("/v1/chat/pin_conversation.php", {"conversation_id": conversation_id, "pin": pin})

    def set_disappearing(self, conversation_id: int, disappear_seconds: int = 0) -> dict:
        return self._post("/v1/chat/set_disappearing.php", {"conversation_id": conversation_id, "disappear_seconds": disappear_seconds})

    def star(self, message_id: int, starred: bool = True) -> dict:
        return self._post("/v1/chat/star.php" if starred else "/v1/chat/unstar.php", {"message_id": message_id})

    def add_reaction(self, message_id: int, emoji: str) -> dict:
        return self._post("/v1/chat/reactions/add.php", {"message_id": message_id, "emoji": emoji})

    def remove_reaction(self, message_id: int, emoji: str | None = None) -> dict:
        payload = {"message_id": message_id}
        if emoji: payload["emoji"] = emoji
        return self._post("/v1/chat/reactions/remove.php", payload)

    def list_reactions(self, message_id: int) -> dict:
        return self._get("/v1/chat/reactions/list.php", {"message_id": message_id})

    def schedule_message(self, conversation_id: int, body: str, scheduled_at: str, *, reply_to_message_id: int | None = None, attachment_id: int | None = None) -> dict:
        payload = {"conversation_id": conversation_id, "body": body, "scheduled_at": scheduled_at}
        if reply_to_message_id is not None: payload["reply_to_message_id"] = reply_to_message_id
        if attachment_id is not None: payload["attachment_id"] = attachment_id
        return self._post("/v1/chat/schedule.php", payload)

    def scheduled_messages(self) -> dict:
        return self._get("/v1/chat/scheduled.php")

    def cancel_schedule(self, schedule_id: int) -> dict:
        return self._post("/v1/chat/cancel_schedule.php", {"id": schedule_id})

    def search_messages(self, query: str, conversation_id: int | None = None) -> dict:
        params = {"q": query}
        if conversation_id is not None: params["conversation_id"] = conversation_id
        return self._get("/v1/chat/search.php", params)

    def link_preview(self, url: str) -> dict:
        return self._get("/v1/chat/link_preview.php", {"url": url})

    def view_once(self, message_id: int) -> dict:
        return self._post("/v1/chat/view_once.php", {"message_id": message_id})

    def upload_attachment(self, file_path: str, *, media_type: str | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self._token()}"}
        with open(file_path, "rb") as handle:
            files = {"file": (Path(file_path).name, handle, "application/octet-stream")}
            data = {"media_type": media_type} if media_type else {}
            r = httpx.post(f"{self._base}/v1/chat/upload_attachment.php", files=files, data=data, headers=headers, timeout=60)
        return self._envelope(r)

    def download_attachment(self, attachment: dict, *, max_bytes: int = 10_000_000) -> tuple[bytes, str]:
        """Download only TODY-hosted media; never follow arbitrary URLs."""
        raw = str(attachment.get("url") or "")
        url = urljoin(self._base + "/", raw)
        allowed = {urlparse(self._base).netloc}
        allowed.update(h.strip() for h in get_settings().tody_media_allowed_hosts.split(",") if h.strip())
        if urlparse(url).netloc not in allowed:
            raise TodyError("attachment host is not trusted")
        response = httpx.get(url, headers={"Authorization": f"Bearer {self._token()}"}, timeout=30)
        response.raise_for_status()
        data = response.content
        if len(data) > max_bytes: raise TodyError("attachment exceeds size limit")
        return data, response.headers.get("content-type", attachment.get("mime_type", "application/octet-stream"))

    def set_typing(self, conversation_id: int, is_typing: bool,
                   preview_text: str | None = None) -> dict:
        payload = {
            "conversation_id": conversation_id,
            "is_typing": bool(is_typing),
        }
        if preview_text:
            payload["preview_text"] = preview_text[:500]
        return self._post("/v1/chat/typing.php", payload)

    def create_post(self, body: str) -> dict:
        return self._post("/v1/posts/create.php", {"body": body})


_client: TodyClient | None = None


def get_client() -> TodyClient:
    global _client
    if _client is None:
        _client = TodyClient()
    return _client
