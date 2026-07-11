def test_send_message_supports_reply_attachment_and_forward(monkeypatch):
    from app.integrations import tody_client
    client = tody_client.TodyClient()
    captured = {}
    monkeypatch.setattr(client, "_post", lambda path, payload: captured.update(path=path, payload=payload) or payload)
    client.send_message(12, "caption", reply_to_message_id=44, attachment_id=9, message_type="image", forwarded_from_message_id=33, view_once=True)
    assert captured["path"].endswith("/send.php")
    assert captured["payload"]["reply_to_message_id"] == 44
    assert captured["payload"]["attachment_id"] == 9
    assert captured["payload"]["view_once"] is True


def test_chat_actions_use_server_api(monkeypatch):
    from app.integrations import tody_client
    client = tody_client.TodyClient(); calls = []
    monkeypatch.setattr(client, "_post", lambda path, payload: calls.append((path, payload)) or {})
    client.edit_message(1, "new"); client.delete_message(1, "self"); client.mark_read(2)
    client.archive(2); client.pin_conversation(2); client.star(1, False); client.set_disappearing(2, 86400)
    assert [p.rsplit('/', 1)[-1] for p, _ in calls] == ["edit_message.php", "delete_message.php", "mark_read.php", "archive.php", "pin_conversation.php", "unstar.php", "set_disappearing.php"]


def test_attachment_message_is_not_dropped_by_worker_parser():
    from app.agents import tody_agent
    from app.agents.tody_worker import _latest_unprocessed_message
    row = {"id": "img-1", "sender_name": "Rohit Kumar", "attachment": {"id": 7, "url": "https://api.tody.in/image", "mime_type": "image/jpeg"}}
    out = _latest_unprocessed_message(998, {"messages": [row]})
    assert out["attachments"][0]["id"] == 7
    assert out["body"] == ""
    assert tody_agent._message_attachment(row)["mime_type"] == "image/jpeg"


def test_vision_is_honest_when_disabled():
    from app.vision.tody import analyze_image
    result = analyze_image(b"not-an-image", "image/jpeg")
    assert result["ok"] is False
    assert result["reason"] == "vision_disabled"
