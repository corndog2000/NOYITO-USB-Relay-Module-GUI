import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from usbrelay import USBRelay
import time

with USBRelay("COM5") as relay:  # Use your actual port
    # Turn on relays in sequence
    for i in range(1, 5):
        relay.relay_on(i)
        time.sleep(0.5)
    
    time.sleep(1)
    
    # Turn off relays in sequence
    for i in range(1, 5):
        relay.relay_off(i)
        time.sleep(0.5)