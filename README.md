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
pip install bleak divoom-lib
```

## Usage

The `examples` directory contains several scripts that demonstrate how to use the library. Here are a few examples:

### Discovering Devices

To discover Divoom devices on your network, you can use the `discover_device` function from the `divoom_lib.utils.discovery` module.

```python
import asyncio
from divoom_lib.utils.discovery import discover_device

async def main():
    device, device_id = await discover_device()
    if device:
        print(f"Found device: {device.name} ({device.address})")

if __name__ == "__main__":
    asyncio.run(main())
```

### Connecting to a Device

To connect to a Divoom device, you need its MAC address. You can get the MAC address from the discovery process.

```python
import asyncio
from divoom_lib.divoom import Divoom

async def main():
    device_address = "XX:XX:XX:XX:XX:XX"  # Replace with your device's address
    divoom = Divoom(mac=device_address)
    
    try:
        await divoom.protocol.connect()
        print("Connected!")
    finally:
        if divoom.protocol.is_connected:
            await divoom.protocol.disconnect()
            print("Disconnected.")

if __name__ == "__main__":
    asyncio.run(main())
```

### Setting the Brightness

To set the brightness of the device, you can use the `set_brightness` method from the `divoom.device` object.

```python
import asyncio
from divoom_lib.divoom import Divoom

async def main():
    device_address = "XX:XX:XX:XX:XX:XX"  # Replace with your device's address
    divoom = Divoom(mac=device_address)
    
    try:
        await divoom.protocol.connect()
        await divoom.device.set_brightness(50)
    finally:
        if divoom.protocol.is_connected:
            await divoom.protocol.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
```

### Showing a Light

To show a solid color light, you can use the `show_light` method from the `divoom.light` object.

```python
import asyncio
from divoom_lib.divoom import Divoom

async def main():
    device_address = "XX:XX:XX:XX:XX:XX"  # Replace with your device's address
    divoom = Divoom(mac=device_address)
    
    try:
        await divoom.protocol.connect()
        await divoom.light.show_light(color=(255, 0, 0))
    finally:
        if divoom.protocol.is_connected:
            await divoom.protocol.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
```

## Library Structure

The library is organized into the following modules:

* `divoom_lib/`: The main library code.
  * `divoom.py`: The main `Divoom` class.
  * `protocol.py`: The `DivoomProtocol` class for low-level communication.
  * `models.py`: Divoom protocol constants and data models.
  * `display/`: Modules for controlling the display.
    * `light.py`: Light related commands.
    * `animation.py`: Animation related commands.
    * `drawing.py`: Drawing related commands.
    * `text.py`: Text related commands.
  * `media/`: Modules for controlling media playback.
    * `music.py`: Music related commands.
    * `radio.py`: Radio related commands.
  * `scheduling/`: Modules for scheduling events.
    * `alarm.py`: Alarm related commands.
    * `sleep.py`: Sleep related commands.
    * `timeplan.py`: Time plan related commands.
  * `system/`: Modules for controlling system settings.
    * `device.py`: General device settings.
    * `time.py`: Time related functions.
    * `bluetooth.py`: Bluetooth settings.
  * `tools/`: Modules for controlling tools.
    * `scoreboard.py`: Scoreboard tool.
    * `timer.py`: Timer tool.
    * `countdown.py`: Countdown tool.
    * `noise.py`: Noise tool.
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
