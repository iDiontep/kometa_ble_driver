"""BLE transport over the system Bluetooth adapter (CellerLab 5.3 USB dongle)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak.exc import BleakError

from kometa.constants import (
    DEFAULT_COMMAND_TIMEOUT_S,
    DEFAULT_IDLE_S,
    DEFAULT_SCAN_TIMEOUT_S,
    DEVICE_NAME,
    DEVICE_NAME_PREFIX,
    MAX_CHAR_VALUE_LEN,
    RX_CHAR_UUID,
    SERVICE_UUID,
    TX_CHAR_UUID,
)
from kometa.exceptions import KometaDisconnected, KometaNotFound, KometaTimeout
from kometa.protocol import looks_complete

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FoundDevice:
    name: str
    address: str
    rssi: int | None


def _is_kometa(device: BLEDevice, adv: AdvertisementData) -> bool:
    name = (device.name or adv.local_name or "").strip()
    return name.upper().startswith(DEVICE_NAME_PREFIX)


async def scan(
    timeout: float = DEFAULT_SCAN_TIMEOUT_S,
    adapter: str | None = None,
) -> list[FoundDevice]:
    """Scan for KOMETA v2 advertisements using the Windows BLE adapter."""
    found: dict[str, FoundDevice] = {}

    def _callback(device: BLEDevice, adv: AdvertisementData) -> None:
        if not _is_kometa(device, adv):
            return
        name = (device.name or adv.local_name or DEVICE_NAME).strip()
        rssi = adv.rssi if adv.rssi is not None else getattr(device, "rssi", None)
        previous = found.get(device.address)
        if previous is None or (rssi is not None and (previous.rssi is None or rssi > previous.rssi)):
            found[device.address] = FoundDevice(name=name, address=device.address, rssi=rssi)

    # ADV payload on WB is name-only, so do not filter by service UUID.
    scanner = BleakScanner(_callback, adapter=adapter)
    await scanner.start()
    try:
        await asyncio.sleep(timeout)
    finally:
        await scanner.stop()

    return sorted(found.values(), key=lambda item: item.rssi or -999, reverse=True)


async def find_device(
    address: str | None = None,
    name: str = DEVICE_NAME,
    timeout: float = DEFAULT_SCAN_TIMEOUT_S,
    adapter: str | None = None,
) -> BLEDevice:
    """Wait until the named KOMETA (or a given address) shows up in advertising."""
    loop = asyncio.get_running_loop()
    found: asyncio.Future[BLEDevice] = loop.create_future()
    wanted_name = name.strip().upper()
    wanted_addr = address.strip().upper() if address else None

    def _callback(device: BLEDevice, adv: AdvertisementData) -> None:
        if found.done():
            return
        if wanted_addr and device.address.upper() != wanted_addr:
            return
        advertised = (device.name or adv.local_name or "").strip().upper()
        if wanted_addr:
            found.set_result(device)
            return
        if wanted_name == DEVICE_NAME.upper():
            if advertised.startswith(DEVICE_NAME_PREFIX):
                found.set_result(device)
            return
        if advertised == wanted_name:
            found.set_result(device)

    scanner = BleakScanner(_callback, adapter=adapter)
    await scanner.start()
    try:
        return await asyncio.wait_for(found, timeout=timeout)
    except asyncio.TimeoutError as exc:
        if wanted_addr:
            raise KometaNotFound(f"No BLE device at {address}") from exc
        raise KometaNotFound(f"No advertising device named {name!r}") from exc
    finally:
        await scanner.stop()


class KometaBle:
    """Write CLI frames to RX, reassemble HGFE replies from TX notifications."""

    def __init__(
        self,
        address: str | None = None,
        name: str = DEVICE_NAME,
        adapter: str | None = None,
        timeout: float = DEFAULT_COMMAND_TIMEOUT_S,
        idle: float = DEFAULT_IDLE_S,
        write_with_response: bool = False,
    ) -> None:
        self.address = address
        self.name = name
        self.adapter = adapter
        self.timeout = timeout
        self.idle = idle
        self.write_with_response = write_with_response
        self.client: BleakClient | None = None
        self._rx = bytearray()
        self._chunk = asyncio.Event()
        self._lock = asyncio.Lock()
        self._disconnected = asyncio.Event()
        self._on_unsolicited: Callable[[str], None] | None = None

    @property
    def is_connected(self) -> bool:
        return self.client is not None and self.client.is_connected

    def set_unsolicited_handler(self, handler: Callable[[str], None] | None) -> None:
        self._on_unsolicited = handler

    async def connect(
        self,
        scan_timeout: float = DEFAULT_SCAN_TIMEOUT_S,
    ) -> BLEDevice:
        device = await find_device(
            address=self.address,
            name=self.name,
            timeout=scan_timeout,
            adapter=self.adapter,
        )
        self.address = device.address
        client_kwargs: dict[str, object] = {
            "disconnected_callback": self._on_disconnect,
            "services": [SERVICE_UUID],
        }
        self.client = BleakClient(device, **client_kwargs)
        self._disconnected.clear()
        await self.client.connect()
        await self.client.start_notify(TX_CHAR_UUID, self._on_notify)
        await self._drain_welcome()
        logger.info("Connected to %s (%s)", device.name or self.name, device.address)
        return device

    async def disconnect(self) -> None:
        client = self.client
        self.client = None
        if client is None:
            return
        try:
            if client.is_connected:
                await client.stop_notify(TX_CHAR_UUID)
                await client.disconnect()
        except BleakError as exc:
            logger.debug("Disconnect ignored: %s", exc)

    async def write_command(self, frame: str) -> str:
        if self.client is None or not self.client.is_connected:
            raise KometaDisconnected("not connected")

        payload = frame.encode("ascii", errors="ignore")
        if not payload:
            raise ValueError("empty BLE payload")

        async with self._lock:
            self._rx.clear()
            self._chunk.clear()
            await self._write_chunks(payload)
            return await self._read_response()

    async def _write_chunks(self, payload: bytes) -> None:
        assert self.client is not None
        offset = 0
        while offset < len(payload):
            chunk = payload[offset : offset + MAX_CHAR_VALUE_LEN]
            try:
                await self.client.write_gatt_char(
                    RX_CHAR_UUID,
                    chunk,
                    response=self.write_with_response,
                )
            except BleakError:
                # Some Windows stacks reject Write Request on this characteristic.
                await self.client.write_gatt_char(RX_CHAR_UUID, chunk, response=False)
            offset += len(chunk)

    async def _read_response(self) -> str:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.timeout
        while True:
            if self._disconnected.is_set():
                raise KometaDisconnected("disconnected while waiting for HGFE")

            remaining = deadline - loop.time()
            if remaining <= 0:
                partial = self._decode()
                raise KometaTimeout("timed out waiting for HGFE response", partial=partial)

            wait = min(self.idle, remaining)
            try:
                await asyncio.wait_for(self._chunk.wait(), timeout=wait)
                self._chunk.clear()
                continue
            except asyncio.TimeoutError:
                text = self._decode()
                if looks_complete(text):
                    self._rx.clear()
                    return text
                if loop.time() >= deadline:
                    raise KometaTimeout("incomplete HGFE response", partial=text) from None

    def _decode(self) -> str:
        return bytes(self._rx).decode("ascii", errors="replace")

    def _on_notify(self, _char: BleakGATTCharacteristic, data: bytearray) -> None:
        if not data:
            return
        self._rx.extend(data)
        self._chunk.set()
        if self._lock.locked():
            return
        text = bytes(data).decode("ascii", errors="replace")
        if self._on_unsolicited is not None:
            self._on_unsolicited(text)

    def _on_disconnect(self, _client: BleakClient) -> None:
        self._disconnected.set()
        self._chunk.set()

    async def _drain_welcome(self) -> None:
        """Consume the optional `HGFE BLE ON` notify that arrives after CCCD enable."""
        try:
            await asyncio.wait_for(self._chunk.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            return
        self._chunk.clear()
        # Wait a short idle so a fragmented welcome message is fully collected.
        try:
            await asyncio.wait_for(self._chunk.wait(), timeout=self.idle)
            self._chunk.clear()
        except asyncio.TimeoutError:
            pass
        welcome = self._decode().strip()
        if welcome:
            logger.debug("Welcome: %s", welcome)
            if self._on_unsolicited is not None:
                self._on_unsolicited(welcome)
        self._rx.clear()

    async def __aenter__(self) -> KometaBle:
        await self.connect()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.disconnect()
