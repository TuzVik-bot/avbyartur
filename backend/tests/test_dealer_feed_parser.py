import pytest


def test_csv_parser_maps_external_columns_to_stable_fields():
    from app.feed_services import parse_feed_bytes

    content = b"stock_number,brand,cost\nA-100,Toyota,12000.50\n"
    rows = parse_feed_bytes(
        content,
        feed_format="csv",
        field_mapping={
            "dealer_external_id": "stock_number",
            "manual_make": "brand",
            "price_amount": "cost",
        },
    )

    assert rows == [
        {
            "row_number": 2,
            "values": {
                "dealer_external_id": "A-100",
                "manual_make": "Toyota",
                "price_amount": "12000.50",
            },
        }
    ]


def test_xml_parser_rejects_doctype_and_entity_declarations():
    from app.feed_services import FeedParseError, parse_feed_bytes

    content = b'<!DOCTYPE listings [<!ENTITY x "expanded">]><listings><listing><dealer_external_id>A-1</dealer_external_id></listing></listings>'

    with pytest.raises(FeedParseError) as caught:
        parse_feed_bytes(content, feed_format="xml", field_mapping={})

    assert caught.value.code == "unsafe_xml"


def test_parser_rejects_oversized_feed_before_decoding():
    from app.feed_services import FeedParseError, MAX_FEED_BYTES, parse_feed_bytes

    with pytest.raises(FeedParseError) as caught:
        parse_feed_bytes(b"a" * (MAX_FEED_BYTES + 1), feed_format="csv", field_mapping={})

    assert caught.value.code == "feed_too_large"


def test_csv_parser_keeps_overflow_as_a_row_error_and_parses_following_rows():
    from app.feed_services import parse_feed_bytes

    records = parse_feed_bytes(
        b"stock_number,brand\nA-1,Toyota,extra\nA-2,Lada\n",
        feed_format="csv",
        field_mapping={"dealer_external_id": "stock_number", "manual_make": "brand"},
    )

    assert records == [
        {
            "row_number": 2,
            "values": {},
            "error_code": "malformed_row",
            "error_message": "CSV row contains more values than the header",
        },
        {"row_number": 3, "values": {"dealer_external_id": "A-2", "manual_make": "Lada"}},
    ]


def test_csv_parser_accepts_windows_1251_when_utf8_decoding_fails():
    from app.feed_services import parse_feed_bytes

    content = "артикул;марка\nA-1;Лада\n".replace(";", ",").encode("cp1251")

    rows = parse_feed_bytes(
        content,
        feed_format="csv",
        field_mapping={"dealer_external_id": "артикул", "manual_make": "марка"},
    )

    assert rows == [{"row_number": 2, "values": {"dealer_external_id": "A-1", "manual_make": "Лада"}}]


def test_csv_parser_prefers_utf8_with_bom_over_windows_1251():
    from app.feed_services import parse_feed_bytes

    content = "﻿артикул,марка\nA-1,Лада\n".encode("utf-8")

    rows = parse_feed_bytes(
        content,
        feed_format="csv",
        field_mapping={"dealer_external_id": "артикул", "manual_make": "марка"},
    )

    assert rows[0]["values"] == {"dealer_external_id": "A-1", "manual_make": "Лада"}


def test_xml_parser_rejects_utf16_doctype_that_bypasses_the_byte_pattern():
    from app.feed_services import FeedParseError, parse_feed_bytes

    content = (
        '<?xml version="1.0" encoding="UTF-16"?>'
        '<!DOCTYPE listings [<!ENTITY x "expanded">]>'
        "<listings><listing><dealer_external_id>&x;</dealer_external_id></listing></listings>"
    ).encode("utf-16")

    with pytest.raises(FeedParseError) as caught:
        parse_feed_bytes(content, feed_format="xml", field_mapping={})

    assert caught.value.code == "unsafe_xml"


def test_xml_parser_uses_defusedxml():
    from app import feed_services

    assert feed_services.DefusedET.__name__ == "defusedxml.ElementTree"


def test_xml_parser_still_reads_a_plain_feed():
    from app.feed_services import parse_feed_bytes

    content = "<listings><listing><dealer_external_id>A-1</dealer_external_id><manual_make>Лада</manual_make></listing></listings>"

    rows = parse_feed_bytes(content.encode(), feed_format="xml", field_mapping={})

    assert rows == [{"row_number": 1, "values": {"dealer_external_id": "A-1", "manual_make": "Лада"}}]
