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
from bleak.exc import BleakCharacteristicNotFoundError, BleakError

from kometa.constants import (
    DEFAULT_COMMAND_TIMEOUT_S,
    DEFAULT_IDLE_S,
    DEFAULT_SCAN_TIMEOUT_S,
    DEVICE_NAME,
    DEVICE_NAME_PREFIX,
    MAX_CHAR_VALUE_LEN,
    RX_CHAR_UUID,
    TX_CHAR_UUID,
)
from kometa.exceptions import KometaDisconnected, KometaNotFound, KometaTimeout
from kometa.profiles import Generation, display_name, generation_from_advertisement, profile_for
from kometa.protocol import looks_complete

logger = logging.getLogger(__name__)

_GAP = "00001800-0000-1000-8000-00805f9b34fb"
_GATT = "00001801-0000-1000-8000-00805f9b34fb"
_NORDIC_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
_NORDIC_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
_GATT_SETTLE_S = 2.0


def _reverse_uuid(uuid: str) -> str:
    """NimBLE BLE_UUID128_INIT is little-endian; some tables store the string order."""
    raw = uuid.replace("-", "")
    rev = bytes.fromhex(raw)[::-1].hex()
    return f"{rev[0:8]}-{rev[8:12]}-{rev[12:16]}-{rev[16:20]}-{rev[20:32]}"


_KNOWN_UART_PAIRS = (
    (RX_CHAR_UUID, TX_CHAR_UUID),
    (_reverse_uuid(RX_CHAR_UUID), _reverse_uuid(TX_CHAR_UUID)),
    (_NORDIC_RX, _NORDIC_TX),
)


