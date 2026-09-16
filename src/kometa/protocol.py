"""EFGH / HGFE text protocol used by KOMETA CLI over BLE and USB CDC."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from kometa.constants import (
    PACKET_TAIL,
    REQUEST_HEAD,
    RESPONSE_HEAD,
    feature_for,
)
from kometa.exceptions import KometaCommandError, KometaNotAvailable

_FIELD_RE = re.compile(r"^([A-Z][A-Z0-9_]*)\s+(-?\d+)\s*$")
_NOT_AVAILABLE_MARKERS = (
    "CATEGORY NOT AVAILABLE",
    "INVALID COMMAND",
)
_ERROR_MARKERS = (
    "ERROR",
    "INVALID",
    "MISSING",
    "NO PARAMETERS",
    "READ-ONLY",
)


@dataclass
class KometaResponse:
    raw: str
    body: str
    fields: dict[str, int] = field(default_factory=dict)
    ok: bool = True
    not_available: bool = False
    message: str | None = None

    def raise_for_status(self) -> KometaResponse:
        if self.ok:
            return self
        if self.not_available:
            raise KometaNotAvailable(self.message or "not available", raw=self.raw)
        raise KometaCommandError(self.message or "command failed", raw=self.raw)

    def __str__(self) -> str:
        return self.raw.strip()


def normalize_command(text: str) -> str:
    """Turn user input into a single EFGH frame terminated with CRLF."""
    command = text.strip()
    if not command:
        raise ValueError("empty command")

    if not command.upper().startswith(REQUEST_HEAD):
        command = f"{REQUEST_HEAD} {command}"
    else:
        # Keep the canonical prefix casing expected by the firmware.
        command = f"{REQUEST_HEAD}{command[len(REQUEST_HEAD):]}"

    command = command.rstrip("\r\n") + PACKET_TAIL
    return command


def build_get(category: str, *params: str) -> str:
    payload = "ALL" if not params else " ".join(params)
    return normalize_command(f"GET {category} {payload}")


def build_set(category: str, values: dict[str, int] | None = None, default: bool = False) -> str:
    if default:
        return normalize_command(f"SET {category} DFLT")
    if not values:
        raise ValueError("SET needs values or default=True")
    assignments = ",".join(f"{tag}={int(value)}" for tag, value in values.items())
    return normalize_command(f"SET {category} {assignments}")


def looks_complete(buffer: str) -> bool:
    """True when the assembled notify stream looks like a finished HGFE frame."""
    text = buffer.lstrip("\x00")
    if RESPONSE_HEAD not in text:
        return False
    start = text.find(RESPONSE_HEAD)
    return PACKET_TAIL in text[start:]


def _last_frame(raw: str) -> str:
    """Keep the last HGFE frame if a welcome notify was concatenated."""
    text = raw.replace("\x00", "").strip()
    upper = text.upper()
    last = upper.rfind(RESPONSE_HEAD)
    if last < 0:
        return text
    return text[last:]


def parse_response(raw: str) -> KometaResponse:
    text = _last_frame(raw)
    if not text:
        return KometaResponse(raw=raw, body="", ok=False, message="empty response")

    body = text
    if text.upper().startswith(RESPONSE_HEAD):
        body = text[len(RESPONSE_HEAD) :].lstrip()

    fields: dict[str, int] = {}
    leftover: list[str] = []
    for line in body.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = line.strip()
        if not line:
            continue
        match = _FIELD_RE.match(line.upper())
        if match:
            fields[match.group(1)] = int(match.group(2))
        else:
            leftover.append(line)

    message = " ".join(leftover).strip() or None
    upper_message = (message or "").upper()
    not_available = any(marker in upper_message for marker in _NOT_AVAILABLE_MARKERS)
    is_error = (not fields) and message is not None and any(
        marker in upper_message for marker in _ERROR_MARKERS
    )

    return KometaResponse(
        raw=text,
        body=body.strip(),
        fields=fields,
        ok=not not_available and not is_error,
        not_available=not_available,
        message=message,
    )


def describe_capability(cmd: str, category: str | None = None) -> str | None:
    feature = feature_for(cmd, category)
    if feature is None:
        return None
    state = "supported" if feature.implemented else "not on this firmware"
    return f"{state}: {feature.notes}"
