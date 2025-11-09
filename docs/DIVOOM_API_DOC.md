# Divoom Bluetooth API Documentation

## Protocol Introduction

The basic format of the protocol:

**Header + Packet Length + Command Type + Command Data (optional) + Checksum + Footer**

Now let’s explain the significance of each component:

*   **Header**: This marks the beginning of a packet. Whenever this identifier appears in the data stream, it is considered the start of a packet.
*   **Packet Length**: This indicates the total length of the entire packet, excluding the header, footer, and checksum. However, it includes the length field itself.
*   **Command Type**: It represents the type of command for communication between the two parties and is defined as an enumeration.
*   **Command Data**: This field contains the data associated with the command type. If the command does not require any data, this field will be empty.
*   **Checksum**: It is the sum of the packet length, command type, and command data.
*   **Footer**: This marks the end of a packet, signifying the completion of the packet.

Due to the uniqueness requirement of the header and footer in the entire data packet, they need to be escaped if they appear in the data. The header is represented by one byte (0x01) and the footer by one byte (0x02) to minimize their occurrences in the data.

The packet length is represented by two bytes, with the low byte first and the high byte second.

The command type is represented by one byte and starts from 0x04.

The checksum is represented by two bytes and is calculated as the sum of the individual bytes.

All multi-byte data types in the system will follow the little-endian alignment, where the least significant byte comes first, and the most significant byte comes last.

## iOS LE Communication Special Instructions

**Communication**: During the LE communication process, data loss may occur. To maintain stable communication from the device to the iOS app, the communication format from the app to the device has been modified as follows:

**Format: Header + Data Length + Command Identifier (added) + Packet Number (optional, added) + Data + Checksum**

*   **Header**: 4 bytes; 0xFE, 0xEF, 0xAA, 0x55
*   **Data Length**: 2 bytes: data[0] = len & 0xFF; data[1] = len >> 8; includes packet number, data, and checksum;
*   **Command Identifier**: 1 indicates a packet with ACK confirmation, 0 indicates a packet that doesn’t require device response with ACK confirmation.
*   **Packet Number**: 4 bytes: data[0] = id & 0xFF; … data[3] = id >> 24; Only packets with ACK confirmation have this field; packets without ACK confirmation don’t include this field.
*   **Data**: The data format remains unchanged from before.
*   **Checksum**: The checksum is the sum of data length, command identifier, packet number, and data.

**Communication Rule**: For packets without ACK confirmation, the data will be used directly without any retransmission confirmation. For packets with ACK confirmation: all commands are sent from the app, and upon receiving a command, the device will respond with the SPP_LE_CMD_ACK (0x33) command. The app takes this command as a command confirmation. If the app doesn’t receive a response from the device within 1 second, it will resend the command.

## Divoom API Documentation Source

