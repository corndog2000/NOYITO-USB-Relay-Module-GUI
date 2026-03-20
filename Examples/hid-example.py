import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hidrelay import HIDRelay, enumerate_hid_relays
import time

# Discover connected HID relay boards
devices = enumerate_hid_relays()
if not devices:
    print("No HID relay devices found.")
    sys.exit(1)

for dev in devices:
    print(f"Found: {dev}")

# Connect to the first device found
with HIDRelay(path=devices[0].path) as relay:
    print(f"Connected: {relay!r}")

    # Turn on relays in sequence
    for i in range(1, relay.num_relays + 1):
        relay.relay_on(i)
        print(f"Relay {i} ON")
        time.sleep(0.5)

    time.sleep(1)

    # Turn off relays in sequence
    for i in range(1, relay.num_relays + 1):
        relay.relay_off(i)
        print(f"Relay {i} OFF")
        time.sleep(0.5)
