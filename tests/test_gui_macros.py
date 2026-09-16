from kometa.gui import DEFAULT_MACROS, MACRO_COUNT


def test_default_macros_fill_all_slots() -> None:
    assert len(DEFAULT_MACROS) == MACRO_COUNT
    assert DEFAULT_MACROS[0] == "EFGH GET APS ALL"
    assert DEFAULT_MACROS[4] == "EFGH GET APD ALL"
