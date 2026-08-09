from invoice_extraction.utils.text_utils import clean_raw_text, normalize_row, normalize_value


def test_clean_raw_text_collapses_underscores_and_whitespace():
    raw = "Name___John   Doe\nAmount: 750.00"
    cleaned = clean_raw_text(raw)
    assert "___" not in cleaned
    assert "  " not in cleaned
    assert "\n" not in cleaned


def test_clean_raw_text_empty_input():
    assert clean_raw_text("") == ""
    assert clean_raw_text(None) == ""


def test_normalize_value_strips_currency_symbols_and_commas():
    assert normalize_value("$1,250.00") == 1250.00


def test_normalize_value_lowercases_and_strips_spaces_for_non_numeric_strings():
    # commas and spaces are both stripped so "Doe, John" and "DoeJohn" compare equal
    assert normalize_value("  Doe, John ") == "doejohn"


def test_normalize_value_passthrough_for_non_string():
    assert normalize_value(5.0) == 5.0
    assert normalize_value(None) is None


def test_normalize_row_applies_to_every_field():
    row = {"bill_amount": "$525.00", "contractor_name": " Taylor, Sam "}
    assert normalize_row(row) == {"bill_amount": 525.0, "contractor_name": "taylorsam"}


def test_normalize_row_non_dict_returns_empty_dict():
    assert normalize_row(None) == {}
