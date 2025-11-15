# Divoom Lib

This Python library provides a high-level API to interact with Divoom devices over Bluetooth Low Energy (BLE). It allows you to control various aspects of your Divoom device, such as displaying images and animations, changing channels, setting the brightness, and more.

## Features

* **Device Discovery:** Discover Divoom devices on your network.
* **Display Control:**
  * Show images and animations.
  * Display text with different fonts and colors.
  * Clear the display.
* **Channel Control:**
  * Switch between different channels (Clock, Cloud, VJ Effect, etc.).
  * Get the current channel.
* **System Control:**
  * Set brightness.
  * Get device time.
  * Set device time.
* **Extensible:** The library is designed to be extensible with new commands and features.

## Requirements

* Python 3.7+
* `bleak` library

## Installation

```bash
pip install bleak
```

## Smoke Test

To perform a basic connectivity test with a Divoom device (specifically, Timoo), run the following command from the project root:

```bash
python3 -m tests.api_test
```

This test attempts to discover a Divoom device, connect to it, send a blue light command, and then disconnect.

Example output:

```
INFO:divoom_lib.utils.discovery:Scanning for Bluetooth devices searching for name containing 'Timoo'...
INFO:divoom_lib.utils.discovery:Found device: Timoo-light-4 (F90D2CC9-420E-65F9-9E06-F9554470FCED) — using this device.
INFO:api_test:Connected to Divoom device at F90D2CC9-420E-65F9-9E06-F9554470FCED
INFO:api_test:Enabled notifications for 49535343-aca3-481c-91ec-d85e28a60318
INFO:api_test:Enabled notifications for 49535343-1e4d-4bd9-ba61-23c647249616
INFO:api_test:Successfully connected to F90D2CC9-420E-65F9-9E06-F9554470FCED!
INFO:api_test:Sending blue light command...
INFO:api_test:Command sent successfully.
INFO:api_test:Disconnected from Divoom device at F90D2CC9-420E-65F9-9E06-F9554470FCED
INFO:api_test:Disconnected from Divoom device.
```

## Usage

The `examples` directory contains several scripts that demonstrate how to use the library. Here's a simple example of how to connect to a device and show an image:

```python
import asyncio
from divoom_lib import Divoom
from divoom_lib.utils.discovery import discover_divoom_devices

async def main():
    # Discover devices
    devices = await discover_divoom_devices()
    if not devices:
        print("No Divoom devices found.")
        return

    # Connect to the first device found
    device_address = devices[0].address
    divoom = Divoom(device_address)
    await divoom.connect()

    # Show an image
    await divoom.show_image("/path/to/your/image.png")

    # Disconnect
    await divoom.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
```

To run the examples, navigate to the `examples` directory and run the desired script:

```bash
python examples/discover_devices.py
```

## Library Structure

The library is organized into the following modules:

* `divoom_lib/`: The main library code.
  * `__init__.py`: Exports the main `Divoom` class.
  * `divoom_protocol.py`: The core `Divoom` class for device communication.
  * `constants.py`: Divoom protocol constants.
  * `alarm.py`: Alarm related commands.
  * `base.py`: Base class for all Divoom commands.
  * `display.py`: Display related commands.
  * `game.py`: Game related commands.
  * `light.py`: Light related commands.
  * `music.py`: Music related commands.
  * `sleep.py`: Sleep related commands.
  * `system.py`: System related commands.
  * `timeplan.py`: Time plan related commands.
  * `tool.py`: Tool related commands.
  * `channels/`: Modules for different channels.
  * `commands/`: Modules for different commands.
  * `drawing/`: Modules for drawing and text rendering.
  * `utils/`: Utility functions for discovery, image processing, etc.
* `examples/`: Example scripts.
* `docs/`: Documentation files.

## Contributing

Contributions are welcome! If you want to contribute to the project, please follow these steps:

1. Fork the repository.
2. Create a new branch for your feature or bug fix.
3. Make your changes and commit them.
4. Push your changes to your fork.
5. Create a pull request.

## Disclaimer

This project is unofficial and not affiliated with Divoom Technology Co., Ltd. Use at your own risk.
