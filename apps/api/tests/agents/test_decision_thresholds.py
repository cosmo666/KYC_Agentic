from app.agents.decision import compute_decision


def _state(
    score=85,
    face_ok=True,
    face_detected=True,
    critical_fails=None,
    country_ok=True,
    flags=None,
):
    critical_fails = critical_fails or []
    return {
        "cross_validation": {
            "overall_score": score,
            "checks": [
                {
                    "name": "name_match",
                    "status": "fail" if "name" in critical_fails else "pass",
                    "score": 0.9,
                },
                {
                    "name": "dob_match",
                    "status": "fail" if "dob" in critical_fails else "pass",
                    "score": 1.0,
                },
            ],
        },
        "face_check": {
            "verified": face_ok,
            "confidence": 85 if face_ok else 30,
            "faces_detected": face_detected,
        },
        "ip_check": {"country_ok": country_ok},
        "flags": flags or [],
    }


def test_approved_when_score_high_and_face_ok():
    d = compute_decision(_state(score=85))
    assert d["decision"] == "approved"


def test_rejected_on_name_critical_fail():
    d = compute_decision(_state(critical_fails=["name"]))
    assert d["decision"] == "rejected"
    assert any("name" in f for f in d["flags"])


def test_rejected_on_country_mismatch():
    d = compute_decision(_state(country_ok=False))
    assert d["decision"] == "rejected"


def test_flagged_on_mid_score():
    d = compute_decision(_state(score=65))
    assert d["decision"] == "flagged"


def test_rejected_on_low_score():
    d = compute_decision(_state(score=20))
    assert d["decision"] == "rejected"
