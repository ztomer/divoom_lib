# Divoom Protocol Summary

This document provides a high-level overview of the Divoom communication protocol. The information is based on community-driven reverse-engineering efforts and may not be complete or accurate for all devices.

## Communication

Divoom devices primarily use Bluetooth for communication. Two main protocols have been observed:

1.  **Classic Bluetooth (SPP/RFCOMM):** Older devices might use the Serial Port Profile (SPP) for communication. This protocol involves a simple packet structure with a start byte, length, payload, checksum, and end byte.

2.  **Bluetooth Low Energy (BLE):** Newer devices use BLE for communication. They expose specific services and characteristics for sending commands and receiving notifications.

## Packet Structure

The packet structure varies between the classic and BLE protocols.

### Classic Bluetooth (SPP/RFCOMM)

-   **Start of Packet:** `0x01`
-   **Length:** 2 bytes, little-endian, representing the payload length.
-   **Payload:** The command and its data.
-   **Checksum:** 2 bytes, little-endian, calculated over the payload.
-   **End of Packet:** `0x02`

Data within the payload that matches the start or end bytes must be escaped.

### Bluetooth Low Energy (BLE)

The BLE packet structure is more complex and can vary between device models and firmware versions. A common structure includes:

-   **Header:** A fixed sequence of bytes.
-   **Length:** 2 bytes, little-endian, representing the length of the remaining packet.
-   **Command:** 1 byte, identifying the command to be executed.
-   **Payload:** The data associated with the command.
-   **Checksum:** 2 bytes, little-endian, calculated over a portion of the packet.

## Commands

Divoom devices support a wide range of commands to control their features. These commands are identified by a 1-byte command code. Some common command categories include:

-   **System Settings:** Setting brightness, time, temperature, etc.
-   **Display Control:** Showing images, animations, and text.
-   **Channel Switching:** Changing the active display mode (e.g., clock, VJ effects, scoreboard).
-   **Music and Audio:** Controlling music playback and volume.
-   **Tools:** Using tools like the stopwatch or noise meter.

The specific command codes and their payload structures can be found by examining the source code of various open-source Divoom libraries or by analyzing the communication with the official Divoom app.

## Image and Animation Data

-   **Images:** Static images are typically sent as a raw bitmap with a color palette. The pixel data is compressed and encoded in a specific format.
-   **Animations:** Animations are sent as a series of frames. Each frame is individually encoded and sent to the device. For large animations, the data is often chunked to fit within the MTU (Maximum Transmission Unit) of the Bluetooth connection.

## Further Reading

For more detailed information about the Divoom protocol, you can refer to the following resources:

-   The source code of this library (`divoom_lib`).
-   Other open-source Divoom libraries and projects.
-   Community forums and discussions where the protocol has been reverse-engineered.
