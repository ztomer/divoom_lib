# Divoom Protocol Summary

This document provides a high-level overview of the Divoom communication protocol. The information is based on community-driven reverse-engineering efforts and may not be complete or accurate for all devices.

## Communication

Divoom devices primarily use Bluetooth for communication. Two main protocols have been observed:

1.  **Classic Bluetooth (SPP/RFCOMM):** Older devices might use the Serial Port Profile (SPP) for communication. This protocol involves a simple packet structure with a start byte, length, payload, checksum, and end byte.

2.  **Bluetooth Low Energy (BLE):** Newer devices use BLE for communication. They expose specific services and characteristics for sending commands and receiving notifications. This library implements two different BLE protocols that have been observed in the wild:
    *   **Basic Protocol:** A simple protocol that is very similar to the classic SPP/RFCOMM protocol.
    *   **iOS LE Protocol:** A more complex protocol that seems to be used by the official Divoom iOS app.
    *   **Mixed Protocol Behavior:** Many newer BLE firmware revisions require writes in iOS LE Protocol format, but respond in Basic Protocol format.

## Packet Structure

The packet structure varies between the classic and BLE protocols.

### Basic Protocol (and SPP/RFCOMM)

-   **Start of Packet (1 byte):** `0x01`
-   **Length (2 bytes):** Little-endian, representing the length of the payload + checksum.
-   **Payload (variable):** The command and its data.
-   **Checksum (2 bytes):** Little-endian, calculated as the sum of the length, and payload bytes.
-   **End of Packet (1 byte):** `0x02`

Data within the payload that matches `0x01`, `0x02`, or `0x03` must be escaped.

### iOS LE Protocol

-   **Header (4 bytes):** `0xFE, 0xEF, 0xAA, 0x55`
-   **Length (2 bytes):** Little-endian, representing the length of the rest of the packet (command + packet number + payload + checksum).
-   **Command (1 byte):** The command to be executed.
-   **Packet Number (4 bytes):** A number that seems to increment with each packet.
-   **Payload (variable):** The data associated with the command.
-   **Checksum (2 bytes):** Little-endian, calculated as the sum of the length, command, packet number, and payload bytes.

### Mixed Protocol Behavior & Agnostic Notification Handling

In many physical Divoom devices (e.g., Timoo, Pixoo, Ditoo, and Tivoo Max running newer firmware versions), the device accepts command writes in the **iOS LE Protocol** framing (`feefaa55...`) but transmits notifications and query response packets (like ACKs `0x33` or data responses `0x46`) back to the client formatted in the **Basic Protocol** framing (`01...02`).

To support this mixed-protocol behavior and prevent query timeouts:
- The library implements **Protocol-Agnostic Response Parsing** inside `DivoomConnection._notification_handler()`.
- Incoming notifications are dynamically inspected: if they match the `feefaa55` `IOS_LE_HEADER`, they are handled as iOS LE packets. Otherwise, they are routed to the Basic Protocol frame parser.
- This allows the library to successfully write iOS-LE commands and read back Basic-formatted responses seamlessly.

### LAN HTTP Protocol (Wi-Fi)

For Wi-Fi capable devices (e.g., Pixoo 64, Pixoo Max, Timebox Evo with Wi-Fi firmware), the communication shifts from BLE/SPP to a local HTTP API.

- **Protocol**: HTTP/1.1 POST
- **Endpoint**: `http://<device-ip>:9000/divoom_api`
- **Request Format**: JSON payload containing:
  - `Command` (string): The command name to execute (e.g. `"Channel/SetBrightness"`).
  - `LocalToken` (int): A pairing security token (defaults to `0` if not set/enforced).
  - Additional parameters specific to the command (e.g. `{"Brightness": 80}`).
- **Response Format**: JSON payload with return fields or an `error_code` (e.g., `{"error_code": 0}`).

Unlike BLE, this protocol is stateless, doesn't require packet escaping or checksum headers, and supports faster data transfers for high-resolution coordinates/frames (64x64 or higher).

## Multi-Transport Layer Routing

The library segments all commands and queries into one of four transports (defined in [`divoom_lib/transport.py`](../divoom_lib/transport.py)):

