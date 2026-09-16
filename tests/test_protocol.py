"""Offline tests for the EFGH/HGFE parser. BLE hardware is not required."""

from kometa.protocol import build_get, build_set, looks_complete, normalize_command, parse_response


def test_normalize_adds_prefix_and_crlf() -> None:
    assert normalize_command("GET APS VOL") == "EFGH GET APS VOL\r\n"
    assert normalize_command("efgh GET APS VOL\n") == "EFGH GET APS VOL\r\n"


def test_build_get_set() -> None:
    assert build_get("APS") == "EFGH GET APS ALL\r\n"
    assert build_get("APS", "VOL") == "EFGH GET APS VOL\r\n"
    assert build_set("APS", {"VOL": 2}) == "EFGH SET APS VOL=2\r\n"
    assert build_set("APS", default=True) == "EFGH SET APS DFLT\r\n"


def test_parse_get_aps_all() -> None:
    raw = (
        "HGFE STAT 228 \r\n"
        "VOL 1 \r\n"
        "VLV_IND 0 \r\n"
        "TX_DEBUG 0 \r\n"
        "BTN_SOUND 1 \r\n"
        "\r\n"
    )
    response = parse_response(raw)
    assert response.ok
    assert response.fields["STAT"] == 228
    assert response.fields["VOL"] == 1
    assert response.fields["BTN_SOUND"] == 1


def test_parse_set_vol() -> None:
    response = parse_response("HGFE VOL 2 \r\n\r\n")
    assert response.ok
    assert response.fields == {"VOL": 2}


def test_parse_set_dflt() -> None:
    response = parse_response("HGFE Default APP settings\r\n")
    assert response.ok
    assert response.fields == {}
    assert response.message == "Default APP settings"


def test_parse_category_not_available() -> None:
    response = parse_response("HGFE Category not available\r\n")
    assert not response.ok
    assert response.not_available


def test_parse_readonly() -> None:
    response = parse_response("HGFE read-only\r\n")
    assert not response.ok
    assert not response.not_available


def test_parse_invalid_command() -> None:
    response = parse_response("HGFE Invalid Command\r\n")
    assert response.not_available


def test_looks_complete() -> None:
    assert not looks_complete("HG")
    assert looks_complete("HGFE VOL 2 \r\n")
    assert looks_complete("xxHGFE BLE ON\r\n")


def test_parse_skips_welcome_frame() -> None:
    raw = "HGFE BLE ON\r\nHGFE VOL 2 \r\n"
    response = parse_response(raw)
    assert response.ok
    assert response.fields == {"VOL": 2}
