# NOYITO-USB-Relay-Module-GUI
# relaygui.py
Windows/Linux control software for manual control of the 2-channel and 4-channel NOYITO USB relay modules.

Manufacturer documentation for 2-channel module: [NOYITO  5V 2-Channel Micro USB Relay Module User Manual.pdf](https://github.com/corndog2000/NOYITO-USB-Relay-Module-GUI/blob/main/NOYITO%20%205V%202-Channel%20Micro%20USB%20Relay%20Module%20User%20Manual.pdf)

**If you are using a 2-channel relay module then you can safely ignore the Relay 3 and Relay 4 buttons.**

![This image shows a graphical user interface for a "4-Channel USB Relay Control" application. The window contains a serial port selection dropdown showing "COM5 - USB-SERIAL CH340 (COM" selected, a "Refresh Ports" button, and a "Connect" button. Below these is a status indicator showing "Status: Disconnected". The main section labeled "Relay Controls" has four rows of controls, one for each relay (1-4), with "ON" and "OFF" buttons for each. At the bottom is a note about ensuring CH340 drivers are installed. The interface appears to be running on Windows.](https://github.com/corndog2000/NOYITO-USB-Relay-Module-GUI/blob/main/interface.png)

Relay modules this software is for use with:
- [https://www.amazon.com/NOYITO-2-Channel-Module-Control-Intelligent/dp/B081RM7PMY](https://www.amazon.com/NOYITO-2-Channel-Module-Control-Intelligent/dp/B081RM7PMY)
- [https://www.amazon.com/NOYITO-4-Channel-Computer-Drive-free-Controller/dp/B08CS9MMD6](https://www.amazon.com/NOYITO-4-Channel-Computer-Drive-free-Controller/dp/B08CS9MMD6)
- [https://www.amazon.com/NOYITO-4-Channel-Module-Control-Intelligent/dp/B09RGVQXXT](https://www.amazon.com/NOYITO-4-Channel-Module-Control-Intelligent/dp/B09RGVQXXT)


# usbrelay.py
Control the relay modules in Python without a GUI.

Example 1 - Basic Control:
```python
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
```

Example 2 - Using context manager (automatically handles connect/disconnect):
```python
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
```

Example 3 - Sequence pattern:
```python
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
```
