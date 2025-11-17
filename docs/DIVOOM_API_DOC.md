# Divoom Library API Reference

This document provides a reference for the `divoom_lib` Python library API. For details on the underlying Divoom protocol, please refer to [DIVOOM_PROTOCOL_SUMMARY.md](./DIVOOM_PROTOCOL_SUMMARY.md).

## Core Components

The library is structured into several modules, each responsible for a specific set of functionalities.

### `divoom_lib.Divoom`

This is the main class for interacting with a Divoom device.

**`Divoom(mac, logger=None, **kwargs)`**

*   **`mac`**: The Bluetooth MAC address of the Divoom device.
*   **`logger`**: An optional logger instance.
*   **`**kwargs`**: Additional keyword arguments for the `DivoomProtocol` class.

**Attributes:**

*   **`protocol`**: An instance of `divoom_lib.protocol.DivoomProtocol` for low-level communication.
*   **`light`**: An instance of `divoom_lib.display.light.Light` for controlling the device's light.
*   **`animation`**: An instance of `divoom_lib.display.animation.Animation` for managing animations.
*   **`drawing`**: An instance of `divoom_lib.display.drawing.Drawing` for drawing on the screen.
*   **`text`**: An instance of `divoom_lib.display.text.Text` for displaying text.
*   **`device`**: An instance of `divoom_lib.system.device.Device` for general device settings.
*   **`time`**: An instance of `divoom_lib.system.time.Time` for time-related functions.
*   **`bluetooth`**: An instance of `divoom_lib.system.bluetooth.Bluetooth` for Bluetooth settings.
*   **`music`**: An instance of `divoom_lib.media.music.Music` for music playback.
*   **`radio`**: An instance of `divoom_lib.media.radio.Radio` for FM radio.
*   **`alarm`**: An instance of `divoom_lib.scheduling.alarm.Alarm` for managing alarms.
*   **`sleep`**: An instance of `divoom_lib.scheduling.sleep.Sleep` for sleep mode.
*   **`timeplan`**: An instance of `divoom_lib.scheduling.timeplan.Timeplan` for time plans.
*   **`scoreboard`**: An instance of `divoom_lib.tools.scoreboard.Scoreboard` for the scoreboard tool.
*   **`timer`**: An instance of `divoom_lib.tools.timer.Timer` for the timer tool.
*   **`countdown`**: An instance of `divoom_lib.tools.countdown.Countdown` for the countdown tool.
*   **`noise`**: An instance of `divoom_lib.tools.noise.Noise` for the noise tool.

### `divoom_lib.protocol.DivoomProtocol`

This class handles the low-level communication with the Divoom device.

**Methods:**

*   **`async connect()`**: Connects to the Divoom device.
*   **`async disconnect()`**: Disconnects from the Divoom device.
*   **`is_connected`**: Property to check if the device is connected.
*   **`async send_command(command, args)`**: Sends a command to the device.
*   **`async send_command_and_wait_for_response(command, args)`**: Sends a command and waits for a response.

### `divoom_lib.utils.discovery`

This module provides functions for discovering Divoom devices.

**`async discover_device(name_substring="Divoom", address=None, logger=None)`**

*   **`name_substring`**: The name to look for in the device's Bluetooth name (case-insensitive).
*   **`address`**: The Bluetooth address of the device to connect to directly.
*   **`logger`**: An optional logger instance.
*   **Returns**: A tuple of (`bleak.backends.device.BLEDevice`, `device_id`).

## Example Usage

The `examples` directory contains various scripts demonstrating the library's functionalities. To run an example, navigate to the `examples` directory and execute the script with `python3`.

For instance, to discover devices:

```bash
python3 examples/discover_devices.py
```

To control a device, you will typically need its Bluetooth MAC address. You can modify the example scripts to use your device's address.

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
