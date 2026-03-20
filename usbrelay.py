"""
Serial (CH340) USB Relay Controller
====================================
Driver for CH340-based serial USB relay boards (4-channel).

These boards appear as a virtual COM port and use a simple 4-byte
binary protocol at 9600 baud.

Dependencies:
    pip install pyserial
"""

import serial
import serial.tools.list_ports
import time
import platform
import re
from typing import Optional


# CH340 USB identifiers
CH340_VID = 0x1A86
CH340_PID = 0x7523


def enumerate_serial_relays() -> list[dict]:
    """Find serial ports that look like CH340 relay boards.

    Returns:
        List of dicts with keys: device, description, is_ch340.
    """
    results = []
    for port in serial.tools.list_ports.comports():
        is_ch340 = (
            "CH340" in (port.description or "")
            or "USB Serial" in (port.description or "")
            or (getattr(port, "vid", None) == CH340_VID
                and getattr(port, "pid", None) == CH340_PID)
        )
        results.append({
            "device": port.device,
            "description": port.description or "",
            "is_ch340": is_ch340,
        })
    # CH340 ports first
    results.sort(key=lambda p: (not p["is_ch340"], p["device"]))
    return results


class USBRelay:
    """Controller for a CH340-based serial relay board (up to 4 channels).

    Protocol (4 bytes per command):
        Byte 0: 0xA0 (header)
        Byte 1: relay number (0x01–0x04)
        Byte 2: action (0x01 = ON, 0x00 = OFF)
        Byte 3: checksum (sum of bytes 0-2)

    Usage::

        relay = USBRelay("/dev/ttyUSB0")
        relay.connect()
        relay.relay_on(1)
        relay.relay_off(1)
        relay.disconnect()
    """

    NUM_RELAYS = 4

    # Pre-computed command lookup
    COMMANDS = {
        ch: {
            "on": bytes([0xA0, ch, 0x01, (0xA0 + ch + 0x01) & 0xFF]),
            "off": bytes([0xA0, ch, 0x00, (0xA0 + ch + 0x00) & 0xFF]),
        }
        for ch in range(1, 5)
    }

    def __init__(self, port: str):
        """
        Args:
            port: Serial port path, e.g. 'COM5' or '/dev/ttyUSB0'.
        """
        self.port = port
        self.serial: Optional[serial.Serial] = None
        self._state: int = 0  # Software-tracked bitmask (no hw readback)

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open the serial port."""
        try:
            self.serial = serial.Serial(self.port, baudrate=9600, timeout=1)
            time.sleep(2)  # CH340 needs time after open
        except serial.SerialException as exc:
            raise ConnectionError(f"Failed to connect to {self.port}: {exc}") from exc

    def disconnect(self) -> None:
        """Close the serial port."""
        if self.serial and self.serial.is_open:
            self.serial.close()
        self.serial = None

    @property
    def is_connected(self) -> bool:
        return self.serial is not None and self.serial.is_open

    # ------------------------------------------------------------------
    # Relay operations
    # ------------------------------------------------------------------

    def _send(self, command: bytes) -> None:
        if not self.is_connected:
            raise ConnectionError("Not connected to relay module")
        self.serial.write(command)
        time.sleep(0.05)

    def relay_on(self, relay_num: int) -> None:
        """Turn on (energize) a relay channel (1-based)."""
        self._validate_channel(relay_num)
        self._send(self.COMMANDS[relay_num]["on"])
        self._state |= (1 << (relay_num - 1))

    def relay_off(self, relay_num: int) -> None:
        """Turn off (de-energize) a relay channel (1-based)."""
        self._validate_channel(relay_num)
        self._send(self.COMMANDS[relay_num]["off"])
        self._state &= ~(1 << (relay_num - 1))

    def all_on(self) -> None:
        """Turn on all relays."""
        for ch in range(1, self.NUM_RELAYS + 1):
            self.relay_on(ch)

    def all_off(self) -> None:
        """Turn off all relays."""
        for ch in range(1, self.NUM_RELAYS + 1):
            self.relay_off(ch)

    def get_status(self) -> int:
        """Return software-tracked relay state bitmask.

        Note: CH340 serial relay boards do not support hardware readback,
        so this reflects commands sent since connecting.
        """
        return self._state

    def get_relay_state(self, relay_num: int) -> bool:
        """Check software-tracked state of a single relay."""
        self._validate_channel(relay_num)
        return bool(self._state & (1 << (relay_num - 1)))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _validate_channel(self, relay_num: int) -> None:
        if relay_num < 1 or relay_num > self.NUM_RELAYS:
            raise ValueError(
                f"Relay number must be 1–{self.NUM_RELAYS}, got {relay_num}"
            )

    @property
    def num_relays(self) -> int:
        return self.NUM_RELAYS

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.disconnect()

    def __repr__(self):
        return f"USBRelay({self.port!r})"


# ======================================================================
# Demo
# ======================================================================
if __name__ == "__main__":
    print("Scanning for CH340 serial relay boards...")
    ports = enumerate_serial_relays()
    for p in ports:
        tag = " [CH340]" if p["is_ch340"] else ""
        print(f"  {p['device']} - {p['description']}{tag}")

    ch340_ports = [p for p in ports if p["is_ch340"]]
    if not ch340_ports:
        print("No CH340 ports found.")
        raise SystemExit(1)

    with USBRelay(ch340_ports[0]["device"]) as relay:
        print(f"Connected to {relay!r}")
        relay.relay_on(1)
        time.sleep(1)
        relay.relay_off(1)
        print("Done.")
