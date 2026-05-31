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

## Architectural Principles (Linus & Uncle Bob)

The system architecture is governed by strict technical guidelines established during our core codebase review:
1.  **Low-Level Data Efficiency (Linus)**: Enforce pure binary buffers (`bytearray` or `bytes`) for parsing and notification handling. Avoid list-backed queues for bytes and hex-to-byte round-trips. Keep hot-path logs lazy to prevent garbage collection churn.
2.  **Event Loop Safety (Linus)**: Disk and file-system I/O (such as cache reads/writes) must never block the asyncio loop; always run blocking operations in worker threads using `asyncio.to_thread`.
3.  **Dependency Inversion (Uncle Bob)**: Decouple high-level modules (e.g. Light, Clock, Sleep) from concrete BLE clients. All sub-modules must depend on the `CommandSender` Protocol interface, allowing standalone unit testing and connection protocol swapping.
4.  **Domain Exceptions (Uncle Bob)**: All Bluetooth, transport, and validation logic should raise domain-specific subclasses (e.g., `DeviceConnectionError`) instead of generic exception strings.

## "Gotchas" & Clarifications for AI Agents

1.  **Inheritance-based Deduplication**: Previously, `DivoomProtocol` and `Divoom` were parallel classes. They have been collapsed; `DivoomProtocol` now inherits directly from the unified `Divoom` orchestrator, with framing and escape routines moved to `divoom_lib/framing.py`.
2.  **Framing Context**: The `_framing_context` manager in `Divoom` dynamically switches between standard basic framing and iOS LE protocols to support multi-device transparent compatibility.
3.  **Notification Handling**: Responses are asynchronous. The client pushes bytes into a `notification_queue`, and requests wait via `asyncio.wait_for(queue.get(), timeout)`.
4.  **Generic ACKs**: A generic acknowledgment `0x33` is automatically parsed and ignored by `wait_for_response` when the device is preparing real data responses.

---

## Strict Architectural Standards

To maintain high maintainability, rapid semantic searches, and easy codebase updates for both human developers and AI agents, the project enforces a strict limit:
*   **No File Above 500 Lines of Code (LOC)**: No single Python, JS, or CSS source file in the library must exceed 500 lines of code.
*   **Agent/Developer Rationale**:
    *   **LLM Context Optimization**: Under 500 LOC ensures an AI assistant can read and reason about the *entire* file without truncation or loss of precision.
    *   **Strict Modularity**: A 500 LOC ceiling forces developers to apply the Single Responsibility Principle, separating framing logic, networking, and data processing.
    *   **Faster Test Runs**: Smaller files encourage discrete unit test files, improving local caching and test execution speed.

---

## 👾 Working with this Codebase: AI Agent Self-Reflections

To make working with the `divoom-control` codebase easier, faster, and more robust, future stages should prioritize the following enhancements:

### 1. Unified Declarative Command Registry
Instead of splitting byte parsing, argument packs, and command codes across `models.py` and display helper files (e.g. VJ effects and Alarm configurations), we should construct a single, **declarative schema registry** (such as JSON or typed Python dataclasses).
*   **Benefits**: Allows AI coding agents to map newly reverse-engineered APK command IDs to byte packing schemas instantly without tracing through duplicate class methods.

### 2. High-Fidelity Loopback BLE Simulation Server
Developing a comprehensive mock client simulation framework (like a loopback socket server or a local Bluetooth mock that responds with authentic Divoom response packets for time, channels, and custom visuals).
*   **Benefits**: Unit tests can run without real hardware, validating entire connection lifecycles, retries, and escaping structures in full loopback speed.

### 3. Modular Decoupling of God Objects
Refactoring the tight bi-directional references between the main `Divoom` entry object and its display sub-modules (e.g., passing a thin, abstract connection proxy delegate to `Light` instead of the whole concrete `Divoom` parent).
*   **Benefits**: Modules can be imported, tested, and upgraded in absolute isolation.

---

## Development Workflow

1.  **Modify Code**: Make changes in `divoom_lib/`.
2.  **Verify**: Run unit tests (`pytest`).
3.  **Mock Test**: Use `scripts/mock_device.py` (if available) to verify protocol logic without hardware.
