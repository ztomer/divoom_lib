# divoom_api/drawing/drawing.py
from ..base import DivoomBase
from typing import Optional, Dict, Any, List, Union
import asyncio
from PIL import Image, ImageSequence
import io

class DisplayAnimation:
    """
    This class is used to display static images and animations on the Divoom Timebox Evo.
    """
    def __init__(self, divoom_instance: DivoomBase):
        self._divoom_instance = divoom_instance

    async def read(self, input_data: Union[str, bytes]) -> List[List[int]]:
        """
        Reads an image and returns a list of Divoom-formatted frames.
        It works with GIF, JPEG, PNG, and BMP.
        """
        if isinstance(input_data, str):
            # Assume it's a file path
            with open(input_data, 'rb') as f:
                buffer = f.read()
        elif isinstance(input_data, bytes):
            buffer = input_data
        else:
            raise ValueError("Input must be a file path (str) or bytes.")

        image = Image.open(io.BytesIO(buffer))
        
        if hasattr(image, 'is_animated') and image.is_animated:
            return await self._display_animation_from_gif(image)
        else:
            return await self._display_image(image)

    async def _display_image(self, image: Image.Image) -> List[List[int]]:
        """
        Processes a static image and returns a list containing one Divoom-formatted frame.
        """
        resized_image = image.resize((16, 16), Image.NEAREST)
        return [self._encode_image_data(resized_image, is_animated=False)]

    async def _display_animation_from_gif(self, image: Image.Image) -> List[List[int]]:
        """
        Processes a GIF animation and returns a list of Divoom-formatted frames.
        """
        frames_data = []
        for i, frame in enumerate(ImageSequence.Iterator(image)):
            resized_frame = frame.resize((16, 16), Image.NEAREST)
            # Get duration for each frame, default to 100ms if not available
            duration = frame.info.get('duration', 100)
            frames_data.append(self._encode_image_data(resized_frame, is_animated=True, frame_delay=duration, frame_index=i))
        return frames_data

    def _encode_image_data(self, image: Image.Image, is_animated: bool, frame_delay: int = 0, frame_index: int = 0) -> List[int]:
        """
        Encodes image data into Divoom protocol format.
        This function combines logic from DivoomJimp, DivoomJimpAnim, DivoomJimpStatic.
        """
        # Convert to RGB if not already
        image = image.convert("RGB")

        colors_array = []
        pixel_indices = []
        color_to_index = {}

        for y in range(image.height):
            for x in range(image.width):
                r, g, b = image.getpixel((x, y))
                color_hex = f"{r:02x}{g:02x}{b:02x}"

                if color_hex not in color_to_index:
                    color_to_index[color_hex] = len(colors_array)
                    colors_array.append(color_hex)
                pixel_indices.append(color_to_index[color_hex])

        nb_colors = len(colors_array)
        if nb_colors > 256:
            raise ValueError(f"Too many colors ({nb_colors}) in image. Max 256 supported.")

        # Calculate bits per pixel
        if nb_colors <= 1:
            bits_per_pixel = 1
        else:
            bits_per_pixel = math.ceil(math.log2(nb_colors))
        
        # Build pixel string (binary representation)
        pixel_binary_string = ""
        for pixel_idx in pixel_indices:
            pixel_binary_string += bin(pixel_idx)[2:].zfill(bits_per_pixel)

        # Pad to a multiple of 8 bits
        while len(pixel_binary_string) % 8 != 0:
            pixel_binary_string += "0"
        
        # Convert binary string to hex string
        pixel_hex_string = ""
        for i in range(0, len(pixel_binary_string), 8):
            byte_str = pixel_binary_string[i:i+8]
            pixel_hex_string += f"{int(byte_str, 2):02x}"

        # Construct the Divoom message payload
        # This part is complex and depends on whether it's static or animated
        
        if is_animated:
            # Logic for DivoomJimpAnim
            # Node.js: 'aa' + sizeHex + delayHex + (resetPalette ? "00" : "01") + nbColorsHex + colorString + pixelString
            # Here, we're building the payload bytes directly.
            
            # delayHex (2 bytes, little endian)
            delay_hex = self._divoom_instance._int2hexlittle(frame_delay)
            
            # resetPalette (1 byte, "00" for reset, "01" for reuse) - always reset for simplicity here
            reset_palette = "00" 
            
            # nbColorsHex (1 byte)
            nb_colors_hex = self._divoom_instance.number2HexString(nb_colors)
            
            # colorString (variable length)
            color_string = "".join(colors_array)
            
            # Combine all parts into a hex string first
            payload_inner_hex = delay_hex + reset_palette + nb_colors_hex + color_string + pixel_hex_string
            
            # Calculate size (length of payload_inner_hex / 2 + 2 for 'aa' and size itself)
            # The Node.js code calculates size as (stringWithoutHeader.length + 6) / 2
            # stringWithoutHeader is delayHex + resetPalette + nbColorsHex + colorString + pixelString
            # So, payload_inner_hex is stringWithoutHeader.
            # The '6' comes from 'aa' (2 bytes) + sizeHex (2 bytes) + '0000' (2 bytes, for static image)
            # For animation, it's 'aa' (2 bytes) + sizeHex (2 bytes)
            # Let's follow the Node.js logic for size calculation for animation:
            # sizeHex = int2hexlittle((stringWithoutHeader.length + 6) / 2);
            # The '6' seems to be for 'aa' + sizeHex + '0000' (static image header)
            # For animation, it's 'aa' + sizeHex. So, the length of the actual data is payload_inner_hex.length / 2
            # The total length of the message is 1 (0xAA) + 2 (length) + payload_inner_hex.length / 2
            # The Node.js code has `sizeHex = int2hexlittle((stringWithoutHeader.length + 6) / 2);`
            # This `+6` is confusing. Let's re-examine the Divoom protocol.
            # Divoom protocol: 0x01 + length (2 bytes) + command (1 byte) + payload + checksum (2 bytes) + 0x02
            # The Node.js `TimeboxEvoMessage` handles the 0x01, length, checksum, 0x02.
            # The `asDivoomMessage` method in `DivoomJimpAnim` returns a `TimeboxEvoMessage` with `fullString`.
            # `fullString = 'aa' + sizeHex + stringWithoutHeader;`
            # `stringWithoutHeader = delayHex + resetPalette + nbColorsHex + colorString + pixelString`
            # `sizeHex = int2hexlittle((stringWithoutHeader.length + 6) / 2);`
            # The `+6` is likely for the `aa` (1 byte) + `sizeHex` (2 bytes) + `0000` (2 bytes) + `00` (1 byte) in the static image header.
            # For animation, the `aa` is a magic number, not part of the length.
            # The actual payload for animation starts after `aa` and `sizeHex`.
            # So, the length should be `len(payload_inner_hex) / 2`.
            # Let's assume `sizeHex` in Node.js is the length of `stringWithoutHeader` in bytes.
            
            # Let's re-evaluate the Node.js `asDivoomMessage` for animation:
            # `fullString = 'aa' + sizeHex + stringWithoutHeader;`
            # `sizeHex` is `int2hexlittle((stringWithoutHeader.length + 6) / 2)`
            # This `sizeHex` is the length of the *entire* message part that follows `aa` and `sizeHex` itself.
            # So, `stringWithoutHeader` is the actual data.
            # `stringWithoutHeader.length / 2` is the number of bytes in `stringWithoutHeader`.
            # The `+6` is likely for the `delayHex` (2 bytes), `resetPalette` (1 byte), `nbColorsHex` (1 byte), and two unknown bytes (0000).
            # Let's assume the `sizeHex` is the length of `delayHex + resetPalette + nbColorsHex + colorString + pixel_hex_string` in bytes.
            
            # Let's simplify and assume the payload is `delay_hex + reset_palette + nb_colors_hex + color_string + pixel_hex_string`.
            # The command for animation is 0x49.
            # The Node.js code uses `_PACKAGE_PREFIX = '49'` for animation.
            # The `TimeboxEvoMessage` is constructed with `fullString`.
            # `fullString` is then split into chunks and sent.
            # The `fullString` starts with `aa` which is a magic number.
            # The `sizeHex` is the length of the data that follows `aa` and `sizeHex`.
            # So, the actual data is `delayHex + resetPalette + nbColorsHex + colorString + pixelString`.
            # The length of this data in bytes is `len(payload_inner_hex) / 2`.
            # The `sizeHex` in Node.js is `int2hexlittle((stringWithoutHeader.length + 6) / 2)`.
            # This `+6` is still a mystery.
            # Let's look at the Rust library for animation.
            # Rust `Animation` serialize: `writer.write_u8(self.control_word as u8)?;`
            # `writer.write_u32::<LittleEndian>(self.file_size)?;`
            # `writer.write_u16::<LittleEndian>(self.offset_id)?;`
            # `writer.write_all(&self.image_part)?;`
            # This is for sending animation *files*, not individual frames.
            
            # Let's go back to the Node.js `DivoomJimpAnim.asDivoomMessage()`
            # `fullString = 'aa' + sizeHex + stringWithoutHeader;`
            # `stringWithoutHeader = delayHex + (resetPalette ? "00" : "01") + nbColorsHex + colorString + pixelString`
            # `sizeHex = int2hexlittle((stringWithoutHeader.length + 6) / 2);`
            # The `+6` is likely for the `aa` (1 byte) + `sizeHex` (2 bytes) + `0000` (2 bytes) + `00` (1 byte) in the static image header.
            # For animation, the `aa` is a magic number, not part of the length.
            # The actual payload for animation starts after `aa` and `sizeHex`.
            # So, the length should be `len(payload_inner_hex) / 2`.
            # Let's assume `sizeHex` in Node.js is the length of `stringWithoutHeader` in bytes.
            
            # Let's assume the `fullString` is the actual payload that needs to be sent.
            # The `TimeboxEvoMessage` takes `msg` as a hex string.
            # So, we need to construct the `fullString` as a hex string.
            
            # `stringWithoutHeader` is `delay_hex + reset_palette + nb_colors_hex + color_string + pixel_hex_string`
            # `size_value = (len(payload_inner_hex) // 2) + 6` (This is the Node.js logic)
            # `size_hex = self._divoom_instance._int2hexlittle(size_value)`
            
            # Let's try to reconstruct the `fullString` as in Node.js.
            # `stringWithoutHeader` is the actual data part.
            string_without_header = delay_hex + reset_palette + nb_colors_hex + color_string + pixel_hex_string
            
            # The Node.js `sizeHex` is `int2hexlittle((stringWithoutHeader.length + 6) / 2)`
            # This `+6` is still a mystery. Let's assume it's a fixed offset for animation.
            # The length of `string_without_header` in bytes is `len(string_without_header) // 2`.
            # So, `size_value = (len(string_without_header) // 2) + 6`
            # `size_hex = self._divoom_instance._int2hexlittle(size_value)`
            
            # Let's try a simpler approach based on the Divoom protocol structure.
            # The command for animation is 0x49.
            # The payload for 0x49 is complex.
            # The Node.js `DivoomJimpAnim.asDivoomMessage()` returns a `TimeboxEvoMessage`
            # which then gets wrapped in the full Divoom packet.
            # The `fullString` in `asDivoomMessage` is the *payload* for the 0x49 command.
            # So, the `fullString` should be converted to bytes and sent as args to 0x49.
            
            # Let's assume the `fullString` is the actual payload for the 0x49 command.
            # `fullString = 'aa' + sizeHex + stringWithoutHeader;`
            # `stringWithoutHeader = delayHex + (resetPalette ? "00" : "01") + nbColorsHex + colorString + pixelString`
            # `sizeHex = int2hexlittle((stringWithoutHeader.length + 6) / 2);`
            
            # Let's try to calculate `size_hex` as `len(string_without_header) // 2`.
            # This would be the actual byte length of the data.
            
            # Let's try to follow the Node.js `sizeHex` calculation exactly.
            # `stringWithoutHeader` is `delay_hex + reset_palette + nb_colors_hex + color_string + pixel_hex_string`
            # `size_value = (len(string_without_header) // 2) + 6`
            # `size_hex = self._divoom_instance._int2hexlittle(size_value)`
            
            # `full_payload_hex = "aa" + size_hex + string_without_header`
            
            # This `full_payload_hex` is then sent as the payload for command 0x49.
            
            # Let's try this:
            string_without_header = delay_hex + reset_palette + nb_colors_hex + color_string + pixel_hex_string
            size_value = (len(string_without_header) // 2) + 6 # Node.js magic number
            size_hex = self._divoom_instance._int2hexlittle(size_value)
            
            full_payload_hex = "aa" + size_hex + string_without_header
            
            return [int(full_payload_hex[i:i+2], 16) for i in range(0, len(full_payload_hex), 2)]
            
        else:
            # Logic for DivoomJimpStatic
            # Node.js: 'aa' + sizeHex + '000000' + nbColorsHex + colorString + pixelString
            # `sizeHex = int2hexlittle((('AA0000000000' + stringWithoutHeader).length) / 2);`
            # `stringWithoutHeader = nbColorsHex + colorString + pixelString`
            
            nb_colors_hex = self._divoom_instance.number2HexString(nb_colors)
            color_string = "".join(colors_array)
            
            string_without_header = nb_colors_hex + color_string + pixel_hex_string
            
            # Node.js `sizeHex` calculation for static image:
            # `sizeHex = int2hexlittle((('AA0000000000' + stringWithoutHeader).length) / 2);`
            # The `AA0000000000` part is `aa` (1 byte) + `sizeHex` (2 bytes) + `000000` (3 bytes) = 6 bytes.
            # So, `size_value = (len(string_without_header) // 2) + 6`
            # `size_hex = self._divoom_instance._int2hexlittle(size_value)`
            
            # `full_payload_hex = "aa" + size_hex + "000000" + string_without_header`
            
            # Let's try this:
            string_without_header = nb_colors_hex + color_string + pixel_hex_string
            size_value = (len(string_without_header) // 2) + 6 # Node.js magic number
            size_hex = self._divoom_instance._int2hexlittle(size_value)
            
            full_payload_hex = "aa" + size_hex + "000000" + string_without_header
            
            return [int(full_payload_hex[i:i+2], 16) for i in range(0, len(full_payload_hex), 2)]
