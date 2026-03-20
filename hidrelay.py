"""
HID USB Relay Controller
========================
Cross-platform driver for HID-based USB relay boards (LCUS, SainSmart, etc.)
using the ``hid`` Python module.

These boards use USB HID (not serial) and are identified by:
  VID: 0x16C0  PID: 0x05DF

Supports 1, 2, 4, and 8 channel boards.

Dependencies (install ONE of these — both provide ``import hid``):
    pip install hidapi        # recommended, bundles the native library
    pip install hid           # alternative, may need hidapi DLL separately

Linux users may need a udev rule for non-root access:
    echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="16c0", ATTR{idProduct}=="05df", MODE="0666"' | \\
        sudo tee /etc/udev/rules.d/99-usbrelay.rules
    sudo udevadm control --reload-rules && sudo udevadm trigger
"""

try:
    import hid
except ImportError:
    raise ImportError(
        "HID support requires the 'hid' Python module. Install with:\n"
        "    pip install hidapi\n"
        "or: pip install hid"
    )

# ---------------------------------------------------------------------------
# Compatibility shim: the 'hid' and 'hidapi' pip packages both provide
# `import hid` but expose different APIs.
#   hidapi (cython-hidapi): hid.Device(...), hid.HIDException
#   hid:                    hid.device(), dev.open_path(), dev.open()
# We normalise to a common wrapper so the rest of the module doesn't care.
# ---------------------------------------------------------------------------
_USE_CYTHON_HIDAPI = hasattr(hid, "Device")  # True for cython-hidapi


class _HIDDeviceWrapper:
    """Thin wrapper that presents the same interface regardless of backend."""

    def __init__(self):
        if _USE_CYTHON_HIDAPI:
            self._dev = None  # Will be a hid.Device
        else:
            self._dev = hid.device()

    # -- open ---------------------------------------------------------------
    def open_path(self, path: bytes):
        if _USE_CYTHON_HIDAPI:
            self._dev = hid.Device(path=path)
        else:
            self._dev.open_path(path)

    def open(self, vid: int, pid: int, serial: str = None):
        if _USE_CYTHON_HIDAPI:
            self._dev = hid.Device(vid=vid, pid=pid, serial=serial)
        else:
            self._dev.open(vid, pid, serial)

    # -- feature reports ----------------------------------------------------
    def send_feature_report(self, data: bytes):
        if _USE_CYTHON_HIDAPI:
            self._dev.send_feature_report(data)
        else:
            self._dev.send_feature_report(data)

    def get_feature_report(self, report_id: int, length: int) -> bytes:
        if _USE_CYTHON_HIDAPI:
            return self._dev.get_feature_report(report_id, length)
        else:
            return bytes(self._dev.get_feature_report(report_id, length))

    # -- info ---------------------------------------------------------------
    @property
    def product(self) -> str:
        if _USE_CYTHON_HIDAPI:
            return self._dev.product
        else:
            return self._dev.get_product_string() or ""

    # -- close --------------------------------------------------------------
    def close(self):
        if self._dev is not None:
            self._dev.close()
            if _USE_CYTHON_HIDAPI:
                self._dev = None
from dataclasses import dataclass
from typing import Optional


# Known USB identifiers for HID relay boards
KNOWN_HID_RELAY_IDS = [
    (0x16C0, 0x05DF),  # LCUS / SainSmart / generic "USBRelay"
    (0x0519, 0x2018),  # Some Chinese relay boards
    (0x5131, 0x2007),  # Another common variant
]

# Keywords to detect relay boards by product/manufacturer string
RELAY_KEYWORDS = ["relay", "usbrelay"]

# HID feature report commands
CMD_RELAY_ON = 0xFF
CMD_RELAY_OFF = 0xFD
CMD_ALL_ON = 0xFE
CMD_ALL_OFF = 0xFC

# Feature report size (report ID + 8 data bytes)
REPORT_SIZE = 9
STATUS_REPORT_ID = 0x01
STATUS_BYTE_INDEX = 7  # Relay state bitmask is in byte 7 of the status report


@dataclass
class HIDRelayDeviceInfo:
    """Information about a discovered HID relay device."""
    serial_number: str
    path: bytes
    product_string: str
    manufacturer_string: str
    num_relays: int  # Inferred from product string or default
    vid: int = 0
    pid: int = 0

    def __str__(self):
        return (f"HID Relay [{self.serial_number or self.path}] "
                f"({self.num_relays}ch) - {self.product_string}")


