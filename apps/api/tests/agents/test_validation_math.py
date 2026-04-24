from app.agents.validation import (
    check_dob,
    check_name,
    jaccard,
    normalize_dob,
    normalize_name,
)


def test_normalize_name_strips_titles():
    assert normalize_name("Mr. Asha Sharma") == "asha sharma"
    assert normalize_name("श्री Asha Sharma") == "asha sharma"
    assert normalize_name("Kumari Asha") == "asha"


def test_jaccard_full_match():
    assert jaccard("asha sharma", "asha sharma") == 1.0


def test_jaccard_partial_match():
    # "asha sharma" vs "asha" → 1/2 = 0.5
    assert abs(jaccard("asha sharma", "asha") - 0.5) < 1e-9


def test_jaccard_zero_when_disjoint():
    assert jaccard("asha", "rahul") == 0.0


def test_normalize_dob_accepts_various_formats():
    assert normalize_dob("01/01/1990") == "01/01/1990"
    assert normalize_dob("1-1-1990") == "01/01/1990"
    assert normalize_dob("1990-01-01") == "01/01/1990"


def test_check_name_pass_on_high_similarity():
    c = check_name("Mr. Asha Sharma", "Asha Sharma")
    assert c["status"] == "pass"
    assert c["score"] >= 0.9


def test_check_dob_fail_on_mismatch():
    c = check_dob("01/01/1990", "02/01/1990")
    assert c["status"] == "fail"
