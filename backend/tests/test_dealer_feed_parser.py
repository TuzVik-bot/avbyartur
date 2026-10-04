import pytest


def test_csv_feed_keeps_frame_serial_number_in_category_details_and_never_promotes_it_to_vin():
    import csv
    import io
    import json
    from app.feed_services import parse_feed_bytes, _normalized_record

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["dealer_external_id", "category_code", "category_details"])
    writer.writerow(["SERIAL-42", "special_equipment", json.dumps({
        "category_code": "special_equipment",
        "details": {"equipment_type": "Excavator", "frame_serial_number": "FRAME-2026/42"},
    })])
    rows = parse_feed_bytes(output.getvalue().encode(), feed_format="csv", field_mapping={})
    _, form, _, _ = _normalized_record(rows[0]["values"])
    assert form.category_details.details["frame_serial_number"] == "FRAME-2026/42"
    assert form.vin is None


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
