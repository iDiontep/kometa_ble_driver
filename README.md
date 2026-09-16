# KOMETA v2 BLE driver

Python host for **KOMETA V2.0**. It uses the system Bluetooth adapter (CellerLab USB 5.3) and talks to the custom GATT service on the STM32WB.

Commands go to RX as `EFGH …`. Replies come back as TX notifications starting with `HGFE`.

## Firmware map (current WB build)

| Command | Status |
|---|---|
| `EFGH GET APS ALL` / `VOL` / … | works, RAM settings |
| `EFGH SET APS VOL=2` | works, **RAM only** |
| `EFGH SET APS DFLT` | works, RAM only |
| `EFGH GET APD ALL` | works, read-only |
| `HWS` / `SAS` / `HWD` / `SAD` | firmware: `Category not available` |
| EEPROM write after SET | not on WB yet |
| `SERVICE`, `FWV`, `HELP`, `SHIP`, … | firmware: `Invalid Command` |

Raw passthrough still sends those frames, so the same driver keeps working when the firmware grows.

GATT (same UUIDs as `ble-module`):

- service `3ba1eb58-dd27-8bbc-6c45-7c678cfca153`
- RX write `e1f75570-6196-46df-806c-5c6661445c5e`
- TX notify `38761769-7097-424b-967e-e718a8834f60`

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
python -m kometa get-apd
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
