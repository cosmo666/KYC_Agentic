from app.agents.orchestrator import detect_language, heuristic_intent


def test_detect_language_en():
    assert detect_language("my name is Asha") == "en"


def test_detect_language_hi_devanagari():
    assert detect_language("मेरा नाम आशा है") == "hi"


def test_detect_language_mixed():
    # Hinglish in Latin script
    assert detect_language("mera naam Asha hai, kyc start karo") == "mixed"


def test_heuristic_intent_faq_on_question_mark():
    assert heuristic_intent("what is KYC?") == "faq"


def test_heuristic_intent_continue_on_short_answer():
    assert heuristic_intent("Asha Sharma") == "continue_flow"
