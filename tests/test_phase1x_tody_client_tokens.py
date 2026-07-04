"""TODY token persistence safeguards."""


def test_tody_client_persists_and_reuses_tokens(monkeypatch, tmp_path):
    from app.config import get_settings
    from app.integrations import tody_client

    token_path = tmp_path / "tody_tokens.json"
    monkeypatch.setenv("TODY_EMAIL", "bot@example.com")
    monkeypatch.setenv("TODY_PASSWORD", "secret")
    monkeypatch.setenv("TODY_TOKEN_PATH", str(token_path))
    get_settings.cache_clear()

    class FakeResponse:
        def __init__(self, data):
            self._data = data
            self.status_code = 200

        def json(self):
            return self._data

    calls = []

    def fake_post(url, json=None, headers=None, timeout=30):
        calls.append(url)
        return FakeResponse({
            "ok": True,
            "data": {
                "tokens": {
                    "access_token": "access-1",
                    "refresh_token": "refresh-1",
                    "expires_in": 3600,
                },
                "user": {"username": "brain"},
            },
        })

    monkeypatch.setattr(tody_client.httpx, "post", fake_post)

    first = tody_client.TodyClient()
    assert first.login()["username"] == "brain"
    assert token_path.exists()

    second = tody_client.TodyClient()
    assert second._token() == "access-1"
    assert len(calls) == 1
