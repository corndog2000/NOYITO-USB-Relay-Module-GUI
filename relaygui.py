"""
Unified USB Relay Control GUI
==============================
Supports two types of relay boards:

  1. **Serial (CH340)** — appears as a virtual COM port, 1/2/4/8 channels
     (channel count selected manually; the board cannot self-report it).
  2. **HID** — appears as a USB HID device (VID 16C0 : PID 05DF), 1–8 channels.

Dependencies:
    pip install pyserial hidapi
"""

import tkinter as tk
from tkinter import ttk, messagebox
import platform

# Local modules
from usbrelay import USBRelay, enumerate_serial_relays
HID_IMPORT_ERROR = ""
try:
    from hidrelay import HIDRelay, enumerate_hid_relays, HIDRelayDeviceInfo
    HID_AVAILABLE = True
except Exception as _exc:
    HID_AVAILABLE = False
    HID_IMPORT_ERROR = str(_exc)


# ======================================================================
# Constants
# ======================================================================
MAX_CHANNELS = 8


class RelayControlGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("USB Relay Control")
        self.root.geometry("620x620")
        self.root.resizable(False, False)
        self.os_type = platform.system()

        # State
        self.relay = None          # USBRelay | HIDRelay
        self.connected = False
        self.num_channels = 0
        self._poll_job = None

        # Discovered device lists (cached between refreshes)
        self._serial_ports: list[dict] = []
        self._hid_devices: list[HIDRelayDeviceInfo] = []

        self._build_ui()
        self.refresh_devices()

        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        pad = dict(padx=6, pady=4)
        self.main = ttk.Frame(self.root, padding=10)
        self.main.grid(row=0, column=0, sticky="nsew")

        # ---- Row 0: platform ----
        ttk.Label(self.main, text=f"Platform: {self.os_type}").grid(
            row=0, column=0, columnspan=3, **pad)

        # ---- Row 1: device type selector ----
        ttk.Label(self.main, text="Device Type:").grid(row=1, column=0, **pad, sticky="e")
        self.type_var = tk.StringVar(value="serial")
        type_frame = ttk.Frame(self.main)
        type_frame.grid(row=1, column=1, columnspan=2, sticky="w", **pad)
        ttk.Radiobutton(type_frame, text="Serial (CH340)", variable=self.type_var,
                        value="serial", command=self._on_type_changed).pack(side="left")
        hid_rb = ttk.Radiobutton(type_frame, text="HID", variable=self.type_var,
                                 value="hid", command=self._on_type_changed)
        hid_rb.pack(side="left", padx=(12, 0))
        if not HID_AVAILABLE:
            hid_rb.configure(state="disabled")
            hint = f"  (unavailable: {HID_IMPORT_ERROR})" if HID_IMPORT_ERROR else "  (unavailable)"
            ttk.Label(type_frame, text=hint, foreground="red").pack(side="left")

        # ---- Row 2: device selector ----
        ttk.Label(self.main, text="Device:").grid(row=2, column=0, **pad, sticky="e")
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(
            self.main, textvariable=self.device_var, width=38, state="readonly")
        self.device_combo.grid(row=2, column=1, **pad, sticky="w")
        ttk.Button(self.main, text="Refresh", command=self.refresh_devices).grid(
            row=2, column=2, **pad)

        # ---- Row 2b: serial channel count (serial boards can't self-report) ----
        ttk.Label(self.main, text="Channels:").grid(row=3, column=0, **pad, sticky="e")
        self.serial_ch_var = tk.StringVar(value="4")
        self.serial_ch_combo = ttk.Combobox(
            self.main, textvariable=self.serial_ch_var, width=6,
            values=["1", "2", "4", "8"], state="readonly")
        self.serial_ch_combo.grid(row=3, column=1, **pad, sticky="w")
        ttk.Label(self.main, text="(serial only)", foreground="gray").grid(
            row=3, column=2, **pad, sticky="w")

        # ---- Row 4: connect button ----
        self.connect_btn = ttk.Button(self.main, text="Connect",
                                      command=self._toggle_connection)
        self.connect_btn.grid(row=4, column=0, columnspan=3, pady=12)

        # ---- Row 5: status ----
        self.status_var = tk.StringVar(value="Disconnected")
        ttk.Label(self.main, textvariable=self.status_var, foreground="gray").grid(
            row=5, column=0, columnspan=3, **pad)

        # ---- Row 6: relay channel controls (built dynamically) ----
        self.relay_frame = ttk.LabelFrame(self.main, text="Relay Channels", padding=8)
        self.relay_frame.grid(row=6, column=0, columnspan=3, pady=8, sticky="ew")
        self._channel_widgets: list[dict] = []  # list of {label, on_btn, off_btn, indicator}

        # Build placeholder (max 8 rows); visibility toggled on connect
        for i in range(MAX_CHANNELS):
            row_widgets = self._make_channel_row(self.relay_frame, i)
            self._channel_widgets.append(row_widgets)
        self._set_channels_visible(0)

        # ---- Row 7: all-on / all-off ----
        bulk_frame = ttk.Frame(self.main)
        bulk_frame.grid(row=7, column=0, columnspan=3, pady=4)
        self.all_on_btn = ttk.Button(bulk_frame, text="All ON",
                                     command=self._all_on, state="disabled")
        self.all_on_btn.pack(side="left", padx=6)
        self.all_off_btn = ttk.Button(bulk_frame, text="All OFF",
                                      command=self._all_off, state="disabled")
        self.all_off_btn.pack(side="left", padx=6)
        self.refresh_status_btn = ttk.Button(
            bulk_frame, text="Refresh Status",
            command=self._poll_status, state="disabled")
        self.refresh_status_btn.pack(side="left", padx=6)

        # ---- Row 8: help text ----
        self.help_var = tk.StringVar()
        ttk.Label(self.main, textvariable=self.help_var,
                  wraplength=580, justify="left", foreground="gray").grid(
            row=8, column=0, columnspan=3, pady=(10, 0))
        self._update_help_text()

    def _make_channel_row(self, parent, index: int) -> dict:
        """Create a single relay channel row (label + ON + OFF + indicator)."""
        row = index
        lbl = ttk.Label(parent, text=f"Relay {index + 1}:")
        lbl.grid(row=row, column=0, padx=4, pady=3, sticky="e")

        on_btn = ttk.Button(parent, text="ON", width=6,
                            command=lambda ch=index + 1: self._relay_on(ch))
        on_btn.grid(row=row, column=1, padx=4, pady=3)

        off_btn = ttk.Button(parent, text="OFF", width=6,
                             command=lambda ch=index + 1: self._relay_off(ch))
        off_btn.grid(row=row, column=2, padx=4, pady=3)

        # Status indicator (canvas circle)
        # ttk widgets don't expose "background" via cget; pull from the style
        try:
            bg = ttk.Style().lookup("TLabelframe", "background") or "SystemButtonFace"
        except Exception:
            bg = "SystemButtonFace"
        canvas = tk.Canvas(parent, width=18, height=18,
                           highlightthickness=0, bg=bg)
        canvas.grid(row=row, column=3, padx=6, pady=3)
        dot = canvas.create_oval(3, 3, 15, 15, fill="gray", outline="darkgray")

        return {"label": lbl, "on": on_btn, "off": off_btn,
                "canvas": canvas, "dot": dot}

    def _set_channels_visible(self, n: int):
        """Show the first *n* channel rows, hide the rest."""
        for i, w in enumerate(self._channel_widgets):
            state = "normal" if i < n and self.connected else "disabled"
            for key in ("label", "on", "off", "canvas"):
                widget = w[key]
                if i < n:
                    widget.grid()
                    if key in ("on", "off"):
                        widget.configure(state=state)
                else:
                    widget.grid_remove()

    # ------------------------------------------------------------------
    # Device discovery
    # ------------------------------------------------------------------

    def refresh_devices(self):
        """Repopulate the device combo based on current type selection."""
        dev_type = self.type_var.get()
        entries: list[str] = []

        if dev_type == "serial":
            self._serial_ports = enumerate_serial_relays()
            for p in self._serial_ports:
                tag = " [CH340]" if p["is_ch340"] else ""
                entries.append(f"{p['device']} — {p['description']}{tag}")
        elif dev_type == "hid" and HID_AVAILABLE:
            self._hid_devices = enumerate_hid_relays()
            for d in self._hid_devices:
                ch_str = f"{d.num_relays}ch" if d.num_relays else "?ch"
                label = d.serial_number or f"{d.vid:04X}:{d.pid:04X}"
                entries.append(
                    f"{label} — {d.product_string or 'Unknown'} ({ch_str})")

        self.device_combo["values"] = entries
        if entries:
            self.device_combo.current(0)
            self.status_var.set(f"Found {len(entries)} device(s)")
        else:
            self.device_var.set("")
            kind = "serial ports" if dev_type == "serial" else "HID relay devices"
            self.status_var.set(f"No {kind} found")

    def _on_type_changed(self):
        """Handle switching between Serial / HID radio buttons."""
        if self.connected:
            self._disconnect()
        self.refresh_devices()
        self._update_help_text()
        # Channel-count selector is only meaningful for serial boards
        self.serial_ch_combo.configure(
            state="readonly" if self.type_var.get() == "serial" else "disabled")

    def _update_help_text(self):
        dev_type = self.type_var.get()
        if dev_type == "serial":
            if self.os_type == "Windows":
                self.help_var.set(
                    "Serial mode: Ensure CH340 drivers are installed. "
                    "Device appears as 'USB-SERIAL CH340' in Device Manager.")
            elif self.os_type == "Linux":
                self.help_var.set(
                    "Serial mode: Linux usually has built-in CH340 support "
                    "(shows as /dev/ttyUSBx). You may need to add your user to "
                    "the 'dialout' group: sudo usermod -aG dialout $USER")
            else:
                self.help_var.set(
                    "Serial mode: CH340 drivers may be needed — check the "
                    "manufacturer's website.")
        else:
            if self.os_type == "Linux":
                self.help_var.set(
                    "HID mode: If the device isn't found, add a udev rule:\n"
                    "  echo 'SUBSYSTEM==\"usb\", ATTR{idVendor}==\"16c0\", "
                    "ATTR{idProduct}==\"05df\", MODE=\"0666\"' | "
                    "sudo tee /etc/udev/rules.d/99-usbrelay.rules\n"
                    "then: sudo udevadm control --reload-rules && "
                    "sudo udevadm trigger")
            elif self.os_type == "Windows":
                self.help_var.set(
                    "HID mode: No extra drivers needed on Windows. "
                    "The 'hidapi' Python package must be installed: pip install hidapi")
            else:
                self.help_var.set(
                    "HID mode: Install the 'hidapi' package: pip install hidapi")

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _toggle_connection(self):
        if self.connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        dev_type = self.type_var.get()
        idx = self.device_combo.current()
        if idx < 0:
            messagebox.showwarning("No Device", "Select a device first.")
            return

        try:
            if dev_type == "serial":
                port_info = self._serial_ports[idx]
                num_relays = int(self.serial_ch_var.get())
                relay = USBRelay(port_info["device"], num_relays=num_relays)
                relay.connect()
                self.relay = relay
                self.num_channels = relay.num_relays
                label = port_info["device"]
            else:
                dev_info = self._hid_devices[idx]
                relay = HIDRelay(path=dev_info.path,
                                 vid=dev_info.vid,
                                 pid=dev_info.pid,
                                 num_relays=dev_info.num_relays)
                relay.connect()
                self.relay = relay
                self.num_channels = relay.num_relays
                label = dev_info.serial_number or f"{dev_info.vid:04X}:{dev_info.pid:04X}"
        except Exception as exc:
            messagebox.showerror("Connection Error", str(exc))
            return

        self.connected = True
        self.connect_btn.configure(text="Disconnect")
        self.device_combo.configure(state="disabled")
        self.serial_ch_combo.configure(state="disabled")
        self.status_var.set(f"Connected: {label}  ({self.num_channels} channels)")
        self.all_on_btn.configure(state="normal")
        self.all_off_btn.configure(state="normal")
        self.refresh_status_btn.configure(state="normal")
        self._set_channels_visible(self.num_channels)

        # Start polling relay status (meaningful for HID; software-tracked for serial)
        self._poll_status()

    def _disconnect(self):
        self._cancel_poll()
        if self.relay:
            try:
                self.relay.disconnect()
            except Exception:
                pass
        self.relay = None
        self.connected = False
        self.num_channels = 0
        self.connect_btn.configure(text="Connect")
        self.device_combo.configure(state="readonly")
        self.serial_ch_combo.configure(
            state="readonly" if self.type_var.get() == "serial" else "disabled")
        self.status_var.set("Disconnected")
        self.all_on_btn.configure(state="disabled")
        self.all_off_btn.configure(state="disabled")
        self.refresh_status_btn.configure(state="disabled")
        self._set_channels_visible(0)
        self._reset_indicators()

    # ------------------------------------------------------------------
    # Relay control callbacks
    # ------------------------------------------------------------------

    def _relay_on(self, ch: int):
        if not self.connected:
            return
        try:
            self.relay.relay_on(ch)
            self._update_indicator(ch, True)
        except Exception as exc:
            messagebox.showerror("Command Error", str(exc))

    def _relay_off(self, ch: int):
        if not self.connected:
            return
        try:
            self.relay.relay_off(ch)
            self._update_indicator(ch, False)
        except Exception as exc:
            messagebox.showerror("Command Error", str(exc))

    def _all_on(self):
        if not self.connected:
            return
        try:
            self.relay.all_on()
            for ch in range(1, self.num_channels + 1):
                self._update_indicator(ch, True)
        except Exception as exc:
            messagebox.showerror("Command Error", str(exc))

    def _all_off(self):
        if not self.connected:
            return
        try:
            self.relay.all_off()
            for ch in range(1, self.num_channels + 1):
                self._update_indicator(ch, False)
        except Exception as exc:
            messagebox.showerror("Command Error", str(exc))

    # ------------------------------------------------------------------
    # Status indicators
    # ------------------------------------------------------------------

    def _update_indicator(self, ch: int, on: bool):
        """Set the dot color for a relay channel."""
        w = self._channel_widgets[ch - 1]
        color = "#22c55e" if on else "gray"      # green / gray
        outline = "#16a34a" if on else "darkgray"
        w["canvas"].itemconfig(w["dot"], fill=color, outline=outline)

    def _reset_indicators(self):
        for w in self._channel_widgets:
            w["canvas"].itemconfig(w["dot"], fill="gray", outline="darkgray")

    def _poll_status(self):
        """Periodically read relay status and update indicators.

        Uses hardware readback where supported (HID feature report;
        serial 0xFF query), otherwise software-tracked state.
        """
        if not self.connected or self.relay is None:
            return
        try:
            status = self.relay.get_status()
            for ch in range(1, self.num_channels + 1):
                on = bool(status & (1 << (ch - 1)))
                self._update_indicator(ch, on)
        except Exception:
            pass  # Board may not support readback
        # Schedule next poll
        if self.connected:
            self._poll_job = self.root.after(2000, self._poll_status)

    def _cancel_poll(self):
        if self._poll_job is not None:
            self.root.after_cancel(self._poll_job)
            self._poll_job = None

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def _on_closing(self):
        if self.connected:
            self._disconnect()
        self.root.destroy()


# ======================================================================
# Entry point
# ======================================================================
def main():
    root = tk.Tk()

    # Catch unhandled exceptions in tkinter callbacks so the app doesn't
    # silently crash from button presses or after() timers.
    def _tk_exception_handler(exc_type, exc_value, exc_tb):
        import traceback
        msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        print(msg, file=__import__("sys").stderr)
        try:
            messagebox.showerror("Unexpected Error", str(exc_value))
        except Exception:
            pass

    root.report_callback_exception = _tk_exception_handler

    app = RelayControlGUI(root)

    # Anaconda's tkinter on Windows can raise spurious KeyboardInterrupt
    # from mainloop even without Ctrl+C.  Retry until the window is actually
    # destroyed (root.winfo_exists() returns False or raises TclError).
    while True:
        try:
            root.mainloop()
            break  # Normal exit (window closed)
        except KeyboardInterrupt:
            # Check if the window still exists; if so, keep running
            try:
                if not root.winfo_exists():
                    break
            except Exception:
                break  # Window gone, exit cleanly


if __name__ == "__main__":
    main()
