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
    command_identifier = payload_bytes[0]
    data_bytes = payload_bytes
    packet_number_bytes = list(
        packet_number.to_bytes(models.IOS_LE_MESSAGE_PACKET_NUM_LENGTH, byteorder='little'))
    data_length_value = models.IOS_LE_MESSAGE_CMD_ID_LENGTH + models.IOS_LE_MESSAGE_PACKET_NUM_LENGTH + len(data_bytes) + models.IOS_LE_MESSAGE_CHECKSUM_LENGTH
    data_length_bytes = list(
        data_length_value.to_bytes(2, byteorder='little'))
    checksum_input = data_length_bytes + \
        [command_identifier] + packet_number_bytes + data_bytes
    checksum_value = sum(checksum_input)
    checksum_bytes = list(checksum_value.to_bytes(models.IOS_LE_MESSAGE_CHECKSUM_LENGTH, byteorder='little'))
    final_message_bytes = models.IOS_LE_MESSAGE_HEADER + data_length_bytes + \
        [command_identifier] + packet_number_bytes + \
        data_bytes + checksum_bytes
    return bytes(final_message_bytes)


def parse_ios_le_notification(data: bytes) -> dict | None:
    if len(data) >= models.IOS_LE_MIN_DATA_LENGTH and data[0:4] == bytes(models.IOS_LE_HEADER):
        command_identifier = data[models.IOS_LE_COMMAND_IDENTIFIER]
        packet_number = int.from_bytes(data[models.IOS_LE_PACKET_NUMBER_START:models.IOS_LE_PACKET_NUMBER_END], byteorder='little')
        response_data = data[models.IOS_LE_DATA_OFFSET:-models.IOS_LE_CHECKSUM_LENGTH]
        checksum = int.from_bytes(data[-models.IOS_LE_CHECKSUM_LENGTH:], byteorder='little')
        return {
            'command_id': command_identifier,
            'payload': response_data,
            'packet_number': packet_number,
            'checksum': checksum,
        }
    return None


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
