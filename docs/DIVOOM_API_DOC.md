# Divoom Library API Reference

This document provides a reference for the `divoom_lib` Python library API. For details on the underlying Divoom protocol, please refer to [DIVOOM_PROTOCOL_SUMMARY.md](./DIVOOM_PROTOCOL_SUMMARY.md).

## Core Components

The library is structured into several modules, each responsible for a specific set of functionalities.

### `divoom_lib.Divoom`

This is the main class for interacting with a Divoom device.

**`Divoom(address, logger=None)`**

*   **`address`**: The Bluetooth address of the Divoom device.
*   **`logger`**: An optional logger instance.

**Attributes:**

*   **`display`**: An instance of `divoom_lib.display.Display` for controlling the device's screen.

**Methods:**

*   **`async connect()`**: Connects to the Divoom device.
*   **`async disconnect()`**: Disconnects from the Divoom device.
*   **`is_connected`**: Property to check if the device is connected.
*   **`async send_command(command, args)`**: Sends a command to the device.
*   **`async send_command_and_wait_for_response(command, args)`**: Sends a command and waits for a response.
*   **`async set_brightness(brightness)`**: Sets the device brightness.
*   **`async set_time(dt=None)`**: Sets the device time.
*   **`async get_time()`**: Gets the device time.
*   **`async set_channel(channel)`**: Switches to a specific channel.
*   **`async get_channel()`**: Gets the current channel.

### `divoom_lib.display.Display`

This class provides methods for controlling the device's display. It is accessed through the `display` attribute of a `Divoom` object.

**Methods:**

*   **`async show_clock(clock, twentyfour, weather, temp, calendar, color, hot)`**: Shows the clock.
*   **`async show_design(number)`**: Shows a design from the gallery.
*   **`async show_effects(number)`**: Shows a special effect.
*   **`async show_image(file, time)`**: Displays a static image or GIF animation.
*   **`async show_light(color, brightness, power)`**: Sets a solid color light.
*   **`async show_visualization(number)`**: Shows a music visualizer.

### `divoom_lib.utils.discovery`

This module provides functions for discovering Divoom devices.

**`async discover_divoom_devices(device_name="Divoom", logger=None)`**

*   **`device_name`**: The name to look for in the device's Bluetooth name (case-insensitive).
*   **`logger`**: An optional logger instance.
*   **Returns**: A list of `bleak.backends.device.BLEDevice` objects.

### `divoom_lib.channels`

This package contains modules for each display channel.

*   **`TimeChannel`**: Displays the time with various options.
*   **`LightningChannel`**: Controls lightning effects.
*   **`VJEffectChannel`**: Displays VJ effects.
*   **`ScoreboardChannel`**: Displays a scoreboard.
*   **`CloudChannel`**: Activates the cloud channel.
*   **`CustomChannel`**: Activates the custom channel.

Each channel class has options to customize its appearance and behavior.

### `divoom_lib.commands`

This package contains modules for specific device commands.

*   **`BrightnessCommand`**: Sets the device brightness.
*   **`DateTimeCommand`**: Sets the device date and time.
*   **`TempWeatherCommand`**: Sets the temperature and weather icon.

### `divoom_lib.drawing`

This package provides tools for creating and displaying custom content.

*   **`DisplayText`**: Displays text with custom fonts and colors.
*   **`DisplayAnimation`**: Processes and displays images and animations.

## Example Usage

The `examples` directory contains various scripts demonstrating the library's functionalities. To run an example, navigate to the `examples` directory and execute the script with `python3`.

For instance, to discover devices:

```bash
python3 examples/discover_devices.py
```

To control a device, you will typically need its Bluetooth address. You can modify the example scripts to use your device's address.

```python
import asyncio
from divoom_lib import Divoom

async def main():
    device_address = "XX:XX:XX:XX:XX:XX"  # Replace with your device's address
    divoom = Divoom(device_address)
    
    try:
        await divoom.connect()
        await divoom.display.show_light(color=(255, 0, 0))
    finally:
        await divoom.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
```