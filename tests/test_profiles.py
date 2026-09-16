from kometa.profiles import (
    FEATURES_D1,
    Generation,
    display_name,
    generation_from_advertisement,
    generation_from_name,
    profile_for,
)


def test_generation_from_name() -> None:
    assert generation_from_name("KOMETA V1.0") is Generation.D1
    assert generation_from_name("KOMETA V2.0") is Generation.D2
    assert generation_from_name("kometa v1.0") is Generation.D1
    assert generation_from_name("speaker") is Generation.UNKNOWN


def test_generation_from_advertisement_uses_st_oui_for_d2() -> None:
    assert generation_from_advertisement("KOMETA V2.0", "00:80:E1:27:A4:A0") is Generation.D2
    assert generation_from_advertisement("KOMETA V1.0", "00:80:E1:27:A4:A0") is Generation.D2


def test_generation_from_advertisement_espressif_mac_is_d1() -> None:
    # Windows sometimes caches a V2.0 name onto the ESP32 dongle.
    assert generation_from_advertisement("KOMETA V2.0", "F4:12:FA:B5:8E:B1") is Generation.D1
    assert generation_from_advertisement("KOMETA V1.0", "F4:12:FA:B5:8E:B1") is Generation.D1


def test_display_name_follows_generation_not_windows_cache() -> None:
    assert display_name(Generation.D1, "KOMETA V2.0") == "KOMETA V1.0"
    assert display_name(Generation.D2, "KOMETA V1.0") == "KOMETA V2.0"


def test_d1_profile_uses_write_request() -> None:
    profile = profile_for(Generation.D1)
    assert profile.advertised_name == "KOMETA V1.0"
    assert profile.write_with_response is True
    assert profile.command_timeout_s >= 6.0
    assert FEATURES_D1[("GET", "HWS")].implemented
    assert FEATURES_D1[("SET", "SAS")].implemented
    assert FEATURES_D1[("HELP", None)].implemented


def test_reverse_uuid_matches_nimble_wire_order() -> None:
    from kometa.ble import _reverse_uuid
    from kometa.constants import TX_CHAR_UUID

    assert _reverse_uuid(TX_CHAR_UUID) == "604f83a8-18e7-7e96-4b42-977069177638"
    assert _reverse_uuid(_reverse_uuid(TX_CHAR_UUID)) == TX_CHAR_UUID


def test_d2_profile_hws_unavailable() -> None:
    profile = profile_for(Generation.D2)
    assert profile.write_with_response is False
    assert profile.features[("GET", "HWS")].implemented is False
    assert profile.features[("GET", "APS")].implemented is True
