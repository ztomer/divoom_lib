# Divoom Control Architecture

This document provides a high-level overview of the `divoom-control` library, designed to help AI agents (and humans) quickly understand the system structure and communication protocols.

## System Overview

The library is structured to provide a high-level Python API for controlling Divoom devices over Bluetooth Low Energy (BLE).

```mermaid
graph TD
    User[User Script] --> Divoom[Divoom Class (divoom.py)]
    Divoom --> Modules[Sub-modules (light, media, etc.)]
    Divoom --> Protocol[DivoomProtocol (protocol.py)]
    Protocol --> Bleak[BleakClient (BLE Library)]
    Bleak --> Device[Physical Divoom Device]
```

### Key Components

*   **`divoom_lib/divoom.py` (`Divoom`)**: The main entry point. It initializes sub-modules and manages the connection. It currently (and redundantly) implements some protocol logic that should ideally be in `protocol.py`.
*   **`divoom_lib/protocol.py` (`DivoomProtocol`)**: Handles the low-level details of BLE communication, including packet framing, checksum calculation, and payload escaping.
*   **`divoom_lib/models.py`**: Contains constants, command codes, and configuration data classes (`DivoomConfig`).
*   **`divoom_lib/display/`, `divoom_lib/system/`, etc.**: Sub-modules that group related functionality (e.g., `Light`, `Time`, `Radio`).

## Communication Protocols

Divoom devices use two distinct protocols over BLE. The library attempts to support both.

### 1. Basic Protocol (Timebox Evo / SPP-like)
Used by older devices or specific modes.
*   **Structure**: `0x01` (Start) + `Length` (2 bytes, LSB) + `Payload` + `Checksum` (2 bytes, LSB) + `0x02` (End).
*   **Payload Escaping**: Certain bytes in the payload (`0x01`, `0x02`, `0x03`) are escaped using `0x03` + `byte + 0x03`.
*   **Responses**: Often framed with `0x04 <CMD> 0x55 ...`.

### 2. iOS LE Protocol
Used by newer devices (Pixoo, Ditoo) for more reliable BLE communication.
*   **Structure**: `HEADER` (4 bytes) + `Length` (2 bytes) + `Command` (1 byte) + `Packet Num` (4 bytes) + `Payload` + `Checksum` (2 bytes).
*   **Header**: `0xfe 0xef 0xaa 0x55` (defined in `models.IOS_LE_MESSAGE_HEADER`).
*   **No Escaping**: The payload is sent raw within the frame.

## "Gotchas" for AI Agents

1.  **Redundancy**: The `Divoom` class has methods like `connect`, `disconnect`, and `send_command` that mirror those in `DivoomProtocol`. This is technical debt. The `Divoom` class should delegate these entirely to `DivoomProtocol`.
2.  **Framing Context**: The `_framing_context` manager in `Divoom` is used to temporarily switch between protocols (e.g., trying iOS LE if Basic fails).
3.  **Checksums**: The checksum algorithm is a simple sum of bytes (LSB first).
4.  **Notification Handling**: Responses are asynchronous. The `DivoomProtocol` class uses a `notification_queue` to store incoming responses, which `wait_for_response` polls.
5.  **Generic ACK**: Many commands return a generic acknowledgment (`0x33`) instead of a specific data response. The `wait_for_response` logic handles this by ignoring the ACK and waiting for the real data (if expected).

## Development Workflow

1.  **Modify Code**: Make changes in `divoom_lib/`.
2.  **Verify**: Run unit tests (`pytest`).
3.  **Mock Test**: Use `scripts/mock_device.py` (if available) to verify protocol logic without hardware.
