# Divoom Protocol Summary

This document provides a high-level overview of the Divoom communication protocol. The information is based on community-driven reverse-engineering efforts and may not be complete or accurate for all devices.

## Communication

Divoom devices primarily use Bluetooth for communication. Two main protocols have been observed:

1.  **Classic Bluetooth (SPP/RFCOMM):** Older devices might use the Serial Port Profile (SPP) for communication. This protocol involves a simple packet structure with a start byte, length, payload, checksum, and end byte.

2.  **Bluetooth Low Energy (BLE):** Newer devices use BLE for communication. They expose specific services and characteristics for sending commands and receiving notifications. This library implements two different BLE protocols that have been observed in the wild:
    *   **Basic Protocol:** A simple protocol that is very similar to the classic SPP/RFCOMM protocol.
    *   **iOS LE Protocol:** A more complex protocol that seems to be used by the official Divoom iOS app.

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

## Commands

Divoom devices support a wide range of commands to control their features. These commands are identified by a 1-byte command code. Some common command categories include:

-   **System Settings:** Setting brightness, time, temperature, etc.
-   **Display Control:** Showing images, animations, and text.
-   **Channel Switching:** Changing the active display mode (e.g., clock, VJ effects, scoreboard).
-   **Music and Audio:** Controlling music playback and volume.
-   **Tools:** Using tools like the stopwatch or noise meter.

A comprehensive list of command codes can be found in the [`divoom_lib/models.py`](../divoom_lib/models.py) file.

## Image and Animation Data

-   **Images:** Static images are typically sent as a raw bitmap with a color palette. The pixel data is compressed and encoded in a specific format.
-   **Animations:** Animations are sent as a series of frames. Each frame is individually encoded and sent to the device. For large animations, the data is often chunked to fit within the MTU (Maximum Transmission Unit) of the Bluetooth connection.

## Further Reading

For more detailed information about the Divoom protocol, you can refer to the following resources:

-   The source code of this library (`divoom_lib`).
-   Other open-source Divoom libraries and projects.
-   Community forums and discussions where the protocol has been reverse-engineered.
