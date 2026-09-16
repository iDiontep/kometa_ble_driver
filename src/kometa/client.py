"""High-level KOMETA client: d1 (ble-module) and d2 (STM32WB)."""

from __future__ import annotations

import logging
from collections.abc import Mapping

from kometa.ble import KometaBle
from kometa.constants import (
    Category,
    Command,
    DEVICE_NAME,
    RUNTIME_GET_ONLY,
)
from kometa.exceptions import KometaNotAvailable
from kometa.profiles import Generation, feature_for, profile_for
from kometa.protocol import (
    KometaResponse,
    build_get,
    build_set,
    describe_capability,
    normalize_command,
    parse_response,
)

logger = logging.getLogger(__name__)


class KometaClient:
    """Talk to KOMETA d1 or d2 over the CellerLab Bluetooth 5.3 adapter."""

    def __init__(
        self,
        address: str | None = None,
        name: str = DEVICE_NAME,
        adapter: str | None = None,
        timeout: float = 3.0,
        raise_on_error: bool = True,
    ) -> None:
        self.transport = KometaBle(address=address, name=name, adapter=adapter, timeout=timeout)
        self.raise_on_error = raise_on_error

    @property
    def address(self) -> str | None:
        return self.transport.address

    @property
    def advertised_name(self) -> str:
        return self.transport.advertised_name

    @property
    def generation(self) -> Generation:
        return self.transport.generation

    @property
    def is_connected(self) -> bool:
        return self.transport.is_connected

    async def connect(self, scan_timeout: float = 8.0) -> None:
        await self.transport.connect(scan_timeout=scan_timeout)

    async def disconnect(self) -> None:
        await self.transport.disconnect()

    async def command(self, text: str) -> KometaResponse:
        frame = normalize_command(text)
        previous_timeout = self.transport.timeout
        if _is_help(frame):
            self.transport.timeout = max(previous_timeout, profile_for(self.generation).help_timeout_s)
        try:
            raw = await self.transport.write_command(frame)
        finally:
            self.transport.timeout = previous_timeout
        response = parse_response(raw)
        if self.raise_on_error:
            response.raise_for_status()
        return response

    async def get(self, category: str | Category, *params: str) -> dict[str, int]:
        cat = _category(category)
        _warn_if_missing(Command.GET.value, cat.value, self.generation)
        response = await self.command(build_get(cat.value, *params))
        return response.fields

    async def set(
        self,
        category: str | Category,
        values: Mapping[str, int] | None = None,
        *,
        default: bool = False,
        **kwargs: int,
    ) -> KometaResponse:
        cat = _category(category)
        if cat in RUNTIME_GET_ONLY:
            raise KometaNotAvailable(f"{cat.value} is read-only")
        _warn_if_missing(Command.SET.value, cat.value, self.generation)
        merged = dict(values or {})
        merged.update(kwargs)
        return await self.command(build_set(cat.value, merged, default=default))

    async def get_aps(self, *params: str) -> dict[str, int]:
        if params:
            return await self.get(Category.APS, *params)
        return await self.get_aps_all()

    async def get_aps_all(self) -> dict[str, int]:
        return await self.get(Category.APS, "ALL")

    async def set_aps(self, values: Mapping[str, int] | None = None, **kwargs: int) -> dict[str, int]:
        response = await self.set(Category.APS, values, **kwargs)
        return response.fields

    async def set_aps_default(self) -> KometaResponse:
        return await self.set(Category.APS, default=True)

    async def get_apd(self, *params: str) -> dict[str, int]:
        if params:
            return await self.get(Category.APD, *params)
        return await self.get_apd_all()

    async def get_apd_all(self) -> dict[str, int]:
        return await self.get(Category.APD, "ALL")

    async def get_hws(self, *params: str) -> dict[str, int]:
        return await self.get(Category.HWS, *(params or ("ALL",)))

    async def set_hws(self, values: Mapping[str, int] | None = None, **kwargs: int) -> dict[str, int]:
        response = await self.set(Category.HWS, values, **kwargs)
        return response.fields

    async def get_sas(self, *params: str) -> dict[str, int]:
        return await self.get(Category.SAS, *(params or ("ALL",)))

    async def set_sas(self, values: Mapping[str, int] | None = None, **kwargs: int) -> dict[str, int]:
        response = await self.set(Category.SAS, values, **kwargs)
        return response.fields

    async def get_hwd(self, *params: str) -> dict[str, int]:
        return await self.get(Category.HWD, *(params or ("ALL",)))

    async def get_sad(self, *params: str) -> dict[str, int]:
        return await self.get(Category.SAD, *(params or ("ALL",)))

    async def fwv(self) -> KometaResponse:
        return await self._special(Command.FWV)

    async def help(self) -> KometaResponse:
        return await self._special(Command.HELP)

    async def chg(self) -> KometaResponse:
        return await self._special(Command.CHG)

    async def service(self, *stages: str) -> KometaResponse:
        extra = " ".join(stages)
        text = f"SERVICE {extra}".strip()
        _warn_if_missing(Command.SERVICE.value, None, self.generation)
        return await self.command(text)

    async def ship(self) -> KometaResponse:
        return await self._special(Command.SHIP)

    async def reset(self) -> KometaResponse:
        return await self._special(Command.RST)

    async def factory(self) -> KometaResponse:
        return await self._special(Command.FACTORY)

    async def _special(self, cmd: Command) -> KometaResponse:
        _warn_if_missing(cmd.value, None, self.generation)
        return await self.command(cmd.value)

    async def __aenter__(self) -> KometaClient:
        await self.connect()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.disconnect()


def _category(value: str | Category) -> Category:
    if isinstance(value, Category):
        return value
    try:
        return Category[value.upper()]
    except KeyError as exc:
        raise ValueError(f"unknown category {value!r}") from exc


def _is_help(frame: str) -> bool:
    body = frame.upper().replace("EFGH", "", 1).strip()
    return body.startswith("HELP")


def _warn_if_missing(cmd: str, category: str | None, generation: Generation) -> None:
    feature = feature_for(cmd, category, generation)
    if feature is not None and not feature.implemented:
        note = describe_capability(cmd, category, generation)
        logger.info(
            "Sending %s anyway (%s)",
            cmd if not category else f"{cmd} {category}",
            note or "not implemented on this firmware",
        )
