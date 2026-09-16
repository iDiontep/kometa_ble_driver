"""GATT UUIDs, CLI tags and firmware capability map for KOMETA v2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

DEVICE_NAME = "KOMETA V2.0"
DEVICE_NAME_PREFIX = "KOMETA"

# Custom GATT service from STM32_WPAN/App/kometa_ble_gatt.c (same UUIDs as ble-module).
SERVICE_UUID = "3ba1eb58-dd27-8bbc-6c45-7c678cfca153"
RX_CHAR_UUID = "e1f75570-6196-46df-806c-5c6661445c5e"  # write / write-without-response
TX_CHAR_UUID = "38761769-7097-424b-967e-e718a8834f60"  # notify

REQUEST_HEAD = "EFGH"
RESPONSE_HEAD = "HGFE"
PACKET_TAIL = "\r\n"
BLE_ON_MESSAGE = "HGFE BLE ON"

# Characteristic value length on the WB firmware.
MAX_CHAR_VALUE_LEN = 128

DEFAULT_SCAN_TIMEOUT_S = 8.0
DEFAULT_COMMAND_TIMEOUT_S = 3.0
DEFAULT_IDLE_S = 0.18


class Category(str, Enum):
    APS = "APS"  # application settings (RAM)
    APD = "APD"  # application runtime data (GET only)
    HWS = "HWS"  # hardware settings — not on WB yet
    SAS = "SAS"  # step-algorithm settings — not on WB yet
    HWD = "HWD"  # live hardware data — not on WB yet
    SAD = "SAD"  # step-algorithm runtime — not on WB yet


class Command(str, Enum):
    GET = "GET"
    SET = "SET"
    FWV = "FWV"
    HELP = "HELP"
    CHG = "CHG"
    SERVICE = "SERVICE"
    RST = "RST"
    SHIP = "SHIP"
    DATA = "DATA"
    FACTORY = "FACTORY"
    BLE_OK = "BLE_OK"
    BLE_ON = "BLE_ON"
    BLE_OFF = "BLE_OFF"
    BLE_CON = "BLE_CON"
    BLE_DISCON = "BLE_DISCON"
    USB_DFU = "USB_DFU"
    USB_CDC = "USB_CDC"
    SLEEP = "SLEEP"
    STOP = "STOP"


# Tags currently exposed by Logic/Inc/app.h on KOMETA v2.
APS_TAGS = (
    "STAT",
    "VOL",
    "VLV_IND",
    "TX_DEBUG",
    "BTN_SOUND",
    "LPS",
    "SLEEP_TIME",
    "SLEEP_INTERVAL",
    "STOP_TIME",
    "STOP_INTERVAL",
    "SHIP_TIME",
)

APD_TAGS = (
    "FSM_STATE",
    "WORK_STATE",
    "BLE_STATE",
    "BLE_CON",
    "BLE_MIN",
    "RX_DATA",
    "CHARGE",
    "TICKS",
    "CHG_STAT",
    "POWER_MODE",
    "LP_TIMER",
)

RUNTIME_GET_ONLY = {Category.APD, Category.HWD, Category.SAD}
SETTINGS_CATEGORIES = {Category.APS, Category.HWS, Category.SAS}


@dataclass(frozen=True)
class Feature:
    implemented: bool
    notes: str


# Matches Logic/Src/cli.c on the current WB firmware.
FEATURES: dict[tuple[str, str | None], Feature] = {
    ("GET", "APS"): Feature(True, "Application settings in RAM"),
    ("SET", "APS"): Feature(True, "Changes RAM only — EEPROM write is not implemented on WB"),
    ("GET", "APD"): Feature(True, "Runtime data, read-only"),
    ("SET", "APD"): Feature(False, "Firmware answers read-only"),
    ("GET", "HWS"): Feature(False, "Category not available"),
    ("SET", "HWS"): Feature(False, "Category not available"),
    ("GET", "SAS"): Feature(False, "Category not available"),
    ("SET", "SAS"): Feature(False, "Category not available"),
    ("GET", "HWD"): Feature(False, "Category not available"),
    ("SET", "HWD"): Feature(False, "Category not available"),
    ("GET", "SAD"): Feature(False, "Category not available"),
    ("SET", "SAD"): Feature(False, "Category not available"),
    ("FWV", None): Feature(False, "Special command is not in the v2 CLI yet"),
    ("HELP", None): Feature(False, "Special command is not in the v2 CLI yet"),
    ("CHG", None): Feature(False, "Special command is not in the v2 CLI yet"),
    ("SERVICE", None): Feature(False, "Special command is not in the v2 CLI yet"),
    ("RST", None): Feature(False, "Special command is not in the v2 CLI yet"),
    ("SHIP", None): Feature(False, "Special command is not in the v2 CLI yet"),
    ("DATA", None): Feature(False, "Special command is not in the v2 CLI yet"),
    ("FACTORY", None): Feature(False, "Special command is not in the v2 CLI yet"),
    ("USB_DFU", None): Feature(False, "Special command is not in the v2 CLI yet"),
    ("USB_CDC", None): Feature(False, "Special command is not in the v2 CLI yet"),
    ("SLEEP", None): Feature(False, "Special command is not in the v2 CLI yet"),
    ("STOP", None): Feature(False, "Special command is not in the v2 CLI yet"),
}


def feature_for(cmd: str, category: str | None = None) -> Feature | None:
    key = (cmd.upper(), category.upper() if category else None)
    return FEATURES.get(key)
