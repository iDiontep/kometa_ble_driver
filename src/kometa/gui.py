"""Minimal terminal-style GUI for KOMETA v2 over BLE (layout close to Terminal 1.9b)."""

from __future__ import annotations

import asyncio
import queue
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog
from typing import Any

from kometa.ble import FoundDevice, scan
from kometa.client import KometaClient
from kometa.exceptions import KometaError

BG = "#d4d0c8"
LED_OFF = "#808080"
LED_ON = "#22c022"
FONT_UI = ("Tahoma", 8)
FONT_MONO = ("Consolas", 10)
MACRO_COUNT = 24

DEFAULT_MACROS = [
    "EFGH GET APS ALL",
    "EFGH GET APS VOL",
    "EFGH SET APS VOL=2",
    "EFGH SET APS DFLT",
    "EFGH GET APD ALL",
    "EFGH GET HWS ALL",
    "EFGH GET SAS ALL",
    "EFGH GET HWD ALL",
    "EFGH GET SAD ALL",
    "EFGH FWV",
    "EFGH HELP",
    "EFGH SERVICE",
    "EFGH SHIP",
    "EFGH CHG",
    "EFGH RST",
    "EFGH FACTORY",
] + [""] * 8

assert len(DEFAULT_MACROS) == MACRO_COUNT

HELP_TEXT = (
    "KOMETA BLE Terminal\n\n"
    "Format: EFGH <CMD> [CATEGORY] [PARAMS]\n"
    "Dividers: space, comma, =\n\n"
    "Scan finds both:\n"
    "  KOMETA V1.0  — d1 through ESP32 ble-module\n"
    "  KOMETA V2.0  — d2 STM32WB onboard BLE\n\n"
    "d1: GET/SET APS HWS SAS, GET APD HWD SAD,\n"
    "    FWV HELP SERVICE SHIP RST FACTORY CHG (EEPROM on SET).\n"
    "d2: GET/SET APS (RAM only), GET APD.\n"
    "    HWS/SAS/HWD/SAD and specials are not on WB yet.\n"
)


class BleWorker:
    """Runs asyncio/bleak on a background thread; UI talks to it through a queue."""

    def __init__(self, events: queue.SimpleQueue[tuple[str, Any]]) -> None:
        self.events = events
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, name="kometa-ble", daemon=True)
        self.client: KometaClient | None = None
        self.thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coro: Any) -> None:
        asyncio.run_coroutine_threadsafe(self._guard(coro), self.loop)

    async def _guard(self, coro: Any) -> None:
        try:
            await coro
        except KometaError as exc:
            self.events.put(("error", str(exc)))
        except Exception as exc:
            self.events.put(("error", f"{type(exc).__name__}: {exc}"))
        finally:
            self.events.put(("idle", None))

    def scan(self, timeout: float) -> None:
        self.submit(self._scan(timeout))

    async def _scan(self, timeout: float) -> None:
        self.events.put(("status", "Scanning..."))
        devices = await scan(timeout=timeout)
        self.events.put(("devices", devices))
        if devices:
            self.events.put(("status", f"Found {len(devices)} device(s)"))
        else:
            self.events.put(("status", "No KOMETA devices found"))

    def connect(self, address: str | None) -> None:
        self.submit(self._connect(address))

    async def _connect(self, address: str | None) -> None:
        await self._disconnect()
        self.events.put(("status", "Connecting..."))
        client = KometaClient(address=address, raise_on_error=False)
        client.transport.set_unsolicited_handler(lambda text: self.events.put(("rx", text)))
        await client.connect()
        self.client = client
        info = {
            "address": client.address or address or "",
            "name": client.advertised_name,
            "generation": client.generation.value,
        }
        self.events.put(("connected", info))
        self.events.put(("rx", f"HGFE BLE connected {info['name'] or info['address']} ({info['generation']})\r\n"))
        self.events.put(("status", f"Connected {info['name'] or info['address']} [{info['generation']}]"))

    def disconnect(self) -> None:
        self.submit(self._disconnect())

    async def _disconnect(self) -> None:
        client = self.client
        self.client = None
        if client is not None:
            await client.disconnect()
        self.events.put(("disconnected", None))
        self.events.put(("status", "Disconnected"))

    def send(self, text: str) -> None:
        self.submit(self._send(text))

    async def _send(self, text: str) -> None:
        if self.client is None or not self.client.is_connected:
            raise KometaError("not connected")
        self.events.put(("tx", text if text.endswith("\n") else text + "\r\n"))
        response = await self.client.command(text)
        raw = response.raw if response.raw.endswith("\n") else response.raw + "\r\n"
        self.events.put(("rx", raw))

    def shutdown(self) -> None:
        if self.loop.is_running():
            fut = asyncio.run_coroutine_threadsafe(self._disconnect(), self.loop)
            try:
                fut.result(timeout=2)
            except Exception:
                pass
            self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=2)


