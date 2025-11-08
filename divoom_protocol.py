import datetime, itertools, logging, math, os, time
from PIL import Image, ImageDraw, ImageFont
from bleak import BleakClient

class DivoomBluetoothProtocol:
    """Class Divoom encapsulates the Divoom Bluetooth communication."""

    COMMANDS = {
        "set radio": 0x05,
        "set volume": 0x08,
        "set playstate": 0x0a,
        "set game keydown": 0x17,
        "set date time": 0x18,
        "set game keyup": 0x21,
        "set keyboard": 0x23,
        "set hot": 0x26,
        "set temp type": 0x2b,
        "set time type": 0x2c,
        "set lightness": 0x32,
        "set sleeptime": 0x40,
        "set alarm": 0x43,
        "set image": 0x44,
        "set view": 0x45,
        "get view": 0x46,
        "set light color": 0x47,
        "set animation frame": 0x49,
        "set temp unit": 0x4c,
        "set memorial": 0x54,
        "set temp": 0x5f,
        "set radio frequency": 0x61,
        "set tool": 0x72,
        "set brightness": 0x74,
        "set game keypress": 0x88,
        "set game": 0xa0,
        "set design": 0xbd,
    }



    logger = None
    client: BleakClient = None
    message_buf = []
    
    def __init__(self, mac=None, logger=None, gatt_characteristic_uuid=None, escapePayload=False):
        self.type = "Ditoo" # Default to Ditoo
        self.screensize = 16
        self.chunksize = 200
        self.colorpalette = None
        self.mac = mac
        self.GATT_CHARACTERISTIC_UUID = gatt_characteristic_uuid
        self.escapePayload = escapePayload
        
        if logger is None:
            logger = logging.getLogger(self.type)
        self.logger = logger

    async def connect(self):
        """Open a connection to the Divoom device using bleak."""
        if self.client is None or not self.client.is_connected:
            try:
                self.client = BleakClient(self.mac)
                await self.client.connect()
                self.logger.info(f"Connected to Divoom device at {self.mac}")
            except Exception as e:
                self.logger.error(f"Failed to connect to {self.mac}: {e}")
                raise

    async def disconnect(self):
        """Closes the connection to the Divoom device."""
        if self.client and self.client.is_connected:
            try:
                await self.client.disconnect()
                self.logger.info(f"Disconnected from Divoom device at {self.mac}")
            except Exception as e:
                self.logger.error(f"Error disconnecting from {self.mac}: {e}")







    async def send_command(self, command, args=None):
        """Send command with optional arguments"""
        if args is None:
            args = []
        if isinstance(command, str):
            command = self.COMMANDS[command]
        
        # Construct payload as a list of bytes
        payload_bytes = [command] + args
        
        return await self.send_payload(payload_bytes)

    async def send_payload(self, payload_bytes):
        """Send raw payload to the Divoom device using the new protocol."""
        if self.client is None or not self.client.is_connected:
            self.logger.error("Not connected to a Divoom device.")
            return

        full_message_hex = self._make_message(payload_bytes)
        
        try:
            # Convert hex string to bytes
            message_bytes = bytes.fromhex(full_message_hex)
            self.logger.debug(f"{self.type} PAYLOAD OUT: {full_message_hex}")
            await self.client.write_gatt_char(self.GATT_CHARACTERISTIC_UUID, message_bytes)
            return True
        except Exception as e:
            self.logger.error(f"Error sending payload: {e}")
            return False

    def _make_message(self, payload_bytes):
        """Make a complete message from the payload data using the new protocol."""
        # payload_bytes is expected to be a list of integers (bytes)
        cs_payload = payload_bytes + self.checksum(payload_bytes)
        escaped_payload = self.escape_payload(cs_payload)
        
        # Construct the final message as a list of integers
        final_message_bytes = [0x01] + escaped_payload + [0x02]
        
        # Convert the list of integers to a hex string for sending
        return "".join(f"{b:02x}" for b in final_message_bytes)

    def _parse_frequency(self, frequency):
        if frequency is not None:
            if isinstance(frequency, str):
                frequency = float(frequency)

            frequency = frequency * 10
            if frequency > 1000:
                return [int(frequency - 1000), int(frequency / 100)]
            else:
                return [int(frequency % 100), int(frequency / 100)]

        return [0x00, 0x00]

    def chunks(self, lst, n):
        """Yield successive n-sized chunks from lst."""
        for i in range(0, len(lst), n):
            yield lst[i:i + n]

    def convert_color(self, color):
        result = []
        result += color[0].to_bytes(1, byteorder='big')
        result += color[1].to_bytes(1, byteorder='big')
        return result

    def checksum(self, payload):
        """Compute the payload checksum. Returned as list with LSM, MSB"""
        length = sum(payload)
        csum = []
        csum += length.to_bytes(4 if length >= 65535 else 2, byteorder='little')
        return csum

    def escape_payload(self, payload):
        """Escaping is not needed anymore as some smarter guys found out"""
        if self.escapePayload == None or self.escapePayload == False:
            return payload
        
        """Escape the payload. It is not allowed to have occurrences of the codes
        0x01, 0x02 and 0x03. They must be escaped by a leading 0x03 followed by 0x04,
        0x05 or 0x06 respectively"""
        escpayload = []
        for payload_data in payload:
            escpayload += \
                [0x03, payload_data + 0x03] if payload_data in range(0x01, 0x04) else [payload_data]
        return escpayload

    def make_frame(self, frame):
        length = len(frame) + 3
        header = [0xAA]
        header += length.to_bytes(2, byteorder='little')
        return [header + frame, length]

    def make_framepart(self, lsum, index, framePart):
        header = []
        if index >= 0:
            header += lsum.to_bytes(4 if self.screensize == 32 else 2, byteorder='little')  # Pixoo-Max expects more
            header += index.to_bytes(2 if self.screensize == 32 else 1, byteorder='little') # Pixoo-Max expects more
        else:
            header += [0x00, 0x0A, 0x0A, 0x04] # Fixed header on single frames
        return header + framePart

    def process_image(self, image, time=None):
        frames = []
        with Image.open(image) as img:
            
            picture_frames = []
            needsFlags = False
            needsResize = False
            frameSize = (self.screensize, self.screensize)
            if self.screensize == 32:
                if img.size[0] <= 16 and img.size[1] <= 16: # Pixoo-Max can handle 16x16 itself
                    frameSize = (16, 16)
                else: needsFlags = True
            if img.size[0] != frameSize[0] or img.size[1] != frameSize[1]:
                needsResize = True
            
            try:
                while True:
                    new_frame = Image.new('RGBA', img.size)
                    new_frame.paste(img, (0, 0), img.convert('RGBA'))

                    if needsResize:
                        new_frame = new_frame.resize(frameSize, Image.Resampling.NEAREST)
                    
                    duration = img.info['duration'] if 'duration' in img.info else None
                    picture_frames.append([new_frame, duration])
                    img.seek(img.tell() + 1)
            except EOFError:
                pass
            
            framesCount = len(picture_frames)
            for pair in picture_frames:
                picture_frame = pair[0]
                picture_time = pair[1]
                
                colors = []
                pixels = [None] * frameSize[0] * frameSize[1]
                
                for pos in itertools.product(range(frameSize[1]), range(frameSize[0])):
                    y, x = pos
                    r, g, b, a = picture_frame.getpixel((x, y))
                    color = [r, g, b] if a > 32 else [0, 0, 0]
                    if color not in colors:
                        colors.append(color)
                    color_index = colors.index(color)
                    pixels[x + frameSize[1] * y] = color_index
                
                if picture_time is None: picture_time = 0
                
                colorCount = len(colors)
                if colorCount >= (frameSize[0] * frameSize[1]): colorCount = 0
                
                frame = self.process_frame(pixels, colors, colorCount, framesCount, picture_time if time is None else time, needsFlags)
                frames.append(frame)
        
        result = []

        if needsFlags: # Pixoo-Max expects two empty frames with flags 0x05 and 0x06 at the start
            result.append(self.make_frame([0x00, 0x00, 0x05, 0x00, 0x00]))
            result.append(self.make_frame([0x00, 0x00, 0x06, 0x00, 0x00, 0x00]))

        for frame in frames:
            result.append(self.make_frame(frame))
        
        return [result, framesCount]
    
    def process_text(self, text, font, size=None, time=None, color1=None, color2=None):
        if color1 is None or len(color1) < 3: color1 = [0xff, 0xff, 0xff]
        if color2 is None or len(color2) < 3: color2 = [0x01, 0x01, 0x01]

        frames = []
        picture_time = 50
        text_margin = 0 if size is None else int((self.screensize - size) / 2)
        text_speed_fast = int(math.ceil(self.screensize / 4))
        text_speed_medium = int(math.ceil(self.screensize / 8))
        text_speed_slow = int(math.ceil(self.screensize / 16))
        needsFlags = True if self.screensize == 32 else False
        frameSize = (self.screensize, self.screensize)
        fontSize = self.screensize - (text_margin * 2) if size is None else size

        if font is not None and 'divoom.ttf' in font: # font calculation is a bit off for divoom.ttf
            fontSize = int(math.ceil(fontSize * 1.2))
            text_margin = int((self.screensize - fontSize) / 2)

        self.logger.info("{0}: FONT: {1}".format(self.type, font))
        fnt = ImageFont.load_default(fontSize)
        try:
            if font is not None: fnt = ImageFont.truetype(font, fontSize)
        except OSError:
            pass
        
        font_width = 60
        with Image.new('RGBA', (self.screensize * 100, self.screensize)) as img_draw:
            drw = ImageDraw.Draw(img_draw)
            drw.fontmode = "1"
            txt = drw.textbbox((0, 0), text, font=fnt)
            font_width = txt[2]
        if font is not None and 'divoom.ttf' in font: # font calculation is a bit off for divoom.ttf
            font_width = int(math.ceil(font_width * 1.2))

        img_width = self.screensize + font_width + self.screensize + text_margin
        with Image.new('RGBA', (img_width, self.screensize), tuple(color2 + [0x00])) as img:
            drw = ImageDraw.Draw(img)
            drw.fontmode = "1"
            drw.text((self.screensize, text_margin), text, font=fnt, fill=tuple(color1 + [0xff]))

            text_speed = text_speed_slow
            framesCount = int(math.floor((img_width - self.screensize) / text_speed))
            if framesCount > 60: # frames are limited, therefore we need to do bigger jumps
                text_speed = text_speed_medium
                picture_time = int(picture_time * (text_speed_medium / text_speed_slow))
                framesCount = int(math.floor((img_width - self.screensize) / text_speed))
                if framesCount > 60: # frames are limited, therefore we need to do even bigger jumps
                    text_speed = text_speed_fast
                    picture_time = int(picture_time * (text_speed_fast / text_speed_medium))
                    framesCount = int(math.floor((img_width - self.screensize) / text_speed))
            if framesCount > 60: self.logger.warning("{0}: text animation is too wide and is very likely cut off.".format(self.type))
            
            for offset in range(framesCount):
                colors = []
                pixels = [None] * frameSize[0] * frameSize[1]

                for pos in itertools.product(range(frameSize[1]), range(frameSize[0])):
                    y, x = pos
                    r, g, b, a = img.getpixel((x + (offset * text_speed), y))
                    color = [r, g, b] if a > 32 else [0, 0, 0]
                    if color not in colors:
                        colors.append(color)
                    color_index = colors.index(color)
                    pixels[x + frameSize[1] * y] = color_index
                
                colorCount = len(colors)
                if colorCount >= (frameSize[0] * frameSize[1]): colorCount = 0

                frame = self.process_frame(pixels, colors, colorCount, framesCount, picture_time if time is None else time, needsFlags)
                frames.append(frame)
        
        result = []

        if needsFlags: # Pixoo-Max expects two empty frames with flags 0x05 and 0x06 at the start
            result.append(self.make_frame([0x00, 0x00, 0x05, 0x00, 0x00]))
            result.append(self.make_frame([0x00, 0x00, 0x06, 0x00, 0x00, 0x00]))

        for frame in frames:
            result.append(self.make_frame(frame))
        
        return [result, framesCount]
    
    def process_frame(self, pixels, colors, colorCount, framesCount, time, needsFlags):
        timeCode = [0x00, 0x00]
        if framesCount > 1:
            timeCode = time.to_bytes(2, byteorder='little')
        
        paletteFlag = 0x00 # default palette flag.
        if needsFlags: paletteFlag = 0x03 # Pixoo-Max expects 0x03 flag. might indicate bigger palette size.

        result = []
        result += timeCode
        result += [paletteFlag]
        result += colorCount.to_bytes(2 if needsFlags else 1, byteorder='little')
        for color in colors:
            result += self.convert_color(color)
        result += self.process_pixels(pixels, colors)
        return result

    def process_pixels(self, pixels, colors):
        """Correctly transform each pixel information based on https://github.com/RomRider/node-divoom-timebox-evo/blob/master/PROTOCOL.md#pixel-string-pixel_data """
        bitsPerPixel = math.ceil(math.log(len(colors)) / math.log(2))
        if bitsPerPixel == 0:
            bitsPerPixel = 1
        
        pixelString = ""
        for pixel in pixels:
            pixelBits = "{0:b}".format(pixel).zfill(8)
            pixelString += pixelBits[::-1][:bitsPerPixel:]
        
        result = []
        for pixel in self.chunks(pixelString, 8):
            result += [int(pixel[::-1], 2)]
        
        return result

    async def send_ping(self):
        """Send a ping (actually it's requesting current view) to the Divoom device to check connectivity"""
        return await self.send_command("get view", [])
    
    async def send_on(self):
        """Sets the display on of the Divoom device"""
        await self.show_light(color=[0x01, 0x01, 0x01], brightness=100, power=True)
    
    async def send_off(self):
        """Sets the display off of the Divoom device"""
        await self.show_light(color=[0x01, 0x01, 0x01], brightness=0, power=False)

    async def show_alarm(self, number=None, time=None, weekdays=None, alarmMode=None, triggerMode=None, frequency=None, volume=None):
        """Show alarm tool on the Divoom device"""
        if number == None: number = 0
        if volume == None: volume = 100
        if alarmMode == None: alarmMode = 0
        if triggerMode == None: triggerMode = 0
        if isinstance(number, str): number = int(number)
        if isinstance(volume, str): volume = int(volume)
        if isinstance(alarmMode, str): alarmMode = int(alarmMode)
        if isinstance(triggerMode, str): triggerMode = int(triggerMode)

        args = []
        args += number.to_bytes(1, byteorder='big')
        args += (0x01 if time != None else 0x00).to_bytes(1, byteorder='big')

        if time != None:
            args += int(time[0:2]).to_bytes(1, byteorder='big')
            args += int(time[3:]).to_bytes(1, byteorder='big')
        else:
            args += [0x00, 0x00]
        if weekdays != None:
            weekbits = 0
            if 'sun' in weekdays: weekbits += 1
            if 'mon' in weekdays: weekbits += 2
            if 'tue' in weekdays: weekbits += 4
            if 'wed' in weekdays: weekbits += 8
            if 'thu' in weekdays: weekbits += 16
            if 'fri' in weekdays: weekbits += 32
            if 'sat' in weekdays: weekbits += 64
            args += weekbits.to_bytes(1, byteorder='big')
        else:
            args += [0x00]

        args += alarmMode.to_bytes(1, byteorder='big')
        args += triggerMode.to_bytes(1, byteorder='big')
        args += self._parse_frequency(frequency)
        args += volume.to_bytes(1, byteorder='big')
        return await self.send_command("set alarm", args)

    async def send_brightness(self, value=None):
        """Send brightness to the Divoom device"""
        if value == None: return
        if isinstance(value, str): value = int(value)
        
        args = []
        args += value.to_bytes(1, byteorder='big')
        return await self.send_command("set brightness", args)

    async def show_clock(self, clock=None, twentyfour=None, weather=None, temp=None, calendar=None, color=None, hot=None):
        """Show clock on the Divoom device in the color"""
        if clock == None: clock = 0
        if twentyfour == None: twentyfour = True
        if weather == None: weather = False
        if temp == None: temp = False
        if calendar == None: calendar = False

        args = [0x00]
        args += [0x01 if twentyfour == True or twentyfour == 1 else 0x00]
        if clock >= 0 and clock <= 15:
            args += clock.to_bytes(1, byteorder='big') # clock mode/style
            args += [0x01] # clock activated
        else:
            args += [0x00, 0x00] # clock mode/style = 0 and clock deactivated
        args += [0x01 if weather == True or weather == 1 else 0x00]
        args += [0x01 if temp == True or temp == 1 else 0x00]
        args += [0x01 if calendar == True or calendar == 1 else 0x00]
        if color is not None and len(color) == 3:
            args += self.convert_color(color)
        result = await self.send_command("set view", args)

        if hot != None:
            args = [0x01 if hot == True or hot == 1 else 0x00]
            await self.send_command("set hot", args)
        return result

    async def show_countdown(self, value=None, countdown=None):
        """Show countdown tool on the Divoom device"""
        if value == None: value = 1
        if isinstance(value, str): value = int(value)

        args = [0x03]
        args += (0x01 if value == True or value == 1 else 0x00).to_bytes(1, byteorder='big')
        if countdown != None:
            args += int(countdown[0:2]).to_bytes(1, byteorder='big')
            args += int(countdown[3:]).to_bytes(1, byteorder='big')
        else:
            args += [0x00, 0x00]
        return await self.send_command("set tool", args)

    async def send_datetime(self, value=None):
        """Send date and time information to the Divoom device"""
        if value == None:
            clock = datetime.datetime.now()
        else:
            clock = datetime.datetime.fromisoformat(value)

        args = []
        args += int(clock.year % 100).to_bytes(1, byteorder='big')
        args += int(clock.year / 100).to_bytes(1, byteorder='big')
        args += clock.month.to_bytes(1, byteorder='big')
        args += clock.day.to_bytes(1, byteorder='big')
        args += clock.hour.to_bytes(1, byteorder='big')
        args += clock.minute.to_bytes(1, byteorder='big')
        args += clock.second.to_bytes(1, byteorder='big')
        return await self.send_command("set date time", args)

    async def show_design(self, number=None):
        """Show design on the Divoom device"""
        args = [0x05]
        result = await self.send_command("set view", args)

        if number != None: # additionally change design tab
            if isinstance(number, str): number = int(number)

            args = [0x17]
            args += number.to_bytes(1, byteorder='big')
            result = await self.send_command("set design", args)
        return result

    async def show_effects(self, number):
        """Show effects on the Divoom device"""
        if number == None: return
        if isinstance(number, str): number = int(number)

        args = [0x03]
        args += number.to_bytes(1, byteorder='big')
        return await self.send_command("set view", args)



    async def show_game(self, value=None):
        """Show game on the Divoom device"""
        if isinstance(value, str): value = int(value)

        args = [0x00 if value == None else 0x01]
        args += (0 if value == None else value).to_bytes(1, byteorder='big')
        return await self.send_command("set game", args)

    async def send_gamecontrol(self, value=None):
        """Send game control to the Divoom device"""
        if value == None: value = 0
        if isinstance(value, str):
            if value == "go": value = 0
            elif value == "ok": value = 5
            elif value == "left": value = 1
            elif value == "right": value = 2
            elif value == "up": value = 3
            elif value == "down": value = 4

        result = None
        args = []
        if value == 0:
            result = await self.send_command("set game keypress", args)
        elif value > 0:
            args += value.to_bytes(1, byteorder='big')
            result = await self.send_command("set game keydown", args)
            time.sleep(0.1)
            result = await self.send_command("set game keyup", args)
        return result

    async def show_image(self, file, time=None):
        """Show image or animation on the Divoom device"""
        frames, framesCount = self.process_image(file, time=time)
        
        result = None
        if framesCount > 1:
            """Sending as Animation"""
            frameParts = []
            framePartsSize = 0
            
            for pair in frames:
                frameParts += pair[0]
                framePartsSize += pair[1]
            
            index = 0
            for framePart in self.chunks(frameParts, self.chunksize):
                frame = self.make_framepart(framePartsSize, index, framePart)
                result = await self.send_command("set animation frame", frame)
                index += 1
        
        elif framesCount == 1:
            """Sending as Image"""
            pair = frames[-1]
            frame = self.make_framepart(pair[1], -1, pair[0])
            result = await self.send_command("set image", frame)
        return result



    async def show_light(self, color, brightness=None, power=None):
        """Show light on the Divoom device in the color"""
        if power == None: power = True
        if brightness == None: brightness = 100
        if isinstance(brightness, str): brightness = int(brightness)

        args = [0x01]
        if color is None or len(color) < 3:
            args += [0xFF, 0xFF, 0xFF]
            args += brightness.to_bytes(1, byteorder='big')
            args += [0x01]
        else:
            args += self.convert_color(color)
            args += brightness.to_bytes(1, byteorder='big')
            args += [0x00]
        args += [0x01 if power == True or power == 1 else 0x00, 0x00, 0x00, 0x00]
        return await self.send_command("set view", args)



    async def show_memorial(self, number=None, value=None, text=None, animate=True):
        """Show memorial tool on the Divoom device"""
        if number == None: number = 0
        if text == None: text = "Home Assistant"
        if isinstance(number, str): number = int(number)
        if not isinstance(text, str): text = str(text)

        args = []
        args += number.to_bytes(1, byteorder='big')
        args += (0x01 if value != None else 0x00).to_bytes(1, byteorder='big')

        if value != None:
            clock = datetime.datetime.fromisoformat(value)
            args += clock.month.to_bytes(1, byteorder='big')
            args += clock.day.to_bytes(1, byteorder='big')
            args += clock.hour.to_bytes(1, byteorder='big')
            args += clock.minute.to_bytes(1, byteorder='big')
        else:
            args += [0x00, 0x00, 0x00, 0x00]
        
        args += (0x01 if animate == True else 0x00).to_bytes(1, byteorder='big')
        for char in text[0:15].ljust(16, '\n').encode('utf-8'):
            args += (0x00 if char == 0x0a else char).to_bytes(2, byteorder='big')
        
        return await self.send_command("set memorial", args)

    async def show_noise(self, value=None):
        """Show noise tool on the Divoom device"""
        if value == None: value = 0
        if isinstance(value, str): value = int(value)

        args = [0x02]
        args += (0x01 if value == True or value == 1 else 0x02).to_bytes(1, byteorder='big')
        return await self.send_command("set tool", args)

    async def send_playstate(self, value=None):
        """Send play/pause state to the Divoom device"""
        args = []
        args += (0x01 if value == True or value == 1 else 0x00).to_bytes(1, byteorder='big')
        return await self.send_command("set playstate", args)

    async def show_radio(self, value=None, frequency=None):
        """Show radio on the Divoom device and optionally changes to the given frequency"""
        args = []
        args += (0x01 if value == True or value == 1 else 0x00).to_bytes(1, byteorder='big')
        result = await self.send_command("set radio", args)

        if (value == True or value == 1) and frequency != None:
            if isinstance(frequency, str): frequency = float(frequency)

            args = []
            args += self._parse_frequency(frequency)
            await self.send_command("set radio frequency", args)
        return result



    async def show_sleep(self, value=None, sleeptime=None, sleepmode=None, volume=None, color=None, brightness=None, frequency=None):
        """Show sleep mode on the Divoom device and optionally sets mode, volume, time, color, frequency and brightness"""
        if sleeptime == None: sleeptime = 120
        if sleepmode == None: sleepmode = 0
        if volume == None: volume = 100
        if brightness == None: brightness = 100
        if isinstance(sleeptime, str): sleeptime = int(sleeptime)
        if isinstance(sleepmode, str): sleepmode = int(sleepmode)
        if isinstance(volume, str): volume = int(volume)
        if isinstance(brightness, str): brightness = int(brightness)

        args = []
        args += sleeptime.to_bytes(1, byteorder='big')
        args += sleepmode.to_bytes(1, byteorder='big')
        args += (0x01 if value == True or value == 1 else 0x00).to_bytes(1, byteorder='big')

        args += self._parse_frequency(frequency)
        args += volume.to_bytes(1, byteorder='big')

        if color is None or len(color) < 3:
            args += [0x00, 0x00, 0x00]
        else:
            args += self.convert_color(color)
        args += brightness.to_bytes(1, byteorder='big')

        return await self.send_command("set sleeptime", args)

    async def show_temperature(self, value=None, color=None):
        """Show temperature on the Divoom device in the color"""
        result = await self.show_clock(clock=None, twentyfour=None, weather=None, temp=True, calendar=None, color=color, hot=None)
        await self.send_command("set temp type", [0x01 if value == True or value == 1 else 0x00])
        return result

    async def show_text(self, text, font, size=None, time=None, color1=None, color2=None):
        """Show image or animation on the Divoom device"""
        frames, framesCount = self.process_text(text, font, size=size, time=time, color1=color1, color2=color2)
        
        result = None
        if framesCount > 1:
            """Sending as Animation"""
            frameParts = []
            framePartsSize = 0
            
            for pair in frames:
                frameParts += pair[0]
                framePartsSize += pair[1]
            
            index = 0
            for framePart in self.chunks(frameParts, self.chunksize):
                frame = self.make_framepart(framePartsSize, index, framePart)
                result = await self.send_command("set animation frame", frame)
                index += 1
        
        elif framesCount == 1:
            """Sending as Image"""
            pair = frames[-1]
            frame = self.make_framepart(pair[1], -1, pair[0])
            result = await self.send_command("set image", frame)
        return result

    async def show_timer(self, value=None):
        """Show timer tool on the Divoom device"""
        if value == None: value = 2
        if isinstance(value, str): value = int(value)

        args = [0x00]
        args += value.to_bytes(1, byteorder='big')
        return await self.send_command("set tool", args)

    async def show_visualization(self, number, color1, color2):
        """Show visualization on the Divoom device"""
        if number == None: return
        if isinstance(number, str): number = int(number)

        args = [0x04]
        args += number.to_bytes(1, byteorder='big')
        return await self.send_command("set view", args)

    async def send_volume(self, value=None):
        """Send volume to the Divoom device"""
        if value == None: value = 0
        if isinstance(value, str): value = int(value)

        args = []
        args += int(value * 15 / 100).to_bytes(1, byteorder='big')
        return await self.send_command("set volume", args)

    async def send_weather(self, value=None, weather=None):
        """Send weather to the Divoom device"""
        if value == None: return
        if weather == None: weather = 0
        if isinstance(weather, str): weather = int(weather)

        args = []
        args += int(round(float(value[0:-2]))).to_bytes(1, byteorder='big', signed=True)
        args += weather.to_bytes(1, byteorder='big')
        result = await self.send_command("set temp", args)

        if value[-2] == "°C":
            await self.send_command("set temp type", [0x00])
        if value[-2] == "°F":
            await self.send_command("set temp type", [0x01])
        return result
