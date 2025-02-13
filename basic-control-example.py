from usbrelay import USBRelay
import time

# Create relay object and connect
relay = USBRelay("COM5")  # Use your actual port
relay.connect()

try:
    # Turn on relay 1
    relay.relay_on(1)
    time.sleep(1)
    
    # Turn off relay 1
    relay.relay_off(1)
finally:
    relay.disconnect()