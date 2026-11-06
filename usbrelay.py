"""
Serial (CH340) USB Relay Controller
====================================
Driver for CH340-based serial USB relay boards (1, 2, 4, or 8 channels).

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
    """Controller for a CH340-based serial relay board (up to 8 channels).

    Protocol (4 bytes per command):
        Byte 0: 0xA0 (header)
        Byte 1: relay number (0x01–0x08)
        Byte 2: action (0x01 = ON, 0x00 = OFF)
        Byte 3: checksum (sum of bytes 0-2)

    8-channel boards: control uses the same per-channel commands extended
    to 0x08 (a bulk address 0x0F exists on some "PRO" clones but is not
    universal, so it is not used). Sending 0xFF alone queries relay state
    (boards that support it reply one byte per channel: 01 = open/ON,
    00 = closed/OFF).

    Usage::

        relay = USBRelay("/dev/ttyUSB0")
        relay.connect()
        relay.relay_on(1)
        relay.relay_off(1)
        relay.disconnect()

        relay8 = USBRelay("/dev/ttyUSB0", num_relays=8)
    """

    DEFAULT_NUM_RELAYS = 4
    MAX_NUM_RELAYS = 8

    # Pre-computed command lookup
    COMMANDS = {
        ch: {
            "on": bytes([0xA0, ch, 0x01, (0xA0 + ch + 0x01) & 0xFF]),
            "off": bytes([0xA0, ch, 0x00, (0xA0 + ch + 0x00) & 0xFF]),
        }
        for ch in range(1, MAX_NUM_RELAYS + 1)
    }

    def __init__(self, port: str, num_relays: int = DEFAULT_NUM_RELAYS):
        """
        Args:
            port: Serial port path, e.g. 'COM5' or '/dev/ttyUSB0'.
            num_relays: Number of channels on the board (1–8).

        Raises:
            ValueError: if num_relays is out of range.
        """
        if not 1 <= num_relays <= self.MAX_NUM_RELAYS:
            raise ValueError(
                f"num_relays must be 1–{self.MAX_NUM_RELAYS}, got {num_relays}"
            )
        self.port = port
        self.num_relays = num_relays
        self.serial: Optional[serial.Serial] = None
        self._state: int = 0  # Software-tracked bitmask
        self._hw_status_supported: Optional[bool] = None  # None = not probed

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
        """Turn on all relays (per-channel loop).

        Note: some 8-channel "PRO" clones accept a bulk command
        (A0 0F 01 B0), but it is NOT supported universally — the
        per-channel commands are documented for channels 1-8 on all
        boards, so always loop.
        """
        for ch in range(1, self.num_relays + 1):
            self.relay_on(ch)

    def all_off(self) -> None:
        """Turn off all relays (per-channel loop; see all_on note)."""
        for ch in range(1, self.num_relays + 1):
            self.relay_off(ch)

    def get_hw_status(self, timeout: float = 0.3) -> Optional[int]:
        """Query the board for its actual relay states (0xFF query).

        Boards that support querying reply one byte per channel
        (01 = open/ON, 00 = closed/OFF).

        Returns:
            Relay state bitmask, or None if the board did not answer.
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to relay module")
        old_timeout = self.serial.timeout
        try:
            self.serial.timeout = timeout
            self.serial.reset_input_buffer()
            self.serial.write(b"\xFF")
            time.sleep(0.05)
            resp = self.serial.read(self.num_relays)
        except serial.SerialException:
            return None
        finally:
            try:
                self.serial.timeout = old_timeout
            except Exception:
                pass
        if len(resp) < self.num_relays or any(b not in (0x00, 0x01) for b in resp):
            return None
        mask = 0
        for i, b in enumerate(resp):
            if b == 0x01:
                mask |= 1 << i
        return mask

    def get_status(self) -> int:
        """Return the relay state bitmask.

        Uses the 0xFF hardware query if the board answers it (probed once);
        otherwise falls back to software-tracked state reflecting commands
        sent since connecting.
        """
        if self._hw_status_supported is not False:
            hw = self.get_hw_status()
            if hw is not None:
                self._hw_status_supported = True
                self._state = hw
            else:
                self._hw_status_supported = False
        return self._state

    def get_relay_state(self, relay_num: int) -> bool:
        """Check software-tracked state of a single relay."""
        self._validate_channel(relay_num)
        return bool(self._state & (1 << (relay_num - 1)))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _validate_channel(self, relay_num: int) -> None:
        if relay_num < 1 or relay_num > self.num_relays:
            raise ValueError(
                f"Relay number must be 1–{self.num_relays}, got {relay_num}"
            )

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
