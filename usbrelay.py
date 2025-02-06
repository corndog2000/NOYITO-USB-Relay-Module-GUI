import serial
import time
from typing import Optional

class USBRelay:
    # Command definitions for all 4 relays
    COMMANDS = {
        1: {"on": bytes([0xA0, 0x01, 0x01, 0xA2]), "off": bytes([0xA0, 0x01, 0x00, 0xA1])},
        2: {"on": bytes([0xA0, 0x02, 0x01, 0xA3]), "off": bytes([0xA0, 0x02, 0x00, 0xA2])},
        3: {"on": bytes([0xA0, 0x03, 0x01, 0xA4]), "off": bytes([0xA0, 0x03, 0x00, 0xA3])},
        4: {"on": bytes([0xA0, 0x04, 0x01, 0xA5]), "off": bytes([0xA0, 0x04, 0x00, 0xA4])}
    }

    def __init__(self, port: str):
        """Initialize the USB Relay.
        
        Args:
            port (str): Serial port (e.g., 'COM5' on Windows or '/dev/ttyUSB0' on Linux)
        """
        self.port = port
        self.serial = None

    def connect(self) -> None:
        """Connect to the relay module."""
        try:
            self.serial = serial.Serial(self.port, baudrate=9600, timeout=1)
            time.sleep(2)  # Wait for connection to establish
        except Exception as e:
            raise ConnectionError(f"Failed to connect to {self.port}: {str(e)}")

    def disconnect(self) -> None:
        """Disconnect from the relay module."""
        if self.serial and self.serial.is_open:
            self.serial.close()

    def send_command(self, command: bytes) -> None:
        """Send a command to the relay.
        
        Args:
            command (bytes): Command bytes to send
        """
        if not self.serial or not self.serial.is_open:
            raise ConnectionError("Not connected to relay module")
        self.serial.write(command)
        time.sleep(0.1)  # Small delay after each command

    def relay_on(self, relay_num: int) -> None:
        """Turn on a specific relay.
        
        Args:
            relay_num (int): Relay number (1-4)
        """
        if relay_num not in self.COMMANDS:
            raise ValueError("Relay number must be between 1 and 4")
        self.send_command(self.COMMANDS[relay_num]["on"])

    def relay_off(self, relay_num: int) -> None:
        """Turn off a specific relay.
        
        Args:
            relay_num (int): Relay number (1-4)
        """
        if relay_num not in self.COMMANDS:
            raise ValueError("Relay number must be between 1 and 4")
        self.send_command(self.COMMANDS[relay_num]["off"])

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Context manager exit."""
        self.disconnect()


# Example usage:
if __name__ == "__main__":
    # Example 1: Basic usage
    relay = USBRelay("COM5")  # Replace with your port
    try:
        relay.connect()
        
        # Turn on relay 1
        relay.relay_on(1)
        time.sleep(1)
        
        # Turn off relay 1
        relay.relay_off(1)
        
    finally:
        relay.disconnect()

    # Example 2: Using context manager
    with USBRelay("COM5") as relay:  # Replace with your port
        # Turn on all relays
        for i in range(1, 5):
            relay.relay_on(i)
            time.sleep(0.5)
        
        time.sleep(1)
        
        # Turn off all relays
        for i in range(1, 5):
            relay.relay_off(i)
            time.sleep(0.5)
