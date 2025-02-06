import tkinter as tk
from tkinter import ttk, messagebox
import serial.tools.list_ports
import serial
import time
import sys
import platform
import re

class RelayControlGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("4-Channel USB Relay Control")
        self.root.geometry("500x450")  # Increased width for longer port names
        self.root.resizable(False, False)
        
        self.relay = None
        self.connected = False
        self.os_type = platform.system()
        
        # Create and set up the main frame
        self.main_frame = ttk.Frame(root, padding="10")
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Platform info
        ttk.Label(self.main_frame, text=f"Platform: {self.os_type}").grid(
            row=0, column=0, columnspan=3, pady=5
        )
        
        # Port selection
        ttk.Label(self.main_frame, text="Serial Port:").grid(row=1, column=0, padx=5, pady=5)
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(self.main_frame, textvariable=self.port_var, width=30)
        self.port_combo.grid(row=1, column=1, padx=5, pady=5)
        
        # Refresh ports button
        ttk.Button(self.main_frame, text="Refresh Ports", command=self.refresh_ports).grid(
            row=1, column=2, padx=5, pady=5
        )
        
        # Connect/Disconnect button
        self.connect_button = ttk.Button(
            self.main_frame, text="Connect", command=self.toggle_connection
        )
        self.connect_button.grid(row=2, column=0, columnspan=3, pady=20)
        
        # Status label
        self.status_var = tk.StringVar(value="Status: Disconnected")
        ttk.Label(self.main_frame, textvariable=self.status_var).grid(
            row=3, column=0, columnspan=3, pady=10
        )
        
        # Frame for relay controls
        self.relay_frame = ttk.LabelFrame(self.main_frame, text="Relay Controls", padding="10")
        self.relay_frame.grid(row=4, column=0, columnspan=3, pady=10, sticky=(tk.W, tk.E))
        
        # Create controls for all 4 relays
        for i in range(4):
            ttk.Label(self.relay_frame, text=f"Relay {i+1}:").grid(row=i, column=0, padx=5, pady=5)
            ttk.Button(self.relay_frame, text="ON", 
                      command=lambda x=i+1: self.relay_on(x)).grid(
                row=i, column=1, padx=5, pady=5
            )
            ttk.Button(self.relay_frame, text="OFF", 
                      command=lambda x=i+1: self.relay_off(x)).grid(
                row=i, column=2, padx=5, pady=5
            )
        
        # Add help information based on platform
        help_text = self.get_platform_help()
        self.help_label = ttk.Label(self.main_frame, text=help_text, wraplength=450, justify="left")
        self.help_label.grid(row=5, column=0, columnspan=3, pady=10)
        
        # Initial port refresh
        self.refresh_ports()
        
        # Set up closing behavior
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def get_platform_help(self):
        """Return platform-specific help text"""
        if self.os_type == "Windows":
            return ("Note: Ensure CH340 drivers are installed. "
                   "The device should appear as 'USB-SERIAL CH340' in Device Manager.")
        elif self.os_type == "Linux":
            return ("Note: Linux usually has built-in CH340 support. "
                   "The device should appear as '/dev/ttyUSBx'. "
                   "You may need to add your user to the 'dialout' group: "
                   "'sudo usermod -a -G dialout $USER' and then log out and back in.")
        else:  # Darwin (macOS) or other
            return ("Note: You may need to install CH340 drivers for your system. "
                   "Check the manufacturer's website for details.")

    def find_ch340_ports(self):
        """Find all potential CH340 serial ports"""
        ports = []
        for port in serial.tools.list_ports.comports():
            # Look for CH340 identifiers
            if "CH340" in port.description or "USB Serial" in port.description:
                ports.append(port)
            # On Linux, also check by USB VID:PID (CH340 common ID)
            elif self.os_type == "Linux" and hasattr(port, 'pid'):
                if port.vid == 0x1A86 and port.pid == 0x7523:  # Common CH340 identifiers
                    ports.append(port)
        return ports

    def refresh_ports(self):
        """Refresh the list of available COM ports"""
        ch340_ports = self.find_ch340_ports()
        all_ports = list(serial.tools.list_ports.comports())
        
        # Create list of port descriptions
        port_list = []
        
        # Add CH340 ports first
        for port in ch340_ports:
            port_list.append(f"{port.device} - {port.description} [CH340]")
            
        # Add other ports
        for port in all_ports:
            if port not in ch340_ports:
                port_list.append(f"{port.device} - {port.description}")
        
        self.port_combo['values'] = port_list
        
        if port_list:
            self.port_combo.set(port_list[0])
        else:
            message = "No serial ports found. "
            if self.os_type == "Linux":
                message += "Try running 'dmesg' after plugging in the device."
            messagebox.showinfo("Port Scan Result", message)

    def get_selected_port(self):
        """Extract the actual port name from the combo box selection"""
        port_str = self.port_var.get()
        # Extract the port name (everything before the first space)
        match = re.match(r"([^\s]+)", port_str)
        if match:
            return match.group(1)
        return ""

    def toggle_connection(self):
        """Handle connection/disconnection to the relay module"""
        if not self.connected:
            try:
                port = self.get_selected_port()
                self.relay = serial.Serial(port, baudrate=9600, timeout=1)
                time.sleep(2)  # Wait for connection to establish
                self.connected = True
                self.connect_button.configure(text="Disconnect")
                self.status_var.set(f"Status: Connected to {port}")
                self.port_combo.configure(state="disabled")
            except serial.SerialPermissionError:
                if self.os_type == "Linux":
                    messagebox.showerror("Permission Error", 
                        "Permission denied. Try adding your user to the 'dialout' group:\n"
                        "sudo usermod -a -G dialout $USER\n"
                        "Then log out and log back in.")
                else:
                    messagebox.showerror("Permission Error", 
                        "Permission denied when opening the port.")
            except Exception as e:
                messagebox.showerror("Connection Error", f"Failed to connect: {str(e)}")
        else:
            try:
                if self.relay:
                    self.relay.close()
                self.connected = False
                self.connect_button.configure(text="Connect")
                self.status_var.set("Status: Disconnected")
                self.port_combo.configure(state="normal")
            except Exception as e:
                messagebox.showerror("Disconnection Error", f"Error during disconnection: {str(e)}")

    def send_command(self, command):
        """Send a command to the relay module"""
        if not self.connected:
            messagebox.showwarning("Not Connected", "Please connect to a relay module first.")
            return
        try:
            self.relay.write(command)
            # Add a small delay after each command
            time.sleep(0.1)
        except Exception as e:
            messagebox.showerror("Command Error", f"Failed to send command: {str(e)}")

    # Command definitions based on the protocol
    RELAY_COMMANDS = {
        1: {"on": bytes([0xA0, 0x01, 0x01, 0xA2]), "off": bytes([0xA0, 0x01, 0x00, 0xA1])},
        2: {"on": bytes([0xA0, 0x02, 0x01, 0xA3]), "off": bytes([0xA0, 0x02, 0x00, 0xA2])},
        3: {"on": bytes([0xA0, 0x03, 0x01, 0xA4]), "off": bytes([0xA0, 0x03, 0x00, 0xA3])},
        4: {"on": bytes([0xA0, 0x04, 0x01, 0xA5]), "off": bytes([0xA0, 0x04, 0x00, 0xA4])}
    }

    def relay_on(self, relay_num):
        """Turn on specified relay"""
        if 1 <= relay_num <= 4:
            self.send_command(self.RELAY_COMMANDS[relay_num]["on"])

    def relay_off(self, relay_num):
        """Turn off specified relay"""
        if 1 <= relay_num <= 4:
            self.send_command(self.RELAY_COMMANDS[relay_num]["off"])

    def on_closing(self):
        """Handle application shutdown"""
        if self.connected:
            try:
                self.relay.close()
            except:
                pass
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = RelayControlGUI(root)
    root.mainloop()