from typing import List, Tuple

from . import models


def int2hexlittle(value: int) -> str:
    byte1 = (value & 0xFF)
    byte2 = ((value >> 8) & 0xFF)
    return f"{byte1:02x}{byte2:02x}"


def escape_payload(payload_bytes: list) -> list:
    escaped = []
    for b in payload_bytes:
        if b == models.ESCAPE_BYTE_1:
            escaped.extend(models.ESCAPE_SEQUENCE_1)
        elif b == models.ESCAPE_BYTE_2:
            escaped.extend(models.ESCAPE_SEQUENCE_2)
        elif b == models.ESCAPE_BYTE_3:
            escaped.extend(models.ESCAPE_SEQUENCE_3)
        else:
            escaped.append(b)
    return escaped


def get_checksum(data_bytes: list) -> str:
    sum_val = sum(data_bytes)
    return int2hexlittle(sum_val)


def encode_basic_payload(payload_bytes: list, escape: bool = False) -> bytes:
    working_payload = payload_bytes
    if escape:
        working_payload = escape_payload(payload_bytes)

    length_value = len(working_payload) + models.MESSAGE_CHECKSUM_LENGTH
    length_bytes = length_value.to_bytes(2, byteorder='little')

    checksum = (sum(length_bytes) + sum(working_payload)) & 0xFFFF

    message = bytearray()
    message.append(models.MESSAGE_START_BYTE)
    message += length_bytes
    message += bytes(working_payload)
    message += checksum.to_bytes(2, byteorder='little')
    message.append(models.MESSAGE_END_BYTE)
    return bytes(message)


def encode_ios_le_payload(payload_bytes: list, packet_number: int = 0x00000000) -> bytes:
    """
    Encode a command in the official Divoom iOS-LE protocol format.

    Layout (from the official APK ``com.divoom.Divoom.bluetooth.c#b``):
        [0xFE, 0xEF, 0xAA, 0x55]                 (4-byte header)
        [len_lo, len_hi]                          (len = total_bytes - 7, little-endian)
        [packet_number_byte]                      (1 byte — only the low byte is transmitted)
        [command_id]                              (1 byte, separate from the data payload)
        [data...]                                 (raw data WITHOUT the command id)
        [checksum_lo, checksum_hi]                (sum of bytes 4..end-3, little-endian)
        [0x02]                                    (end marker)

    The caller passes ``payload_bytes`` as ``[cmd, data...]`` (i.e. cmd is
    included). We strip the cmd off and emit it separately so the wire format
    matches the APK exactly. (Previous versions incorrectly emitted the cmd
    twice — once as ``[command_identifier]`` and again inside ``data_bytes``.)
    """
    if not payload_bytes:
        raise ValueError("payload_bytes must contain at least the command id")
    command_identifier = payload_bytes[0]
    data_bytes = payload_bytes[1:]

    # Total wire length = header(4) + length(2) + packet_num(1) + cmd(1)
    #                  + data + checksum(2) + end(1)
    total_len = 4 + 2 + 1 + 1 + len(data_bytes) + 2 + 1
    length_field = total_len - 7
    length_bytes = list(length_field.to_bytes(2, byteorder="little"))

    packet_number_byte = packet_number & 0xFF

    pre_checksum = (
        length_bytes
        + [packet_number_byte, command_identifier]
        + list(data_bytes)
    )
    checksum = sum(pre_checksum) & 0xFFFF
    checksum_bytes = list(checksum.to_bytes(2, byteorder="little"))

    wire = (
        list(models.IOS_LE_MESSAGE_HEADER)
        + length_bytes
        + [packet_number_byte, command_identifier]
        + list(data_bytes)
        + checksum_bytes
        + [models.MESSAGE_END_BYTE]
    )
    return bytes(wire)


def parse_ios_le_notification(data: bytes) -> dict | None:
    """
    Parse a notification sent in the official Divoom iOS-LE protocol format.

    Layout matches ``encode_ios_le_payload``. The data section begins at
    ``IOS_LE_DATA_OFFSET`` (8) and runs up to ``-IOS_LE_CHECKSUM_LENGTH``;
    the command id lives at ``IOS_LE_COMMAND_IDENTIFIER`` (7) — *not* 6 as
    the previous constants claimed. The packet number is a single byte at
    offset 6.
    """
    if len(data) < models.IOS_LE_MIN_DATA_LENGTH:
        return None
    if data[0:4] != bytes(models.IOS_LE_HEADER):
        return None
    if data[-1] != models.MESSAGE_END_BYTE:
        return None
    command_id = data[models.IOS_LE_COMMAND_IDENTIFIER]
    packet_number = data[models.IOS_LE_PACKET_NUMBER]
    # Payload sits between the data offset and the (checksum + end marker).
    payload = bytes(
        data[models.IOS_LE_DATA_OFFSET : -models.IOS_LE_CHECKSUM_LENGTH - 1]
    )
    checksum = int.from_bytes(
        data[-models.IOS_LE_CHECKSUM_LENGTH - 1:-1], byteorder="little"
    )
    return {
        "command_id": command_id,
        "payload": payload,
        "packet_number": packet_number,
        "checksum": checksum,
    }


def parse_basic_protocol_frames(buf: bytearray) -> Tuple[list, bytearray]:
    messages = []

    while len(buf) >= 7:
        try:
            start_index = buf.index(models.MESSAGE_START_BYTE)
        except ValueError:
            buf.clear()
            break

        if start_index > 0:
            del buf[:start_index]

        if len(buf) < 4:
            break

        length = int.from_bytes(buf[1:3], byteorder='little')
        total_message_len = 4 + length

        if len(buf) < total_message_len:
            break

        message = bytes(buf[:total_message_len])
        del buf[:total_message_len]

        if message[-1] != models.MESSAGE_END_BYTE:
            continue

        if len(message) > 5 and message[3] == models.ACK_PATTERN_BYTE_1 and message[5] == models.ACK_PATTERN_BYTE_3:
            command_id = message[4]
            payload = message[6:-3]
        else:
            command_id = message[3]
            payload = message[4:-3]

        checksum_input = message[1:-3]
        # Mask to 16 bits to match the encoder (encode_basic_payload uses
        # `& 0xFFFF`); without this, large frames (e.g. images) whose checksum
        # overflows 16 bits were wrongly rejected.
        calculated_checksum = sum(checksum_input) & 0xFFFF
        received_checksum = int.from_bytes(bytes(message[-3:-1]), byteorder='little')
        if received_checksum != calculated_checksum:
            continue

        messages.append({'command_id': command_id, 'payload': bytearray(payload)})

    return messages, buf
