import pytest

from leaksentinel.bedrock.json_tools import extract_json_object


def test_extract_json_object_plain() -> None:
    obj = extract_json_object('{"a": 1, "b": "x"}')
    assert obj["a"] == 1
    assert obj["b"] == "x"


def test_extract_json_object_wrapped_text() -> None:
    txt = "Here is the result:\n```json\n{ \"ok\": true, \"n\": 2 }\n```\nThanks."
    obj = extract_json_object(txt)
    assert obj["ok"] is True
    assert obj["n"] == 2


def test_extract_json_object_no_json() -> None:
    with pytest.raises(ValueError):
        extract_json_object("no json here")

