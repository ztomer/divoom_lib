#!/usr/bin/env python3
import sys
import os
import time
import glob

# Ensure divoom_lib is on PATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from divoom_lib.framing import encode_basic_payload, parse_basic_protocol_frames

# Formatting functions per user rules
def print_info(message):
    print(f"[ ==> ] {message}")

def print_wrn(message):
    print(f"[ Wrn ] {message}")

def print_err(message):
    print(f"[ Err ] {message}")

def print_ok(message):
    print(f"[ Ok  ] {message}")

def main():
    device_name = "Timoo-audio-4"
    ports = glob.glob("/dev/cu.*")
    matched_ports = [p for p in ports if device_name.lower().replace("-", "") in p.lower().replace("-", "")]
    
    if not matched_ports:
        print_err(f"No serial ports matching '{device_name}' found.")
        return
        
    port = matched_ports[0]
    print_info(f"Connecting to virtual serial port {port}...")
    
    try:
        import serial
    except ImportError:
        print_err("pyserial is not installed.")
        return
        
    try:
        with serial.Serial(port, 115200, timeout=2.0) as ser:
            print_ok(f"Connected to {port} successfully!")
            
            # Wait for connection to stabilize (very important on macOS serial)
            print_info("Stabilizing serial connection for 2.0 seconds...")
            time.sleep(2.0)
            
            def send_color(color_hex: str):
                r = int(color_hex[0:2], 16)
                g = int(color_hex[2:4], 16)
                b = int(color_hex[4:6], 16)
                # Divoom Env/Light channel command 0x45 expects a 10-byte payload structure:
                # [0x01 (Light Mode), R, G, B, Brightness, Effect Mode, On/Off Switch, 0x00, 0x00, 0x00]
                payload = [0x45, 0x01, r, g, b, 100, 0x00, 0x01, 0x00, 0x00, 0x00]
                frame = encode_basic_payload(payload)
                print_info(f"Sending Color Change to {color_hex} (#RGB): {frame.hex()}")
                ser.write(frame)
                ser.flush()
                
                # Check for ACK
                time.sleep(0.1)
                if ser.in_waiting:
                    resp = ser.read(ser.in_waiting)
                    print_ok(f"Received ACK/Response: {resp.hex()}")
                else:
                    print_wrn("No immediate ACK/Response received.")

            # Step 1: Change to GREEN
            print_info("Step 1: Setting color to GREEN (#00FF00)...")
            send_color("00FF00")
            print_info("Waiting 4 seconds to observe color...")
            time.sleep(4.0)

            # Step 2: Change to RED
            print_info("Step 2: Setting color to RED (#FF0000)...")
            send_color("FF0000")
            print_info("Waiting 4 seconds to observe color...")
            time.sleep(4.0)

            # Step 3: Change to BLUE
            print_info("Step 3: Setting color to BLUE (#0000FF)...")
            send_color("0000FF")
            print_info("Waiting 4 seconds to observe color...")
            time.sleep(4.0)

            print_ok("Multi-color serial test complete!")

    except Exception as e:
        print_err(f"Serial communication failed: {e}")

if __name__ == "__main__":
    main()
