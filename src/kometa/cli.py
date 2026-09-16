"""Command-line front-end: scan, GET/SET, raw EFGH, interactive shell."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from kometa.ble import scan
from kometa.client import KometaClient
from kometa.exceptions import KometaError
from kometa.protocol import KometaResponse

_LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format=_LOG_FORMAT)
    if args.action in (None, "gui"):
        from kometa.gui import run_app

        run_app()
        return 0
    try:
        return asyncio.run(_dispatch(args))
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 130
    except KometaError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kometa",
        description="BLE host driver for CellerLab KOMETA d1 (ble-module) and d2 (STM32WB)",
    )
    parser.add_argument("--address", help="BLE address, skip scan if given")
    parser.add_argument("--name", default="KOMETA", help="Advertised name or prefix (default: any KOMETA)")
    parser.add_argument("--adapter", help="Bluetooth adapter id (Windows radio / Linux hciX)")
    parser.add_argument("--timeout", type=float, default=3.0, help="Command timeout in seconds")
    parser.add_argument("--scan-timeout", type=float, default=8.0, help="Scan timeout in seconds")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="action")
    sub.add_parser("gui", help="Open the terminal-style window")
    sub.add_parser("scan", help="List nearby KOMETA devices")

    sub.add_parser("get-aps", help="GET APS ALL or listed tags").add_argument("tags", nargs="*")
    set_aps = sub.add_parser("set-aps", help="SET APS TAG=value ...")
    set_aps.add_argument("assignments", nargs="+", help="VOL=2 TX_DEBUG=1")
    sub.add_parser("set-aps-dflt", help="SET APS DFLT (RAM only on WB)")
    sub.add_parser("get-apd", help="GET APD ALL or listed tags").add_argument("tags", nargs="*")
    sub.add_parser("get-hws", help="GET HWS ALL (d1)").add_argument("tags", nargs="*")
    sub.add_parser("get-sas", help="GET SAS ALL (d1)").add_argument("tags", nargs="*")
    sub.add_parser("get-hwd", help="GET HWD ALL (d1)").add_argument("tags", nargs="*")
    sub.add_parser("get-sad", help="GET SAD ALL (d1)").add_argument("tags", nargs="*")

    cmd = sub.add_parser("cmd", help="Send a raw CLI frame (EFGH is optional)")
    cmd.add_argument("text", nargs="+", help='Example: GET APS VOL')

    sub.add_parser("shell", help="Interactive CLI over BLE")
    return parser


async def _dispatch(args: argparse.Namespace) -> int:
    if args.action == "scan":
        devices = await scan(timeout=args.scan_timeout, adapter=args.adapter)
        if not devices:
            print("No KOMETA devices found. Is the CellerLab 5.3 adapter the active Windows Bluetooth radio?")
            return 1
        for device in devices:
            rssi = f"{device.rssi} dBm" if device.rssi is not None else "n/a"
            print(f"{device.address}  {device.name}  [{device.generation.value}]  rssi={rssi}")
        return 0

    async with KometaClient(
        address=args.address,
        name=args.name,
        adapter=args.adapter,
        timeout=args.timeout,
        raise_on_error=False,
    ) as client:
        if args.action == "get-aps":
            tags = tuple(tag.upper() for tag in args.tags) or ("ALL",)
            _print_response(await client.command(f"GET APS {' '.join(tags)}"))
        elif args.action == "set-aps":
            payload = ",".join(args.assignments)
            _print_response(await client.command(f"SET APS {payload}"))
        elif args.action == "set-aps-dflt":
            _print_response(await client.command("SET APS DFLT"))
        elif args.action == "get-apd":
            tags = tuple(tag.upper() for tag in args.tags) or ("ALL",)
            _print_response(await client.command(f"GET APD {' '.join(tags)}"))
        elif args.action == "get-hws":
            tags = tuple(tag.upper() for tag in args.tags) or ("ALL",)
            _print_response(await client.command(f"GET HWS {' '.join(tags)}"))
        elif args.action == "get-sas":
            tags = tuple(tag.upper() for tag in args.tags) or ("ALL",)
            _print_response(await client.command(f"GET SAS {' '.join(tags)}"))
        elif args.action == "get-hwd":
            tags = tuple(tag.upper() for tag in args.tags) or ("ALL",)
            _print_response(await client.command(f"GET HWD {' '.join(tags)}"))
        elif args.action == "get-sad":
            tags = tuple(tag.upper() for tag in args.tags) or ("ALL",)
            _print_response(await client.command(f"GET SAD {' '.join(tags)}"))
        elif args.action == "cmd":
            _print_response(await client.command(" ".join(args.text)))
        elif args.action == "shell":
            await _shell(client)
        else:
            raise SystemExit(f"unknown action {args.action}")
    return 0


def _print_response(response: KometaResponse) -> None:
    if response.fields:
        width = max(len(tag) for tag in response.fields)
        for tag, value in response.fields.items():
            print(f"{tag:<{width}}  {value}")
        if response.message:
            print(response.message)
        return
    print(response.body or response.raw)


async def _shell(client: KometaClient) -> None:
    print(
        f"Connected to {client.advertised_name or client.address} [{client.generation.value}]. "
        "Type EFGH commands, or GET/SET without the prefix."
    )
    print("Examples: GET APS ALL   |   GET HWS ALL   |   SET APS VOL=2   |   HELP   |   quit")
    while True:
        try:
            line = await asyncio.to_thread(input, "kometa> ")
        except EOFError:
            print()
            return
        text = line.strip()
        if not text:
            continue
        if text.lower() in {"q", "quit", "exit"}:
            return
        try:
            response = await client.command(text)
        except KometaError as exc:
            print(f"error: {exc}")
            continue
        _print_response(response)


if __name__ == "__main__":
    sys.exit(main())
