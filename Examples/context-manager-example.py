import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from usbrelay import USBRelay
import time

# Using with statement for automatic connection handling
with USBRelay("COM5") as relay:  # Use your actual port
    # Control multiple relays
    relay.relay_on(1)   # Turn on relay 1
    relay.relay_on(2)   # Turn on relay 2
    time.sleep(1)
    relay.relay_off(1)  # Turn off relay 1
    relay.relay_off(2)  # Turn off relay 2