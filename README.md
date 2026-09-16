# KOMETA BLE driver (d1 + d2)

Python host for **KOMETA V1.0** (d1 + ESP32 `ble-module`) and **KOMETA V2.0** (d2 STM32WB).
Uses the CellerLab Bluetooth 5.3 adapter. Commands go to RX as `EFGH …`, replies come as TX notify `HGFE …`.

## Devices

| Advertisement | Hardware | Path |
|---|---|---|
| `KOMETA V1.0` | d1 STM32L0 + ESP32 | GATT write → UART → `uart_ble.c` |
| `KOMETA V2.0` | d2 STM32WB | onboard GATT, `cli.c` |

Same GATT UUIDs (`ble-module` / `kometa_ble_gatt.c`):

- service `3ba1eb58-dd27-8bbc-6c45-7c678cfca153`
- RX write `e1f75570-6196-46df-806c-5c6661445c5e`
- TX notify `38761769-7097-424b-967e-e718a8834f60`

d1 RX is **Write Request** only; the driver enables that automatically.

## Firmware map

| Command | d1 (`KOMETA V1.0`) | d2 (`KOMETA V2.0`) |
|---|---|---|
| `GET/SET APS` | RAM + EEPROM | RAM only |
| `GET APD` | yes | yes |
| `GET/SET HWS SAS` | RAM + EEPROM | `Category not available` |
| `GET HWD SAD` | yes | `Category not available` |
| `FWV HELP SERVICE SHIP RST FACTORY CHG` | yes | `Invalid Command` |

Scan lists both names. The client picks the profile from the advertisement.

## Install

Windows 10/11, Python 3.10+. Plug in the CellerLab Bluetooth 5.3 dongle. If the PC also has built-in Bluetooth, disable it so Windows uses the dongle.

**Do not upgrade pip** if a notice appears. **Do not use the ESP-IDF Python** (`~\.espressif\python_env\...`). After `python -m venv .venv` activate it, or call `.venv\Scripts\python.exe` directly:

```powershell
cd c:\Users\Ionin_da\workspace\kometa_ble_driver
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m kometa
```

Or double-click `run.bat`.

## Terminal GUI

```powershell
.\.venv\Scripts\python.exe -m kometa
.\.venv\Scripts\python.exe -m kometa gui
```

Окно как у Terminal 1.9b: Connect / ReScan, лог Receive / Transmit, строка команды, макросы M1–M24.

## CLI

```powershell
python -m kometa scan
python -m kometa get-aps
python -m kometa get-aps VOL
python -m kometa set-aps VOL=2
python -m kometa set-aps-dflt
python -m kometa get-hws
python -m kometa get-hwd
python -m kometa cmd "HELP"
python -m kometa cmd "GET APS ALL"
python -m kometa shell
```

`shell` accepts both `GET APS ALL` and `EFGH GET APS ALL`.

## Library

```python
import asyncio
from kometa import KometaClient

async def main():
    async with KometaClient() as k:
        print(await k.get_aps_all())
        print(await k.set_aps(VOL=2))
        print(await k.get_apd_all())

asyncio.run(main())
```

Connect by address if several devices are in range:

```python
KometaClient(address="AA:BB:CC:DD:EE:FF")
```

## Tests

```powershell
pytest
```
