## Project Context: Divoom Control Library

This project is focused on developing a Python library, `divoom-control`, for interacting with Divoom devices over Bluetooth Low Energy (BLE). The library aims to provide a high-level API for controlling various device features, including the display, channels, system settings, and more.

### Divoom Library API Summary

The library is structured into several modules, each responsible for a specific set of functionalities.

**`divoom_lib.Divoom`**

This is the main class for interacting with a Divoom device. It takes the device's MAC address as an argument and provides access to all the device's features through its attributes.

**`divoom_lib.protocol.DivoomProtocol`**

This class handles the low-level communication with the Divoom device. It implements two different BLE protocols: a "basic" protocol and an "iOS LE" protocol.

**`divoom_lib.utils.discovery`**

This module provides functions for discovering Divoom devices on the network.

### Divoom Protocol Summary

Divoom devices use two main protocols for communication:

1.  **Basic Protocol (and SPP/RFCOMM):** A simple protocol with a start byte, length, payload, checksum, and end byte.
2.  **iOS LE Protocol:** A more complex protocol with a header, length, command, packet number, payload, and checksum.

A comprehensive list of command codes can be found in the `divoom_lib/models.py` file.

### Recent Progress: Library Refactoring

The project has recently undergone a significant refactoring to improve its structure and usability. The key changes include:

*   **`divoom_lib` Package:** The core logic has been organized into a `divoom_lib` package with modules for different functionalities (e.g., `display`, `light`, `system`).
*   **`Divoom` Class:** A central `Divoom` class in `divoom_lib/divoom.py` provides a simplified interface for interacting with Divoom devices.
*   **Improved Examples:** The example scripts have been updated to use the new library structure.
*   **Documentation:** The documentation has been updated to reflect the new library structure and API.

This refactoring provides a solid foundation for further development and makes it easier to add new features and support for more Divoom devices.

### Core Coding Standards & Guidelines

To maintain clean architecture, peak performance, and high readability for both human developers and AI assistants, the codebase enforces the following:

1.  **Strict File Length Limit**: No source file (Python, JS, CSS) in the library may exceed **500 Lines of Code (LOC)**. Any file growing larger must be split into decoupled helper sub-packages or pure modules.
2.  **Linus Torvalds Performance Principles**:
    *   Enforce `bytearray` or `bytes` instead of list representation for protocol data.
    *   Avoid string hex formatting (`.hex()`) in loop notification logs unless lazy or debug-guarded.
    *   Offload synchronous disk operations in async loops to thread executors via `asyncio.to_thread`.
3.  **Uncle Bob SOLID Principles**:
    *   Apply Dependency Inversion: Sub-modules must depend on the abstract `CommandSender` Protocol interface, not the concrete `Divoom` class.
    *   Utilize creational factories (`Divoom.from_mac`, `Divoom.from_config`) instead of overloaded constructors.
    *   Use custom domain exceptions (e.g. `DeviceConnectionError`) instead of generic strings.

### Future Developer Experience (DevEx) Recommendations
*   **Declarative Schema Registry**: Transition to a central JSON/Python schema repository mapping command IDs to byte packing models, enabling new features to be added instantly.
*   **BLE Mock Socket Simulator**: Expand the test suites to run fully offline at CPU speeds using a loopback simulation server that returns mock responses.
*   **God Object Partitioning**: Decouple sub-modules entirely by moving communication interfaces to dedicated lightweight proxy objects.

