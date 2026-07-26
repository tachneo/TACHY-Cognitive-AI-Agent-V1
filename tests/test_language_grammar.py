from app.brain import language_grammar as lg


def test_language_grammar_detects_hinglish_tense_person_and_targets():
    out = lg.analyze("@niva ko message karo or usse haal chaal pucho")

    assert out["language"] == "hinglish"
    assert out["tense"] in {"present", "mixed"}
    assert out["person"] == "third"
    assert out["temporal_scope"] == "unspecified"
    assert out["targets"] == ["niva"]


def test_language_grammar_detects_past_future_and_people():
    assert lg.analyze("maine khana kha liya")["tense"] == "past"
    assert lg.analyze("kal subah message bhej dena")["temporal_scope"] == "yesterday_or_tomorrow"
    assert lg.analyze("tumne usse baat ki?")["person"] == "mixed"


def test_clean_and_naturalize_recipient_instruction():
    assert lg.clean_recipient_body("or usse haal chaal pucho") == "haal chaal pucho"
    assert lg.naturalize_recipient_instruction(
        "or usse haal chaal pucho, sab thik hai na"
    ) == "Hii, kaise ho? Sab thik hai na?"
    assert lg.naturalize_recipient_instruction(
        "or padhai kisi chal rahi hai"
    ) == "Hii, padhai kaisi chal rahi hai?"


def test_resolve_recent_person_from_pronoun():
    recent = ["talk to niva and ask how she is", "theek hai Papa"]
    assert lg.resolve_recent_person("kya tumne usse baat kiya?", recent) == "niva"