The official Divoom Bluetooth API documentation can be found at:
[https://docin.divoom-gz.com/web/#/5/146](https://docin.divoom-gz.com/web/#/5/146)

This documentation is structured with different sections accessible by changing the number in the URL. For example:
*   Brightness settings: [https://docin.divoom-gz.com/web/#/5/147](https://docin.divoom-gz.com/web/#/5/147)
*   Other sections can be found by incrementing or decrementing the last number in the URL (e.g., `#/5/148`, `#/5/149`, etc.) to explore different commands and features.

### Scraped API Documentation

A local copy of the Divoom API documentation has been scraped and is available in markdown format within the `api_scraper/divoom_docs` directory. Each markdown file in this directory corresponds to a section of the official documentation.

## Set Work Mode (0x05)

**Command Description:** Switch system working mode

**Packet Structure:**
`Head + Len (2 bytes) + Cmd (0x05) + Mode + Checksum + Tail`

**Mode Values:**
*   `SPP_DEFINE_MODE_BT = 0` (Blue)
*   `SPP_DEFINE_MODE_FM = 1` (FM)
*   `SPP_DEFINE_MODE_LINEIN = 2` (LineIn)
*   `SPP_DEFINE_MODE_SD = 3` (SD Card play)
*   `SPP_DEFINE_MODE_USBHOST = 4` (USB HOST)
*   `SPP_DEFINE_MODE_RECORD = 5` (Record)
*   `SPP_DEFINE_MODE_RECORDPLAY = 6` (RecordPlay)
*   `SPP_DEFINE_MODE_UAC = 7` (UAC)
*   `SPP_DEFINE_MODE_PHONE = 8` (Phone)
*   `SPP_DEFINE_MODE_DIVOOM_SHOW = 9` (DIVOOM_SH)
*   `SPP_DEFINE_MODE_ALARM_SET = 10` (Alarm set)
*   `SPP_DEFINE_MODE_GAME = 11` (Game)

**Source:** [https://docin.divoom-gz.com/web/#/5/178](https://docin.divoom-gz.com/web/#/5/178)

## Get Work Mode (0x06)

**Command Description:** Get system working mode

**Packet Structure:**
`Head + Len (2 bytes) + Cmd (0x06) + Checksum + Tail`

**Response:**
`Head + Len (2 bytes) + Cmd (0x06) + Mode + Checksum + Tail`
(Mode values are the same as for Set Work Mode)

**Source:** [https://docin.divoom-gz.com/web/#/5/179](https://docin.divoom-gz.com/web/#/5/179)

---

## Extended Functionalities (Inspired by `node-divoom-timebox-evo`)

The following functionalities have been extended in the `divoom_api` based on the `node-divoom-timebox-evo` library, providing more granular control and display options for Divoom devices.

### Channels

These classes control various display channels on the Divoom device. All channel commands typically use `0x45` as the base command, with specific arguments defining the channel and its settings.

#### Time Channel (`TimeChannel`)

**Description:** Displays time with various customization options.

**Command Code:** `0x45` (with specific arguments)

**Options:**
*   `type`: Defines the display style (e.g., `TimeDisplayType.FullScreen`, `Rainbow`).
*   `color`: Color of the displayed time.
*   `showTime`: Boolean to show/hide time.
*   `showWeather`: Boolean to show/hide weather.
*   `showTemp`: Boolean to show/hide temperature.
*   `showCalendar`: Boolean to show/hide calendar.

#### Lightning Channel (`LightningChannel`)

**Description:** Controls lightning effects and ambient lighting.

**Command Code:** `0x45` (with specific arguments)

**Options:**
*   `type`: Type of lightning effect (e.g., `LightningType.PlainColor`, `Love`).
*   `color`: Color of the lightning.
*   `brightness`: Brightness level (0-100).
*   `power`: Boolean to turn the lightning on/off.

#### VJ Effect Channel (`VJEffectChannel`)

**Description:** Displays various VJ (Video Jockey) effects.

**Command Code:** `0x45` (with specific arguments)

**Options:**
*   `type`: Type of VJ effect (e.g., `VJEffectType.Sparkles`, `Lava`).

#### Scoreboard Channel (`ScoreBoardChannel`)

**Description:** Displays a scoreboard with scores for two players (red and blue).

**Command Code:** `0x45` (with specific arguments)

**Options:**
*   `red`: Score for the red player (0-999).
*   `blue`: Score for the blue player (0-999).

#### Cloud Channel (`CloudChannel`)

**Description:** Activates the Cloud Channel display.

**Command Code:** `0x45` (with specific arguments)

#### Custom Channel (`CustomChannel`)

**Description:** Activates the Custom Channel display.

**Command Code:** `0x45` (with specific arguments)

### Commands

These classes provide direct control over specific device settings.

#### Brightness Command (`BrightnessCommand`)

**Description:** Sets the overall brightness of the Divoom device.

**Command Code:** `0x74`

**Options:**
*   `brightness`: Brightness level (0-100).
*   `in_min`, `in_max`: Input range for brightness mapping (optional).

#### Temperature and Weather Command (`TempWeatherCommand`)

**Description:** Sets the displayed temperature and weather icon.

**Command Code:** `0x5F`

**Options:**
*   `temperature`: Temperature value (-127 to 128).
*   `weather`: Type of weather icon (`WeatherType.Clear`, `CloudySky`, etc.).

#### Date and Time Command (`DateTimeCommand`)

**Description:** Sets the device's internal date and time.

**Command Code:** `0x18`

**Options:**
*   `date`: A `datetime.datetime` object representing the desired date and time.

### Drawing and Display

These classes handle displaying custom content like text and images/animations.

#### Display Text (`DisplayText`)

**Description:** Displays custom text on the Divoom device with various palette and animation effects.

**Command Codes:** `0x6E`, `0x86`, `0x6C` (used in sequence)

**Options:**
*   `text`: The string to display.
*   `paletteFn`: Function to generate the color palette (e.g., `PALETTE_TEXT_ON_BACKGROUND`, `PALETTE_BLACK_ON_RAINBOW`).
*   `animFn`: Function to generate pixel animation data (e.g., `ANIM_STATIC_BACKGROUND`, `ANIM_HORIZONTAL_GRADIANT_BACKGROUND`).

#### Display Animation (`DisplayAnimation`)

**Description:** Processes and displays static images or GIF animations on the Divoom device.

**Command Code:** `0x49` (for animation frames), `0x44` (for static images)

**Usage:**
*   `read(input_data)`: Takes a file path or bytes of an image (GIF, JPEG, PNG, BMP) and converts it into a sequence of Divoom-compatible frames.
*   Handles image resizing to 16x16 pixels, color palette extraction, and pixel data encoding for both static and animated images.

---

## Example Usage: Rotating Channels (`rotate_channels.py`)

A demonstration script `rotate_channels.py` is available in the project root to showcase how to switch between different display channels.

**Usage:**

1.  Open `rotate_channels.py`.
2.  Replace `DIVOOOM_MAC_ADDRESS = "XX:XX:XX:XX:XX:XX"` with the actual MAC address of your Divoom device.
3.  Run the script:
    ```bash
    python3 rotate_channels.py
    ```

This script will connect to your Divoom device and cycle through the implemented channels (Time, Lightning, VJ Effect, Scoreboard, Cloud, Custom), activating each for a few seconds.

---

## Device Discovery

### Discover Divoom Devices (`discover_divoom_devices`)

**Description:** Scans for nearby Bluetooth devices and filters for those whose names contain a specified string (case-insensitive). This is useful for finding Divoom devices without knowing their exact MAC address beforehand.

**Usage:**
```python
import asyncio
import logging
from divoom_api import discover_divoom_devices

async def main():
    logger = logging.getLogger("DiscoveryExample")
    logger.setLevel(logging.INFO)
    
    # Find devices with "Divoom" in their name
    divoom_devices = await discover_divoom_devices(device_name="Divoom", logger=logger)
    
    if divoom_devices:
        logger.info("Found the following Divoom devices:")
        for device in divoom_devices:
            logger.info(f"- Name: {device.name}, Address: {device.address}")
    else:
        logger.info("No Divoom devices found.")

if __name__ == "__main__":
    asyncio.run(main())
```

**Returns:** A list of `bleak.backends.device.BluetoothDevice` objects that match the `device_name` criteria. Each object contains `name` and `address` attributes, among others.
