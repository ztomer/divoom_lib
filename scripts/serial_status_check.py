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

def parse_box_mode_response(payload: bytes):
    """
    Parses the response payload of command 0x46 (GET_BOX_MODE).
    Based on the APK's s.java decoding logic.
    """
    if len(payload) < 15:
        print_wrn(f"Payload too short to parse: {payload.hex()}")
        return None
        
    mode = payload[0]
    temp_type = payload[1]
    light_mode = payload[2]
    r = payload[3]
    g = payload[4]
    b = payload[5]
    brightness = payload[6]
    
    print_ok("--- Device Status ---")
    print(f"  - Mode: {mode} (0=Env, 1=Light, 2=Divoom, 3=Special, 4=Music/EQ, 5=User, 6=Score)")
    print(f"  - Light Mode: {light_mode} (0=Plain Color, 1=Love, 2=Plants, 3=NoMosquitto, 4=Sleeping)")
    print(f"  - RGB Color: #{r:02x}{g:02x}{b:02x} (R:{r}, G:{g}, B:{b})")
    print(f"  - Brightness: {brightness}%")
    return {"mode": mode, "r": r, "g": g, "b": b, "brightness": brightness}

def main():
    device_name = "Timoo-audio-4"
    ports = glob.glob("/dev/cu.*")
    matched_ports = [p for p in ports if device_name.lower().replace("-", "") in p.lower().replace("-", "")]
    
    if not matched_ports:
        print_err(f"No serial ports matching '{device_name}' found. Please pair the device first.")
        return
        
    port = matched_ports[0]
    print_info(f"Connecting to virtual serial port {port}...")
    
    try:
        import serial
    except ImportError:
        print_err("pyserial is not installed. Run 'pip install pyserial' first.")
        return
        
    try:
        with serial.Serial(port, 115200, timeout=2.0) as ser:
            print_ok(f"Connected to {port} successfully!")
            
            # Wait for connection to stabilize (very important on macOS serial)
            print_info("Stabilizing serial connection for 2.0 seconds...")
            time.sleep(2.0)
            
            # Helper to send a command and wait for response
            def send_and_wait(cmd_id: int, payload_args: list) -> bytes | None:
                frame = encode_basic_payload([cmd_id] + payload_args)
                print_info(f"Sending Command {cmd_id:#x}: {frame.hex()}")
                ser.write(frame)
                ser.flush()
                
                # Read response
                buf = bytearray()
                start_time = time.time()
                while time.time() - start_time < 2.0:
                    chunk = ser.read(32)
                    if chunk:
                        buf.extend(chunk)
                        messages, remaining = parse_basic_protocol_frames(buf)
                        if messages:
                            # Return payload of first matching response
                            for msg in messages:
                                if msg["command_id"] == cmd_id:
                                    return bytes(msg["payload"])
                    time.sleep(0.05)
                return None

            # Helper to set color and query final status
            def set_color_and_query(r: int, g: int, b: int, color_name: str):
                # 10-byte payload for command 0x45: [0x01, r, g, b, brightness, type, power, 0, 0, 0]
                args = [0x01, r, g, b, 100, 0x00, 0x01, 0x00, 0x00, 0x00]
                resp = send_and_wait(0x45, args)
                if resp:
                    print_ok(f"Received ACK for setting {color_name}: {resp.hex()}")
                else:
                    print_wrn(f"No direct ACK for setting {color_name}.")
                
                # Always query status using 0x46 afterwards
                print_info(f"Querying status after setting {color_name}...")
                time.sleep(0.5) # Let device apply the state change
                status = send_and_wait(0x46, [])
                if status:
                    parse_box_mode_response(status)
                else:
                    print_err("Failed to retrieve updated device status.")

            # 1. Query initial status
            print_info("Querying initial device status (sending 0x46)...")
            initial_payload = send_and_wait(0x46, [])
            if initial_payload:
                parse_box_mode_response(initial_payload)
            else:
                print_wrn("Failed to read initial status.")

            # 2. Change color to GREEN
            print_info("Step 1: Setting color to GREEN (#00FF00)...")
            set_color_and_query(0x00, 0xFF, 0x00, "GREEN")
            print_info("Waiting 3 seconds to observe...")
            time.sleep(3.0)

            # 3. Change color to RED
            print_info("Step 2: Setting color to RED (#FF0000)...")
            set_color_and_query(0xFF, 0x00, 0x00, "RED")
            print_info("Waiting 3 seconds to observe...")
            time.sleep(3.0)

            # 4. Change color to BLUE
            print_info("Step 3: Setting color to BLUE (#0000FF)...")
            set_color_and_query(0x00, 0x00, 0xFF, "BLUE")
            print_info("Waiting 3 seconds to observe...")
            time.sleep(3.0)

            print_ok("Multi-color serial status check complete!")

    except Exception as e:
        print_err(f"Serial communication failed: {e}")

if __name__ == "__main__":
    main()
