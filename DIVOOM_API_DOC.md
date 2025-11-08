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