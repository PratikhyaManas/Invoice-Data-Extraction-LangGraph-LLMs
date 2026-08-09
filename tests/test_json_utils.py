from invoice_extraction.utils.json_utils import extract_json


def test_extract_json_direct_array():
    assert extract_json('[{"a": 1}]') == [{"a": 1}]


def test_extract_json_direct_object_wrapped_in_list():
    assert extract_json('{"a": 1}') == [{"a": 1}]


def test_extract_json_markdown_fenced():
    text = "Here you go:\n```json\n[{\"a\": 1}, {\"a\": 2}]\n```\nThanks!"
    assert extract_json(text) == [{"a": 1}, {"a": 2}]


def test_extract_json_embedded_array_with_preamble():
    text = 'Sure, here is the data: [{"a": 1}] -- let me know if you need more.'
    assert extract_json(text) == [{"a": 1}]


def test_extract_json_unparseable_returns_empty_list():
    assert extract_json("I could not extract any structured data.") == []


def test_extract_json_empty_string():
    assert extract_json("") == []
