"""KOMETA d1 (ESP32 ble-module) vs d2 (STM32WB) profiles."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from kometa.constants import Feature


class Generation(str, Enum):
    D1 = "d1"
    D2 = "d2"
    UNKNOWN = "unknown"


DEVICE_NAME_D1 = "KOMETA V1.0"
DEVICE_NAME_D2 = "KOMETA V2.0"

HWS_TAGS = (
    "STAT",
    "ANG_MAX",
    "ANG_MIN",
    "TEN_MAX",
    "TEN_MIN",
    "OPA_OFS",
    "TEN_DIR",
    "TEMP_REF",
    "TEN_TARGET",
    "TEMP_UVK",
    "TEMP_MAX",
    "TEMP_MIN",
    "TIM22_PSC",
    "TIM22_ARR",
    "TIM22_CCR1",
    "TIM22_CCR2",
)

HWD_TAGS = (
    "HW_INITED",
    "ANGLE_RAW",
    "ANGLE_LIN",
    "ANGLE_DEG",
    "MCU_VDDA_MV",
    "TEMP",
    "VBAT_MV",
    "THENSO_RAW",
    "THENSO_VOLT",
    "THENSO_NORM",
    "THENSO_FILTERED",
    "VALVE_CHARGE_ST",
    "VALVE_STATE",
    "BLE_PWR",
    "LDC_PWR",
    "OPAMP_PWR",
    "THENSO_PWR",
    "BQ25601_VBUS_STAT",
    "BQ25601_DEVICE_PN",
    "BQ25601_CHG_ST",
    "BQ25601_QON",
    "BQ25601_STAT",
    "BQ25601_DEMO_BIT",
    "BQ25601_REV",
    "BQ25601_VBUS",
    "BQ25601_CHG_CURRENT",
    "BQ25601_NTC",
    "LED_VALS_0",
    "LED_VALS_1",
    "LED_VALS_2",
    "LED_VALS_3",
)

SAS_TAGS = (
    "STAT",
    "MODE",
    "BRAMP_PROT",
    "HEEL_MM",
    "EXT_DLY",
    "FLX_TIME",
    "PRE_SWG",
    "HEEL_MAX",
    "SWG_SPD",
    "TRQ_LIM",
    "MAX_SPL",
    "MIN_SPL",
    "SWG_MOM",
    "EXT_ANG",
    "T1",
    "T2",
    "MIN_SWR",
    "SWG_RT",
    "SUB_MOM",
    "COEF_MOM",
    "ADD_SWR",
    "ADD_ANG",
    "UNL_MOM",
    "HITCH_T",
    "LOAD_MIN",
    "RAMP_THR",
    "TEN_OFS",
)

SAD_TAGS = (
    "ANG_POS",
    "RATE",
    "MOMENT",
    "PEAK_MOM",
    "MIN_MOM",
    "EXT_HOLD_T",
    "T_FIRE",
    "POS_SENS",
    "STATE",
    "VLV_FLAG",
    "BENT_FLAG",
    "EXT_FLAG",
    "STEPS",
    "LAST_STEP",
    "ERR",
)


FEATURES_D2: dict[tuple[str, str | None], Feature] = {
    ("GET", "APS"): Feature(True, "Application settings in RAM"),
    ("SET", "APS"): Feature(True, "Changes RAM only — EEPROM write is not implemented on WB"),
    ("GET", "APD"): Feature(True, "Runtime data, read-only"),
    ("SET", "APD"): Feature(False, "Firmware answers read-only"),
    ("GET", "HWS"): Feature(False, "Category not available on WB"),
    ("SET", "HWS"): Feature(False, "Category not available on WB"),
    ("GET", "SAS"): Feature(False, "Category not available on WB"),
    ("SET", "SAS"): Feature(False, "Category not available on WB"),
    ("GET", "HWD"): Feature(False, "Category not available on WB"),
    ("SET", "HWD"): Feature(False, "Category not available on WB"),
    ("GET", "SAD"): Feature(False, "Category not available on WB"),
    ("SET", "SAD"): Feature(False, "Category not available on WB"),
    ("FWV", None): Feature(False, "Not in the v2 CLI yet"),
    ("HELP", None): Feature(False, "Not in the v2 CLI yet"),
    ("CHG", None): Feature(False, "Not in the v2 CLI yet"),
    ("SERVICE", None): Feature(False, "Not in the v2 CLI yet"),
    ("RST", None): Feature(False, "Not in the v2 CLI yet"),
    ("SHIP", None): Feature(False, "Not in the v2 CLI yet"),
    ("DATA", None): Feature(False, "Not in the v2 CLI yet"),
    ("FACTORY", None): Feature(False, "Not in the v2 CLI yet"),
    ("USB_DFU", None): Feature(False, "Not in the v2 CLI yet"),
    ("USB_CDC", None): Feature(False, "Not in the v2 CLI yet"),
    ("SLEEP", None): Feature(False, "Not in the v2 CLI yet"),
    ("STOP", None): Feature(False, "Not in the v2 CLI yet"),
}

FEATURES_D1: dict[tuple[str, str | None], Feature] = {
    ("GET", "APS"): Feature(True, "Application settings, SET also writes EEPROM"),
    ("SET", "APS"): Feature(True, "RAM + EEPROM"),
    ("GET", "APD"): Feature(True, "Runtime data, read-only"),
    ("SET", "APD"): Feature(False, "read-only"),
    ("GET", "HWS"): Feature(True, "Hardware settings, SET writes EEPROM"),
    ("SET", "HWS"): Feature(True, "RAM + EEPROM"),
    ("GET", "SAS"): Feature(True, "Step-algorithm settings, SET writes EEPROM"),
    ("SET", "SAS"): Feature(True, "RAM + EEPROM"),
    ("GET", "HWD"): Feature(True, "Live hardware data, GET only"),
    ("SET", "HWD"): Feature(False, "read-only"),
    ("GET", "SAD"): Feature(True, "Step-algorithm runtime, GET only"),
    ("SET", "SAD"): Feature(False, "read-only"),
    ("FWV", None): Feature(True, "Firmware version"),
    ("HELP", None): Feature(True, "Full CLI help (~3.5 KB over ble-module)"),
    ("CHG", None): Feature(True, "Battery percent"),
    ("SERVICE", None): Feature(True, "Service / calibration mode"),
    ("RST", None): Feature(True, "Reset"),
    ("SHIP", None): Feature(True, "Shipping mode"),
    ("DATA", None): Feature(True, "Step-algorithm data burst"),
    ("FACTORY", None): Feature(True, "Factory defaults + restart"),
    ("USB_DFU", None): Feature(True, "USB DFU bootloader"),
    ("USB_CDC", None): Feature(True, "USB CDC"),
    ("SLEEP", None): Feature(True, "Enter SLEEP"),
    ("STOP", None): Feature(True, "Enter STOP"),
}


@dataclass(frozen=True)
class DeviceProfile:
    generation: Generation
    advertised_name: str
    write_with_response: bool
    command_timeout_s: float
    idle_s: float
    help_timeout_s: float
    features: dict[tuple[str, str | None], Feature]
    notes: str


PROFILE_D1 = DeviceProfile(
    generation=Generation.D1,
    advertised_name=DEVICE_NAME_D1,
    write_with_response=True,
    command_timeout_s=6.0,
    idle_s=0.45,
    help_timeout_s=12.0,
    features=FEATURES_D1,
    notes="KOMETA d1 via ESP32 ble-module (UART bridge, GATT write-with-response)",
)

PROFILE_D2 = DeviceProfile(
    generation=Generation.D2,
    advertised_name=DEVICE_NAME_D2,
    write_with_response=False,
    command_timeout_s=3.0,
    idle_s=0.18,
    help_timeout_s=3.0,
    features=FEATURES_D2,
    notes="KOMETA d2 STM32WB onboard BLE",
)

PROFILE_UNKNOWN = DeviceProfile(
    generation=Generation.UNKNOWN,
    advertised_name="KOMETA",
    write_with_response=True,
    command_timeout_s=6.0,
    idle_s=0.28,
    help_timeout_s=12.0,
    features=FEATURES_D2,
    notes="Unknown KOMETA advertisement; try d1-safe BLE writes",
)


def generation_from_name(name: str | None) -> Generation:
    upper = (name or "").strip().upper()
    if "V1.0" in upper or upper.startswith("KOMETA V1"):
        return Generation.D1
    if "V2.0" in upper or upper.startswith("KOMETA V2"):
        return Generation.D2
    return Generation.UNKNOWN


def generation_from_address(address: str | None) -> Generation:
    """STM32WB uses ST OUI 00:80:E1."""
    compact = (address or "").upper().replace("-", ":")
    if compact.startswith("00:80:E1"):
        return Generation.D2
    return Generation.UNKNOWN


def generation_from_advertisement(name: str | None, address: str | None = None) -> Generation:
    by_mac = generation_from_address(address)
    by_name = generation_from_name(name)
    if by_mac is Generation.D2:
        return Generation.D2
    compact = (address or "").upper().replace("-", ":")
    # ESP32 ble-module: not ST OUI. Windows sometimes caches a V2.0 name on d1.
    if compact and not compact.startswith("00:80:E1") and (name or "").upper().startswith("KOMETA"):
        return Generation.D1
    return by_name


def display_name(generation: Generation, advertised: str | None = None) -> str:
    """Canonical GAP name for the generation. Windows may cache V2.0 onto a d1 MAC."""
    if generation is Generation.D1:
        return DEVICE_NAME_D1
    if generation is Generation.D2:
        return DEVICE_NAME_D2
    return (advertised or "").strip() or "KOMETA"


def profile_for(generation: Generation) -> DeviceProfile:
    if generation is Generation.D1:
        return PROFILE_D1
    if generation is Generation.D2:
        return PROFILE_D2
    return PROFILE_UNKNOWN


def feature_for(cmd: str, category: str | None = None, generation: Generation = Generation.D2) -> Feature | None:
    key = (cmd.upper(), category.upper() if category else None)
    return profile_for(generation).features.get(key)