@dataclass(frozen=True)
class FoundDevice:
    name: str
    address: str
    rssi: int | None
    generation: Generation = Generation.UNKNOWN


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
            generation = generation_from_advertisement(name, device.address)
            found[device.address] = FoundDevice(
                name=display_name(generation, name),
                address=device.address,
                rssi=rssi,
                generation=generation,
            )

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
        if wanted_name in {DEVICE_NAME.upper(), DEVICE_NAME_PREFIX}:
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
        self.generation = Generation.UNKNOWN
        self.advertised_name = name
        self._rx = bytearray()
        self._chunk = asyncio.Event()
        self._lock = asyncio.Lock()
        self._disconnected = asyncio.Event()
        self._on_unsolicited: Callable[[str], None] | None = None
        self._rx_uuid = RX_CHAR_UUID
        self._tx_uuid = TX_CHAR_UUID
        self._ble_device: BLEDevice | None = None

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
        cached_name = (device.name or self.name or "").strip()
        self.generation = generation_from_advertisement(cached_name, self.address)
        profile = profile_for(self.generation)
        self.advertised_name = display_name(self.generation, cached_name)
        self.timeout = max(self.timeout, profile.command_timeout_s)
        self.idle = max(self.idle, profile.idle_s)
        self.write_with_response = profile.write_with_response
        logger.info(
            "Using %s profile for %s (%s)",
            profile.generation.value,
            self.advertised_name or "unnamed",
            self.address,
        )
        self._ble_device = device
        self._disconnected.clear()
        # ESP32 NimBLE emits Service Changed while Windows is still enumerating GATT.
        # WinRT then logs "unhandled services changed" and start_notify fails.
        self.client = self._make_client(device, use_cached_services=False)
        await self._connect_and_subscribe()
        rx_uuid, tx_uuid = await self._wait_for_uart_chars()
        if rx_uuid is None or tx_uuid is None:
            logger.warning(
                "GATT not ready on %s after connect, reconnecting with Windows cache",
                self.address,
            )
            await self._drop_client()
            await asyncio.sleep(0.8)
            self._disconnected.clear()
            self.client = self._make_client(device, use_cached_services=True)
            await self._connect_and_subscribe()
            rx_uuid, tx_uuid = await self._wait_for_uart_chars()
        if rx_uuid is None or tx_uuid is None:
            raise BleakError(self._gatt_missing_message())
        self._rx_uuid = rx_uuid
        self._tx_uuid = tx_uuid
        logger.info("UART chars RX=%s TX=%s", self._rx_uuid, self._tx_uuid)
        try:
            await self.client.start_notify(self._tx_uuid, self._on_notify)
        except BleakCharacteristicNotFoundError as exc:
            raise BleakError(self._gatt_missing_message()) from exc
        await asyncio.sleep(0.25)
        await self._drain_welcome()
        self._disconnected.clear()
        logger.info("Connected to %s (%s)", self.advertised_name or self.name, device.address)
        return device

    def _make_client(self, device: BLEDevice, use_cached_services: bool) -> BleakClient:
        client = BleakClient(
            device,
            disconnected_callback=self._on_disconnect,
            timeout=30.0,
            winrt={"use_cached_services": use_cached_services},
        )
        backend = getattr(client, "_backend", None)
        if backend is not None and hasattr(backend, "_retry_on_services_changed"):
            backend._retry_on_services_changed = True
        return client

    async def _connect_and_subscribe(self) -> None:
        assert self.client is not None
        await self.client.connect()

    async def _drop_client(self) -> None:
        client = self.client
        self.client = None
        if client is None:
            return
        try:
            if client.is_connected:
                await client.disconnect()
        except BleakError:
            pass

    async def _wait_for_uart_chars(self) -> tuple[str | None, str | None]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + _GATT_SETTLE_S
        last: tuple[str | None, str | None] = (None, None)
        while True:
            last = self._resolve_uart_chars()
            if last[0] and last[1]:
                return last
            if loop.time() >= deadline:
                return last
            await asyncio.sleep(0.25)

    def _resolve_uart_chars(self) -> tuple[str | None, str | None]:
        if self.client is None:
            return None, None
        try:
            services = self.client.services
        except BleakError:
            return None, None
        if services is None:
            return None, None

        def _get(uuid: str) -> BleakGATTCharacteristic | None:
            try:
                return services.get_characteristic(uuid)
            except Exception:
                return None

        for rx_uuid, tx_uuid in _KNOWN_UART_PAIRS:
            if _get(rx_uuid) is not None and _get(tx_uuid) is not None:
                return rx_uuid, tx_uuid

        for service in services:
            if service.uuid.lower() in {_GAP, _GATT}:
                continue
            rx_char = None
            tx_char = None
            for char in service.characteristics:
                props = {item.lower() for item in char.properties}
                if tx_char is None and "notify" in props:
                    tx_char = char
                if rx_char is None and ("write" in props or "write-without-response" in props):
                    rx_char = char
            if rx_char is not None and tx_char is not None:
                logger.info(
                    "Resolved UART pair on %s: RX %s TX %s",
                    service.uuid,
                    rx_char.uuid,
                    tx_char.uuid,
                )
                return rx_char.uuid, tx_char.uuid
        return None, None

    def _gatt_missing_message(self) -> str:
        lines = [
            f"TX/RX characteristics not found on {self.address}.",
            "ESP32 ble-module often finishes GATT after Service Changed; retry Connect.",
            "Discovered services:",
        ]
        try:
            services = self.client.services if self.client is not None else None
            listed = list(services) if services is not None else []
            if not listed:
                lines.append("  (none — Windows GATT cache is empty)")
            else:
                for service in listed:
                    lines.append(f"  service {service.uuid}")
                    for char in service.characteristics:
                        lines.append(f"    {char.uuid}  {char.properties}")
        except Exception as exc:
            lines.append(f"  (could not list GATT: {exc})")
        return "\n".join(lines)

    async def disconnect(self) -> None:
        client = self.client
        self.client = None
        if client is None:
            return
        try:
            if client.is_connected:
                await client.stop_notify(self._tx_uuid)
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
            try:
                return await self._read_response()
            except KometaTimeout as exc:
                if self.generation is Generation.D1 and not (exc.partial or "").strip():
                    logger.warning(
                        "d1 got no HGFE notify, retrying write response=%s",
                        not self.write_with_response,
                    )
                    self.write_with_response = not self.write_with_response
                    self._rx.clear()
                    self._chunk.clear()
                    await self._write_chunks(payload)
                    return await self._read_response()
                raise

    async def _write_chunks(self, payload: bytes) -> None:
        assert self.client is not None
        offset = 0
        while offset < len(payload):
            chunk = payload[offset : offset + MAX_CHAR_VALUE_LEN]
            try:
                await self.client.write_gatt_char(
                    self._rx_uuid,
                    chunk,
                    response=self.write_with_response,
                )
            except BleakError as exc:
                logger.warning(
                    "GATT write response=%s failed: %s; trying opposite",
                    self.write_with_response,
                    exc,
                )
                await self.client.write_gatt_char(
                    self._rx_uuid,
                    chunk,
                    response=not self.write_with_response,
                )
                self.write_with_response = not self.write_with_response
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
                require_tail = self.generation is not Generation.D1
                if looks_complete(text, require_tail=require_tail):
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
