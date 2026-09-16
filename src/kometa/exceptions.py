"""Errors raised by the KOMETA host driver."""

from __future__ import annotations


class KometaError(Exception):
    """Base error for the KOMETA driver."""


class KometaNotFound(KometaError):
    """No advertising KOMETA device was found."""


class KometaTimeout(KometaError):
    """Timed out waiting for a BLE notification or scan result."""

    def __init__(self, message: str, partial: str = "") -> None:
        extra = ""
        if partial:
            preview = partial.replace("\r", "\\r").replace("\n", "\\n")
            extra = f" [{preview}]"
        super().__init__(message + extra)
        self.partial = partial


class KometaDisconnected(KometaError):
    """The BLE connection dropped while a command was in flight."""


class KometaCommandError(KometaError):
    """The device returned an HGFE error payload."""

    def __init__(self, message: str, raw: str = "") -> None:
        super().__init__(message)
        self.raw = raw


class KometaNotAvailable(KometaCommandError):
    """Command or category exists in the d1 protocol but is not on this firmware."""