1.  **🔵 BLE (Bluetooth Low Energy)**: 100% local. Used for commands written directly to the device via GATT characteristics.
2.  **🟢 LAN (Local Wi-Fi)**: 100% local. Talks directly to the device's HTTP server (`:9000/divoom_api`).
3.  **🟡 Divoom Cloud**: Remote. Interacts with `appin.divoom-gz.com` for community gallery browsing, store items, and remote configurations. Requires a Divoom account.
4.  **🔴 External**: Remote. Pulls from third-party services (e.g., Yahoo Finance stock ticker, iTunes album art lookup, OpenWeatherMap) to fetch metadata or render local frames.

## Commands

Divoom devices support a wide range of commands to control their features. These commands are identified by a 1-byte command code. Some common command categories include:

-   **System Settings:** Setting brightness, time, temperature, etc.
-   **Display Control:** Showing images, animations, and text.
-   **Channel Switching:** Changing the active display mode (e.g., clock, VJ effects, scoreboard).
-   **Light Mode Control (0x45 / 0x46):**
    *   **Set Light Mode (`0x45`)**: Expects a strict 10-byte payload (excluding the command header itself):
        `[0x01 (Light Mode), R, G, B, Brightness (0-100), Effect Mode (0x00), On/Off Switch (0x01), 0x00, 0x00, 0x00]`
        If the payload is shorter (e.g. 7 or 8 bytes), the device's internal parser will ignore the packet and the color change will not apply. The device returns a single-byte ACK payload `0x01` on success.
    *   **Get Light Mode (`0x46`)**: Expects no payload arguments. The device responds with command ID `0x46` and a detailed 15-byte status payload containing the current mode, light effect mode, RGB colors, brightness, temperature units, and time formats.
-   **Music and Audio:** Controlling music playback and volume.
-   **Tools:** Using tools like the stopwatch or noise meter.

A comprehensive list of command codes can be found in the [`divoom_lib/models.py`](../divoom_lib/models.py) file.

### Virtual Serial Port (SPP) Connection Stabilization
When communicating with the device's virtual serial port (e.g. `/dev/cu.Timoo-audio-4` on macOS) via `pyserial`:
1.  **Stabilization Delay**: Immediately after opening the serial port, a **2.0-second stabilization delay** (`time.sleep(2.0)`) must be introduced before sending any commands. Otherwise, initial packets are dropped by the link layer.
2.  **macOS Daemon Recovery**: If the virtual serial port stops responding (connection succeeds but reads/writes time out), the macOS DriverKit daemon `bluetoothd` has hung. The recovery sequence is:
    ```bash
    sudo pkill bluetoothd
    sleep 3  # Allow daemon to respawn and device to auto-reconnect
    ```

### BLE iOS-LE vs. Forced Classic SPP (macOS)
1. **The SPP Override Trap**: The library originally auto-routed all classic Divoom devices (names containing `timoo`, `tivoo`, `ditoo`, etc.) to use Classic Bluetooth serial mode (`_use_spp = True`) by default.
2. **Tahoe Emulation Driver Issues**: On macOS, DriverKit serial emulation `/dev/cu.*` is highly unstable, drops writes on sudden disconnects, and fails to retrieve query responses.
3. **The Solution**: We updated `divoom_lib/connection.py` to respect explicit BLE configurations. If `use_ios_le_protocol` is explicitly requested by the client (such as in the GUI or daemons), the library does not override the connection with Classic SPP transport. It connects over BLE using the highly reliable iOS-LE protocol, which works perfectly for visual debugging and two-way verification on all physical devices.

## Image and Animation Data

-   **Images:** Static images are typically sent as a raw bitmap with a color palette. The pixel data is compressed and encoded in a specific format.
-   **Animations:** Animations are sent as a series of frames. Each frame is individually encoded and sent to the device. For large animations, the data is often chunked to fit within the MTU (Maximum Transmission Unit) of the Bluetooth connection.

## Further Reading

For more detailed information about the Divoom protocol, you can refer to the following resources:

-   The source code of this library (`divoom_lib`).
-   Other open-source Divoom libraries and projects.
-   Community forums and discussions where the protocol has been reverse-engineered.
