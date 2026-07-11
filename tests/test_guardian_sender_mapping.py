def test_top_level_guardian_uuid_survives_partial_nested_sender():
    from app.agents.tody_agent import _message_sender
    from app.config import get_settings
    from app.memory.relationship_memory import is_guardian_sender

    expected = get_settings().guardian_tody_user_uuid or "guardian-uuid"
    row = {"sender_uuid": expected,
           "sender_name": "Rohit Kumar", "sender": {"name": "Rohit Kumar"}}
    sender = _message_sender(row)
    assert sender["uuid"] == expected
    if get_settings().guardian_tody_user_uuid:
        assert is_guardian_sender(sender) is True
