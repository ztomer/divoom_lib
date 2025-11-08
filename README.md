# Divoom Control Program

This Python program aims to provide a way to interact with Divoom devices via Bluetooth. It is designed to:

a. Connect to Divoom devices.
b. Tell the Divoom devices to reset their Bluetooth connections.
c. Tell the Divoom devices to update their hot channel top designs.

## Current Status

This project is in its early design phase. The `divoom_control.py` script contains placeholder functions for `reset_bluetooth` and `update_hot_channel_design` as the exact Bluetooth commands for these functionalities need to be reverse-engineered from the official Divoom application or existing community projects.

## Requirements

*   Python 3.x
*   `pybluez` library (installation instructions below)
*   A Bluetooth adapter on your system.

## Installation

1.  **Install `pybluez`:**

    ```bash
    pip install pybluez
    ```

    *Note: `pybluez` might have platform-specific dependencies. On Linux, you might need `libbluetooth-dev` and `bluez`. On macOS, it might require Xcode command line tools.*

## Usage

1.  **Ensure your Divoom device is discoverable and/or paired with your system.**
2.  **Run the script:**

    ```bash
    python divoom_control.py
    ```

    The script will attempt to discover nearby Bluetooth devices and identify potential Divoom devices based on their names. If found, it will attempt to connect, simulate a Bluetooth reset, and then simulate an update to the hot channel design.

## Future Work

*   **Reverse-engineer Divoom protocol:** Identify the exact byte sequences for `reset_bluetooth` and `update_hot_channel_design`.
*   **Implement Divoom-specific commands:** Add more functionalities based on the reverse-engineered protocol.
*   **Improve device discovery:** Add more robust filtering for Divoom devices.
*   **Command-line interface:** Add arguments for specifying MAC addresses, commands, etc.

## Disclaimer

This project is unofficial and not affiliated with Divoom Technology Co., Ltd. Use at your own risk. Bluetooth communication can be complex and may vary between Divoom device models.