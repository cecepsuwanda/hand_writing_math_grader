import pytest

from app.functions.json_extract import extract_json_object


def test_extract_raw_json_object() -> None:
    data = extract_json_object('{"page_number": 1, "questions": []}')
    assert data["page_number"] == 1
    assert data["questions"] == []


def test_extract_json_from_markdown_fence() -> None:
    text = """Here is the result:
```json
{"page_number": 2, "questions": [{"question_number": 1, "steps": []}]}
```
"""
    data = extract_json_object(text)
    assert data["page_number"] == 2
    assert data["questions"][0]["question_number"] == 1


def test_extract_json_with_surrounding_text() -> None:
    text = 'prefix {"page_number": 3, "questions": []} suffix'
    data = extract_json_object(text)
    assert data["page_number"] == 3


def test_extract_rejects_empty() -> None:
    with pytest.raises(ValueError):
        extract_json_object("   ")


def test_extract_rejects_array() -> None:
    with pytest.raises(ValueError):
        extract_json_object("[1, 2, 3]")
