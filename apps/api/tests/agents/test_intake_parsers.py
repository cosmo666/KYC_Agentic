from app.agents.intake import mask_aadhaar, parse_vision_output, pick_ocr_confidence


def test_mask_aadhaar_12_digit():
    assert mask_aadhaar("1234 5678 9012") == "XXXX XXXX 9012"


def test_mask_aadhaar_no_spaces():
    assert mask_aadhaar("123456789012") == "XXXX XXXX 9012"


def test_mask_aadhaar_already_masked_left_alone():
    assert mask_aadhaar("XXXX XXXX 9012") == "XXXX XXXX 9012"


def test_mask_aadhaar_invalid_returns_original():
    assert mask_aadhaar("abc") == "abc"


def test_parse_vision_output_strips_markdown_fence():
    raw = '```json\n{"name": "Asha", "doc_type": "aadhaar"}\n```'
    result = parse_vision_output(raw)
    assert result["name"] == "Asha"


def test_pick_ocr_confidence_low_when_blank_name():
    assert pick_ocr_confidence({"name": "", "dob": "01/01/1990"}) == "low"


def test_pick_ocr_confidence_high_when_full():
    assert (
        pick_ocr_confidence(
            {
                "name": "Asha Sharma",
                "dob": "01/01/1990",
                "doc_type": "aadhaar",
                "aadhaar_number": "XXXX XXXX 9012",
                "gender": "F",
                "address": "Mumbai",
            }
        )
        == "high"
    )