def _is_relay_device(dev_dict: dict) -> bool:
    """Check if a HID device dict looks like a relay board."""
    vid = dev_dict.get("vendor_id", 0)
    pid = dev_dict.get("product_id", 0)
    # Check known VID:PID pairs
    if (vid, pid) in KNOWN_HID_RELAY_IDS:
        return True
    # Check product/manufacturer strings for relay keywords
    product = (dev_dict.get("product_string", "") or "").lower()
    manufacturer = (dev_dict.get("manufacturer_string", "") or "").lower()
    return any(kw in product or kw in manufacturer for kw in RELAY_KEYWORDS)


def enumerate_hid_relays() -> list[HIDRelayDeviceInfo]:
    """Discover all connected HID relay devices.

    Scans by known VID:PID pairs first, then does a broad keyword scan
    across all HID devices to catch boards with unusual identifiers.

    Returns:
        List of HIDRelayDeviceInfo for each discovered device.
    """
    devices = []
    seen_paths = set()

    for dev_dict in hid.enumerate():
        if not _is_relay_device(dev_dict):
            continue

        path = dev_dict.get("path", b"")
        if not path or path in seen_paths:
            continue
        seen_paths.add(path)

        serial = dev_dict.get("serial_number", "") or ""
        product = dev_dict.get("product_string", "") or ""
        manufacturer = dev_dict.get("manufacturer_string", "") or ""

        # Deduplicate by serial when available (boards can have multiple
        # HID interfaces that show up as separate entries)
        if serial:
            if any(d.serial_number == serial for d in devices):
                continue

        num_relays = _parse_channel_count(product)

        devices.append(HIDRelayDeviceInfo(
            serial_number=serial,
            path=path,
            product_string=product,
            manufacturer_string=manufacturer,
            num_relays=num_relays,
            vid=dev_dict.get("vendor_id", 0),
            pid=dev_dict.get("product_id", 0),
        ))

    return devices


def _parse_channel_count(product_string: str) -> int:
    """Try to extract channel count from the product string.

    Common patterns: 'USBRelay2', 'USBRelay4', 'USBRelay8'.
    Defaults to 0 (unknown) if it can't be determined.
    """
    import re
    m = re.search(r"(\d+)\s*$", product_string)
    if m:
        count = int(m.group(1))
        if count in (1, 2, 4, 8):
            return count
    return 0