class KometaTerminal(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("KOMETA BLE Terminal")
        self.configure(bg=BG)
        self.geometry("920x640")
        self.minsize(760, 520)

        self.events: queue.SimpleQueue[tuple[str, Any]] = queue.SimpleQueue()
        self.worker = BleWorker(self.events)
        self.macros = list(DEFAULT_MACROS)
        self.devices: list[FoundDevice] = []
        self.busy = False
        self.connected = False
        self.ascii_mode = tk.BooleanVar(value=True)
        self.cr_var = tk.BooleanVar(value=True)
        self.auto_send = tk.BooleanVar(value=True)
        self.device_var = tk.StringVar(value="")

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_quit)
        self.after(50, self._pump)
        self._set_busy(True)
        self.worker.scan(timeout=8.0)

    def _build(self) -> None:
        top = tk.Frame(self, bg=BG)
        top.pack(fill=tk.X, padx=6, pady=4)

        left = tk.Frame(top, bg=BG)
        left.pack(side=tk.LEFT, anchor=tk.N)
        self.btn_connect = tk.Button(left, text="Connect", width=10, font=FONT_UI, command=self._on_connect)
        self.btn_connect.pack(pady=1)
        self.btn_rescan = tk.Button(left, text="ReScan", width=10, font=FONT_UI, command=self._on_rescan)
        self.btn_rescan.pack(pady=1)
        tk.Button(left, text="Help", width=10, font=FONT_UI, command=self._on_help).pack(pady=1)
        tk.Button(left, text="About", width=10, font=FONT_UI, command=self._on_about).pack(pady=1)
        tk.Button(left, text="Quit", width=10, font=FONT_UI, command=self._on_quit).pack(pady=1)

        mid = tk.LabelFrame(top, text="Device", font=FONT_UI, bg=BG, padx=8, pady=6)
        mid.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        tk.Label(mid, text="KOMETA", font=FONT_UI, bg=BG).pack(anchor=tk.W)
        self.device_combo = tk.OptionMenu(mid, self.device_var, "")
        self.device_combo.config(font=FONT_UI, width=48, bg="white")
        self.device_combo.pack(fill=tk.X, pady=4)
        hint = tk.Label(
            mid,
            text="Bluetooth 5.3  |  V1.0 = d1 ble-module,  V2.0 = d2 WB",
            font=FONT_UI,
            bg=BG,
            fg="#404040",
        )
        hint.pack(anchor=tk.W)

        leds = tk.LabelFrame(top, text="Status", font=FONT_UI, bg=BG, padx=8, pady=4)
        leds.pack(side=tk.RIGHT, padx=4)
        self.led = tk.Canvas(leds, width=18, height=18, bg=BG, highlightthickness=0)
        self.led.grid(row=0, column=0, padx=4)
        self._led_item = self.led.create_oval(3, 3, 15, 15, fill=LED_OFF, outline="#404040")
        tk.Label(leds, text="CONN", font=FONT_UI, bg=BG).grid(row=0, column=1)
        self.lbl_addr = tk.Label(leds, text="---", font=FONT_UI, bg=BG, width=36, anchor=tk.W)
        self.lbl_addr.grid(row=1, column=0, columnspan=2, pady=(4, 0))

        self.receive = self._make_pane(self, "Receive", height=18, extra=self._receive_toolbar)
        self.transmit = self._make_pane(self, "Transmit", height=5, extra=self._transmit_toolbar)

        macros = tk.LabelFrame(self, text="Macros", font=FONT_UI, bg=BG, padx=4, pady=4)
        macros.pack(fill=tk.X, padx=6, pady=2)
        tk.Button(macros, text="Set Macros", font=FONT_UI, command=self._on_set_macros).pack(side=tk.LEFT, padx=4)
        grid = tk.Frame(macros, bg=BG)
        grid.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.macro_buttons: list[tk.Button] = []
        for i in range(MACRO_COUNT):
            btn = tk.Button(
                grid,
                text=f"M{i + 1}",
                width=4,
                font=FONT_UI,
                command=lambda n=i: self._on_macro(n),
            )
            btn.grid(row=i // 12, column=i % 12, padx=1, pady=1)
            self.macro_buttons.append(btn)
        self._refresh_macro_tips()

        bottom = tk.Frame(self, bg=BG)
        bottom.pack(fill=tk.X, padx=6, pady=4)
        self.cmd = tk.Entry(bottom, font=FONT_MONO, bg="white")
        self.cmd.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3)
        self.cmd.insert(0, "EFGH GET APS ALL")
        self.cmd.bind("<Return>", lambda _e: self._on_send())
        tk.Checkbutton(bottom, text="CR", variable=self.cr_var, font=FONT_UI, bg=BG).pack(side=tk.RIGHT, padx=4)
        tk.Checkbutton(bottom, text="Send", variable=self.auto_send, font=FONT_UI, bg=BG).pack(side=tk.RIGHT)
        tk.Button(bottom, text="Send", width=8, font=FONT_UI, command=self._on_send).pack(side=tk.RIGHT, padx=4)

        self.status = tk.Label(self, text="Ready", font=FONT_UI, bg=BG, anchor=tk.W, relief=tk.SUNKEN)
        self.status.pack(fill=tk.X, side=tk.BOTTOM)

    def _receive_toolbar(self, parent: tk.Frame) -> None:
        tk.Button(parent, text="CLEAR", font=FONT_UI, command=lambda: self._clear(self.receive)).pack(side=tk.LEFT)
        tk.Radiobutton(parent, text="ASCII", variable=self.ascii_mode, value=True, font=FONT_UI, bg=BG).pack(
            side=tk.LEFT, padx=8
        )
        tk.Radiobutton(parent, text="HEX", variable=self.ascii_mode, value=False, font=FONT_UI, bg=BG).pack(side=tk.LEFT)

    def _transmit_toolbar(self, parent: tk.Frame) -> None:
        tk.Button(parent, text="CLEAR", font=FONT_UI, command=lambda: self._clear(self.transmit)).pack(side=tk.LEFT)

    def _make_pane(self, parent: tk.Misc, title: str, height: int, extra) -> tk.Text:
        frame = tk.LabelFrame(parent, text=title, font=FONT_UI, bg=BG, padx=4, pady=4)
        frame.pack(fill=tk.BOTH, expand=(title == "Receive"), padx=6, pady=2)
        bar = tk.Frame(frame, bg=BG)
        bar.pack(fill=tk.X)
        extra(bar)
        wrap = tk.Frame(frame, bg=BG)
        wrap.pack(fill=tk.BOTH, expand=True)
        text = tk.Text(
            wrap,
            height=height,
            font=FONT_MONO,
            bg="white",
            relief=tk.SUNKEN,
            wrap=tk.NONE,
            undo=False,
        )
        ys = tk.Scrollbar(wrap, command=text.yview)
        xs = tk.Scrollbar(wrap, orient=tk.HORIZONTAL, command=text.xview)
        text.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        text.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_columnconfigure(0, weight=1)
        text.tag_configure("tx", foreground="#000080")
        text.tag_configure("rx", foreground="#000000")
        text.tag_configure("err", foreground="#a00000")
        return text

    def _set_devices(self, devices: list[FoundDevice]) -> None:
        self.devices = devices
        menu = self.device_combo["menu"]
        menu.delete(0, tk.END)
        labels = [_device_label(item) for item in devices]
        if not labels:
            labels = [""]
            self.device_var.set("")
        else:
            self.device_var.set(labels[0])
        for label in labels:
            menu.add_command(label=label, command=lambda v=label: self.device_var.set(v))

    def _selected_address(self) -> str | None:
        value = self.device_var.get().strip()
        if not value:
            return None
        if "  " in value:
            return value.rsplit("  ", 1)[-1].strip()
        return value

    def _on_rescan(self) -> None:
        if self.busy:
            return
        self._set_busy(True)
        self.worker.scan(timeout=8.0)

    def _on_connect(self) -> None:
        if self.busy:
            return
        if self.connected:
            self._set_busy(True)
            self.worker.disconnect()
            return
        self._set_busy(True)
        self.worker.connect(self._selected_address())

    def _on_send(self) -> None:
        text = self.cmd.get().strip()
        if not text:
            return
        if not self.connected:
            self._append(self.receive, "not connected\r\n", "err")
            return
        if self.busy:
            return
        if self.cr_var.get() and not text.endswith("\n"):
            text = text.rstrip("\r\n")
        self._set_busy(True)
        self.worker.send(text)

    def _on_macro(self, index: int) -> None:
        command = self.macros[index].strip()
        if not command:
            command = simpledialog.askstring("Macro", f"M{index + 1} is empty. Enter command:", parent=self) or ""
            self.macros[index] = command
            self._refresh_macro_tips()
            if not command:
                return
        self.cmd.delete(0, tk.END)
        self.cmd.insert(0, command)
        if self.auto_send.get():
            self._on_send()

    def _on_set_macros(self) -> None:
        win = tk.Toplevel(self)
        win.title("Set Macros")
        win.configure(bg=BG)
        win.transient(self)
        entries: list[tk.Entry] = []
        for i in range(MACRO_COUNT):
            row = tk.Frame(win, bg=BG)
            row.pack(fill=tk.X, padx=8, pady=1)
            tk.Label(row, text=f"M{i + 1:02d}", width=5, font=FONT_UI, bg=BG, anchor=tk.W).pack(side=tk.LEFT)
            entry = tk.Entry(row, font=FONT_MONO, width=48)
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            entry.insert(0, self.macros[i])
            entries.append(entry)

        def save() -> None:
            self.macros = [item.get().strip() for item in entries]
            self._refresh_macro_tips()
            win.destroy()

        bar = tk.Frame(win, bg=BG)
        bar.pack(fill=tk.X, pady=8)
        tk.Button(bar, text="OK", width=10, font=FONT_UI, command=save).pack(side=tk.RIGHT, padx=8)
        tk.Button(bar, text="Cancel", width=10, font=FONT_UI, command=win.destroy).pack(side=tk.RIGHT)

    def _refresh_macro_tips(self) -> None:
        for i, btn in enumerate(self.macro_buttons):
            tip = self.macros[i] or "(empty)"
            btn.configure(text=f"M{i + 1}")
            _tooltip(btn, tip)

    def _on_help(self) -> None:
        messagebox.showinfo("Help", HELP_TEXT, parent=self)

    def _on_about(self) -> None:
        messagebox.showinfo(
            "About",
            "KOMETA BLE Terminal\nCellerLab\n\nHost driver for KOMETA V2.0\nvia Bluetooth 5.3 adapter",
            parent=self,
        )

    def _on_quit(self) -> None:
        try:
            self.worker.shutdown()
        finally:
            self.destroy()

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        self.btn_connect.configure(state=state)
        self.btn_rescan.configure(state=state)

    def _set_connected(self, connected: bool, address: str = "", extra: dict | None = None) -> None:
        self.connected = connected
        self.led.itemconfigure(self._led_item, fill=LED_ON if connected else LED_OFF)
        self.btn_connect.configure(text="Disconnect" if connected else "Connect")
        if extra and extra.get("name"):
            label = f"{extra.get('name')}  [{extra.get('generation', '?')}]  {address}"
        else:
            label = address or "---"
        self.lbl_addr.configure(text=label)

    def _append(self, widget: tk.Text, data: str, tag: str) -> None:
        if not self.ascii_mode.get() and tag in {"tx", "rx"}:
            data = " ".join(f"{byte:02X}" for byte in data.encode("latin-1", errors="replace")) + "\n"
        widget.insert(tk.END, data.replace("\r\n", "\n").replace("\r", "\n"), tag)
        widget.see(tk.END)

    def _clear(self, widget: tk.Text) -> None:
        widget.delete("1.0", tk.END)

    def _pump(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "devices":
                    self._set_devices(payload)
                elif kind == "connected":
                    if isinstance(payload, dict):
                        self._set_connected(True, str(payload.get("address") or ""), payload)
                    else:
                        self._set_connected(True, str(payload))
                elif kind == "disconnected":
                    self._set_connected(False)
                elif kind == "tx":
                    self._append(self.transmit, str(payload), "tx")
                elif kind == "rx":
                    self._append(self.receive, str(payload), "rx")
                elif kind == "status":
                    self.status.configure(text=str(payload))
                elif kind == "error":
                    self.status.configure(text=str(payload))
                    self._append(self.receive, str(payload) + "\r\n", "err")
                elif kind == "idle":
                    self._set_busy(False)
        except queue.Empty:
            pass
        self.after(50, self._pump)


def _device_label(device: FoundDevice) -> str:
    rssi = f"  {device.rssi} dBm" if device.rssi is not None else ""
    gen = f"  [{device.generation.value}]" if device.generation.value != "unknown" else ""
    return f"{device.name}{gen}{rssi}  {device.address}"


def _tooltip(widget: tk.Widget, text: str) -> None:
    tip: list[tk.Toplevel] = []

    def show(_event: tk.Event) -> None:
        if tip:
            return
        win = tk.Toplevel(widget)
        win.wm_overrideredirect(True)
        x = widget.winfo_rootx() + 10
        y = widget.winfo_rooty() + widget.winfo_height() + 4
        win.wm_geometry(f"+{x}+{y}")
        tk.Label(win, text=text, font=FONT_UI, bg="#ffffe0", relief=tk.SOLID, borderwidth=1).pack()
        tip.append(win)

    def hide(_event: tk.Event) -> None:
        while tip:
            tip.pop().destroy()

    widget.bind("<Enter>", show)
    widget.bind("<Leave>", hide)


def run_app() -> None:
    app = KometaTerminal()
    app.mainloop()


def main() -> int:
    run_app()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
