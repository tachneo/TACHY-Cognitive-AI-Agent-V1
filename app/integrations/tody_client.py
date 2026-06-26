"""TODY API client — authenticated connection to the live TODY backend.

Base: https://api.tody.in/api  (PHP REST). Auth is email+password → bearer
access_token (1h) + refresh_token. The client caches tokens in memory and
auto-refreshes (then re-logs-in) on expiry/401.

Read methods (me/conversations/contacts) are safe. Write methods (send_message,
create_post) are exposed but the *agent/route* layer gates them behind the
approval workflow — the client itself stays a thin transport.
"""
from __future__ import annotations

import time
import uuid

import httpx

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

    # ── read ────────────────────────────────────────────────────
    def me(self) -> dict:
        return self._get("/v1/auth/me.php").get("user", {})

    def conversations(self, limit: int = 20) -> dict:
        return self._get("/v1/chat/conversations.php", {"limit": limit})

    def messages(self, conversation_id: int, limit: int = 30) -> dict:
        return self._get("/v1/chat/messages.php",
                         {"conversation_id": conversation_id, "limit": limit})

    def contacts(self) -> dict:
        return self._get("/v1/contacts/list.php")

    # ── write (gated by the agent/approval layer) ───────────────
    def start_direct(self, user_uuid: str) -> dict:
        return self._post("/v1/chat/start_direct.php", {"user_uuid": user_uuid})

    def send_message(self, conversation_id: int, body: str) -> dict:
        return self._post("/v1/chat/send.php", {
            "conversation_id": conversation_id,
            "body": body,
            "client_nonce": uuid.uuid4().hex,
            "message_type": "text",
        })

    def create_post(self, body: str) -> dict:
        return self._post("/v1/posts/create.php", {"body": body})


_client: TodyClient | None = None


def get_client() -> TodyClient:
    global _client
    if _client is None:
        _client = TodyClient()
    return _client