class HIDRelay:
    """Controller for a single HID USB relay board.

    Usage::

        # By device path (most reliable, used by the GUI)
        relay = HIDRelay(path=b"\\\\\\\\?\\\\HID#VID...")
        relay.connect()
        relay.relay_on(1)
        relay.relay_off(1)
        relay.disconnect()

        # By serial number (when VID:PID is known)
        relay = HIDRelay(serial_number="ABCDE", vid=0x16C0, pid=0x05DF)

        # Using context manager
        with HIDRelay(path=dev_info.path) as r:
            r.relay_on(1)
    """

    def __init__(
        self,
        serial_number: Optional[str] = None,
        path: Optional[bytes] = None,
        vid: int = 0,
        pid: int = 0,
        num_relays: int = 0,
    ):
        """
        Args:
            serial_number: Serial string of the target board.
            path: Raw HID device path (preferred — always works).
            vid: USB Vendor ID (needed for serial_number-based open).
            pid: USB Product ID (needed for serial_number-based open).
            num_relays: Number of relay channels (0 = auto-detect on connect).
        """
        if serial_number is None and path is None:
            raise ValueError("Provide either serial_number or path")
        self._serial_number = serial_number
        self._path = path
        self._vid = vid
        self._pid = pid
        self._device: Optional[_HIDDeviceWrapper] = None
        self.num_relays = num_relays
        self._state: int = 0  # Software-tracked bitmask

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open the HID device."""
        if self._device is not None:
            return  # Already connected

        dev = _HIDDeviceWrapper()
        try:
            if self._path:
                dev.open_path(self._path)
            elif self._serial_number and self._vid and self._pid:
                dev.open(self._vid, self._pid, self._serial_number)
            else:
                raise ConnectionError(
                    "Need either a device path, or serial + VID/PID to connect")
        except ConnectionError:
            raise
        except Exception as exc:
            raise ConnectionError(f"Failed to open HID relay: {exc}") from exc

        self._device = dev

        # Auto-detect channel count if not provided
        if self.num_relays == 0:
            product = self._device.product
            self.num_relays = _parse_channel_count(product) or 8  # Assume 8 if unknown

        # Try to sync software state from hardware
        try:
            report = self._device.get_feature_report(STATUS_REPORT_ID, REPORT_SIZE)
            # Status byte position varies by library; try common offsets
            for idx in (STATUS_BYTE_INDEX, STATUS_BYTE_INDEX - 1):
                if 0 <= idx < len(report):
                    val = report[idx]
                    # Sanity: value should fit within num_relays bits
                    if val < (1 << self.num_relays):
                        self._state = val
                        break
        except Exception:
            self._state = 0  # Assume all off

    def disconnect(self) -> None:
        """Close the HID device."""
        if self._device is not None:
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None

    @property
    def is_connected(self) -> bool:
        return self._device is not None

    # ------------------------------------------------------------------
    # Relay operations
    # ------------------------------------------------------------------

    def _send_feature(self, cmd: int, index: int = 0) -> None:
        """Send a 9-byte feature report to the relay board."""
        if self._device is None:
            raise ConnectionError("Not connected to HID relay")
        report = bytes([0x00, cmd, index, 0, 0, 0, 0, 0, 0])
        self._device.send_feature_report(report)

    def relay_on(self, relay_num: int) -> None:
        """Energize (close) a relay channel.

        Args:
            relay_num: Channel number, 1-based.
        """
        self._validate_channel(relay_num)
        self._send_feature(CMD_RELAY_ON, relay_num)
        self._state |= (1 << (relay_num - 1))

    def relay_off(self, relay_num: int) -> None:
        """De-energize (open) a relay channel.

        Args:
            relay_num: Channel number, 1-based.
        """
        self._validate_channel(relay_num)
        self._send_feature(CMD_RELAY_OFF, relay_num)
        self._state &= ~(1 << (relay_num - 1))

    def all_on(self) -> None:
        """Energize all relay channels."""
        self._send_feature(CMD_ALL_ON)
        self._state = (1 << self.num_relays) - 1

    def all_off(self) -> None:
        """De-energize all relay channels."""
        self._send_feature(CMD_ALL_OFF)
        self._state = 0

    def get_status(self) -> int:
        """Return the relay state bitmask (software-tracked).

        Returns:
            Integer bitmask — bit 0 = relay 1, bit 1 = relay 2, etc.
            A set bit means the relay is energized.
        """
        return self._state

    def get_hw_status(self) -> int:
        """Read the relay state bitmask directly from hardware.

        Returns:
            Integer bitmask from the HID feature report.
            May not work reliably with all HID library variants.
        """
        if self._device is None:
            raise ConnectionError("Not connected to HID relay")
        report = self._device.get_feature_report(STATUS_REPORT_ID, REPORT_SIZE)
        return report[STATUS_BYTE_INDEX]

    def get_relay_state(self, relay_num: int) -> bool:
        """Check whether a single relay channel is energized.

        Args:
            relay_num: Channel number, 1-based.

        Returns:
            True if the relay is ON (energized).
        """
        self._validate_channel(relay_num)
        status = self.get_status()
        return bool(status & (1 << (relay_num - 1)))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _validate_channel(self, relay_num: int) -> None:
        if relay_num < 1 or (self.num_relays and relay_num > self.num_relays):
            raise ValueError(
                f"Relay number must be 1–{self.num_relays or '?'}, got {relay_num}"
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
        ident = self._serial_number or self._path
        return f"HIDRelay({ident!r}, relays={self.num_relays})"


# ======================================================================
# Quick demo
# ======================================================================
if __name__ == "__main__":
    import time

    print("Scanning for HID relay boards...")
    found = enumerate_hid_relays()
    if not found:
        print("No HID relay devices found.")
        raise SystemExit(1)

    for info in found:
        print(f"  {info}")

    # Use the first device found (connect by path — always works)
    with HIDRelay(path=found[0].path) as relay:
        print(f"\nConnected to {relay!r}")
        print(f"Status bitmask: {relay.get_status():08b}")

        # Toggle relay 1
        relay.relay_on(1)
        time.sleep(1)
        print(f"After ON:  {relay.get_status():08b}")

        relay.relay_off(1)
        time.sleep(0.2)
        print(f"After OFF: {relay.get_status():08b}")
