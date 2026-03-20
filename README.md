# USB Relay Control Suite

Cross-platform GUI and Python library for controlling USB relay modules — both **Serial (CH340)** and **HID** types.

## Supported Hardware

### Serial (CH340) Relay Modules
These appear as a virtual COM port and use a 4-byte binary protocol at 9600 baud.

- [NOYITO 2-Channel USB Relay Module](https://www.amazon.com/NOYITO-2-Channel-Module-Control-Intelligent/dp/B081RM7PMY)
- [NOYITO 4-Channel USB Relay Module](https://www.amazon.com/NOYITO-4-Channel-Computer-Drive-free-Controller/dp/B08CS9MMD6)
- [NOYITO 4-Channel USB Relay Module (alt)](https://www.amazon.com/NOYITO-4-Channel-Module-Control-Intelligent/dp/B09RGVQXXT)

Manufacturer documentation: [NOYITO 5V 2-Channel Micro USB Relay Module User Manual.pdf](https://github.com/corndog2000/NOYITO-USB-Relay-Module-GUI/blob/main/NOYITO%20%205V%202-Channel%20Micro%20USB%20Relay%20Module%20User%20Manual.pdf)

**If you are using a 2-channel relay module, you can safely ignore the Relay 3 and Relay 4 buttons.**

### HID Relay Modules
These appear as USB HID devices (no COM port) and are controlled via HID feature reports. Supports 1, 2, 4, and 8 channel boards.

Common boards include those from LCUS, SainSmart, dcttech, and similar manufacturers with:
- VID: `0x16C0`, PID: `0x05DF` (most common)
- Product strings containing "USBRelay"

## Installation

### Dependencies
```bash
pip install pyserial hidapi
```

`pyserial` is required for Serial (CH340) relay modules. `hidapi` is required for HID relay modules.

**Note:** The `hidapi` and `hid` pip packages both provide `import hid` but have different APIs. This project supports both. Install **one** of them — `hidapi` is recommended as it bundles the native library on Windows.

### Linux — HID Permissions
HID devices require a udev rule for non-root access:
```bash
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="16c0", ATTR{idProduct}=="05df", MODE="0666"' | \
    sudo tee /etc/udev/rules.d/99-usbrelay.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

### Linux — Serial Permissions
You may need to add your user to the `dialout` group:
```bash
sudo usermod -aG dialout $USER
```
Then log out and back in.

## File Overview

| File | Purpose |
|------|---------|
| `relaygui.py` | Unified GUI — supports both Serial and HID relay modules |
| `usbrelay.py` | Python library for Serial (CH340) relay control |
| `hidrelay.py` | Python library for HID relay control |
| `examples/context-manager-example.py` | Serial relay example using context manager |
| `examples/sequence-example.py` | Serial relay example with sequential pattern |
| `examples/hid-example.py` | HID relay example with enumeration and control |

---

## relaygui.py — GUI Application

A tkinter GUI that supports both Serial (CH340) and HID relay modules with a radio toggle to switch between modes.

Features:
- Auto-detection of CH340 serial ports and HID relay devices
- Dynamic channel count (1–8 channels for HID, 4 for serial)
- Per-channel ON/OFF buttons with green/gray status indicators
- All ON / All OFF bulk controls
- Refresh Status button for manual state readback

```bash
python relaygui.py
```

---

## usbrelay.py — Serial (CH340) Library

Control CH340-based serial relay boards from Python without a GUI.

### Example 1 — Basic control:
```python
from usbrelay import USBRelay
import time

relay = USBRelay("COM5")  # Use your actual port
relay.connect()

try:
    relay.relay_on(1)
    time.sleep(1)
    relay.relay_off(1)
finally:
    relay.disconnect()
```

### Example 2 — Context manager (auto connect/disconnect):
```python
from usbrelay import USBRelay
import time

with USBRelay("COM5") as relay:  # Use your actual port
    relay.relay_on(1)
    relay.relay_on(2)
    time.sleep(1)
    relay.relay_off(1)
    relay.relay_off(2)
```

### Example 3 — Sequence pattern:
```python
from usbrelay import USBRelay
import time

with USBRelay("COM5") as relay:  # Use your actual port
    for i in range(1, 5):
        relay.relay_on(i)
        time.sleep(0.5)

    time.sleep(1)

    for i in range(1, 5):
        relay.relay_off(i)
        time.sleep(0.5)
```

---

## hidrelay.py — HID Relay Library

Control HID-based USB relay boards from Python without a GUI.

### Example 1 — Enumerate and connect:
```python
from hidrelay import HIDRelay, enumerate_hid_relays
import time

# Discover connected HID relay boards
devices = enumerate_hid_relays()
for dev in devices:
    print(dev)

# Connect to the first device found (by path — always works)
with HIDRelay(path=devices[0].path) as relay:
    relay.relay_on(1)
    time.sleep(1)
    relay.relay_off(1)
```

### Example 2 — Connect by serial number (if available):
```python
from hidrelay import HIDRelay

with HIDRelay(serial_number="ABCDE", vid=0x16C0, pid=0x05DF) as relay:
    relay.relay_on(1)
    relay.all_on()
    relay.all_off()
```

### Example 3 — Sequence pattern:
```python
from hidrelay import HIDRelay, enumerate_hid_relays
import time

devices = enumerate_hid_relays()
with HIDRelay(path=devices[0].path) as relay:
    for i in range(1, relay.num_relays + 1):
        relay.relay_on(i)
        time.sleep(0.5)

    time.sleep(1)

    for i in range(1, relay.num_relays + 1):
        relay.relay_off(i)
        time.sleep(0.5)
```

---

## Troubleshooting

### HID relay not detected
Run this to see all HID devices on your system:
```bash
python -c "import hid; [print(f'VID:{d[\"vendor_id\"]:04X} PID:{d[\"product_id\"]:04X} serial:{d[\"serial_number\"]} product:{d[\"product_string\"]}') for d in hid.enumerate()]"
```
If your relay board shows up with a VID:PID not listed above, open an issue with the output.

### GUI crashes with `KeyboardInterrupt`
This is a known Anaconda/tkinter issue on Windows. The GUI includes a workaround that retries `mainloop` automatically.

### `module 'hid' has no attribute 'Device'`
You have conflicting HID packages. Fix with:
```bash
pip uninstall hid hidapi
pip install hidapi
```
