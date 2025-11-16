
from ..models import (
    COMMANDS,
    SPC_CONTROL_INITIALIZE, SPC_CONTROL_RESET,
    PSC_CONTROL_SET_SCROLLING_MODE_SPEED, PSC_CONTROL_SENDING_IMAGE_DATA
)

class Drawing:
    """
    Provides functionality to control the drawing features of a Divoom device.
    """
    def __init__(self, communicator):
        """
        Initializes the Drawing controller.

        Args:
            communicator: The communicator object to send commands to the device.
        """
        self.communicator = communicator
        self.logger = communicator.logger

    async def set_light_pic(self, pic_data: list) -> bool:
        """
        Display user-drawn pictures on the device (0x44).
        
        Args:
            pic_data (list): The encoded picture data.
        
        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info(f"Setting light pic (0x44)...")
        return await self.communicator.send_command(COMMANDS["set light pic"], pic_data)

    async def drawing_mul_pad_ctrl(self, screen_id: int, r: int, g: int, b: int, num_points: int, offset_list: list):
        """
        Control the multiple screen drawing pad.

        Args:
            screen_id (int): The ID of the screen.
            r (int): Red color component (0-255).
            g (int): Green color component (0-255).
            b (int): Blue color component (0-255).
            num_points (int): The number of points to draw.
            offset_list (list): A list of offsets for the points.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info(
            f"Drawing mul pad control: screen_id={screen_id}, color=({r},{g},{b}), num_points={num_points} (0x3a)...")
        args = []
        args += screen_id.to_bytes(1, byteorder='big')
        args += r.to_bytes(1, byteorder='big')
        args += g.to_bytes(1, byteorder='big')
        args += b.to_bytes(1, byteorder='big')
        args += num_points.to_bytes(1, byteorder='big')
        args.extend(offset_list)
        return await self.communicator.send_command(COMMANDS["drawing mul pad ctrl"], args)

    async def drawing_big_pad_ctrl(self, canvas_width: int, screen_id: int, r: int, g: int, b: int, num_points: int, offset_list: list):
        """
        Control the large screen drawing pad.

        Args:
            canvas_width (int): The width of the canvas.
            screen_id (int): The ID of the screen.
            r (int): Red color component (0-255).
            g (int): Green color component (0-255).
            b (int): Blue color component (0-255).
            num_points (int): The number of points to draw.
            offset_list (list): A list of offsets for the points.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info(
            f"Drawing big pad control: canvas_width={canvas_width}, screen_id={screen_id}, color=({r},{g},{b}), num_points={num_points} (0x3b)...")
        args = []
        args += canvas_width.to_bytes(1, byteorder='big')
        args += screen_id.to_bytes(1, byteorder='big')
        args += r.to_bytes(1, byteorder='big')
        args += g.to_bytes(1, byteorder='big')
        args += b.to_bytes(1, byteorder='big')
        args += num_points.to_bytes(1, byteorder='big')
        args.extend(offset_list)
        return await self.communicator.send_command(COMMANDS["drawing big pad ctrl"], args)

    async def drawing_pad_ctrl(self, r: int, g: int, b: int, num_points: int, offset_list: list):
        """
        Control the drawing pad.

        Args:
            r (int): Red color component (0-255).
            g (int): Green color component (0-255).
            b (int): Blue color component (0-255).
            num_points (int): The number of points to draw.
            offset_list (list): A list of offsets for the points.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info(
            f"Drawing pad control: color=({r},{g},{b}), num_points={num_points} (0x58)...")
        args = []
        args += r.to_bytes(1, byteorder='big')
        args += g.to_bytes(1, byteorder='big')
        args += b.to_bytes(1, byteorder='big')
        args += num_points.to_bytes(1, byteorder='big')
        args.extend(offset_list)
        return await self.communicator.send_command(COMMANDS["drawing pad ctrl"], args)

    async def drawing_pad_exit(self):
        """
        Exit the drawing pad.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info("Drawing pad exit (0x5a)...")
        return await self.communicator.send_command(COMMANDS["drawing pad exit"])

    async def drawing_mul_encode_single_pic(self, screen_id: int, data_length: int, data: list):
        """
        Send a single encoded image to multiple screens.

        Args:
            screen_id (int): The ID of the screen.
            data_length (int): The length of the image data.
            data (list): The image data.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info(
            f"Drawing mul encode single pic: screen_id={screen_id}, data_length={data_length} (0x5b)...")
        args = []
        args += screen_id.to_bytes(1, byteorder='big')
        args += data_length.to_bytes(2, byteorder='little')
        args.extend(data)
        return await self.communicator.send_command(COMMANDS["drawing mul encode single pic"], args)

    async def drawing_mul_encode_pic(self, screen_id: int, total_length: int, pic_id: int, pic_data: list):
        """
        Send encoded animation data to multiple screens for later playback.

        Args:
            screen_id (int): The ID of the screen.
            total_length (int): The total length of the animation data.
            pic_id (int): The ID of the picture.
            pic_data (list): The picture data.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info(
            f"Drawing mul encode pic: screen_id={screen_id}, total_length={total_length}, pic_id={pic_id} (0x5c)...")
        args = []
        args += screen_id.to_bytes(1, byteorder='big')
        args += total_length.to_bytes(2, byteorder='little')
        args += pic_id.to_bytes(1, byteorder='big')
        args.extend(pic_data)
        return await self.communicator.send_command(COMMANDS["drawing mul encode pic"], args)

    async def drawing_mul_encode_gif_play(self):
        """
        Start playing the animation that was previously sent to multiple screens.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info("Drawing mul encode GIF play (0x6b)...")
        return await self.communicator.send_command(COMMANDS["drawing mul encode gif play"])

    async def drawing_encode_movie_play(self, frame_id: int, data_length: int, data: list):
        """
        Play a single-screen movie or animation.

        Args:
            frame_id (int): The ID of the frame.
            data_length (int): The length of the frame data.
            data (list): The frame data.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info(
            f"Drawing encode movie play: frame_id={frame_id}, data_length={data_length} (0x6c)...")
        args = []
        args += frame_id.to_bytes(2, byteorder='little')
        args += data_length.to_bytes(2, byteorder='little')
        args.extend(data)
        return await self.communicator.send_command(COMMANDS["drawing encode movie play"], args)

    async def drawing_mul_encode_movie_play(self, screen_id: int, frame_id: int, data_length: int, data: list):
        """
        Play a movie or animation on multiple screens.

        Args:
            screen_id (int): The ID of the screen.
            frame_id (int): The ID of the frame.
            data_length (int): The length of the frame data.
            data (list): The frame data.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info(
            f"Drawing mul encode movie play: screen_id={screen_id}, frame_id={frame_id}, data_length={data_length} (0x6d)...")
        args = []
        args += screen_id.to_bytes(1, byteorder='big')
        args += frame_id.to_bytes(2, byteorder='little')
        args += data_length.to_bytes(2, byteorder='little')
        args.extend(data)
        return await self.communicator.send_command(COMMANDS["drawing mul encode movie play"], args)

    async def drawing_ctrl_movie_play(self, control_command: int):
        """
        Control the movie playback.

        Args:
            control_command (int): 0x00 to exit movie mode, 0x01 to start playback.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info(
            f"Drawing control movie play: command={control_command} (0x6e)...")
        args = [control_command]
        return await self.communicator.send_command(COMMANDS["drawing ctrl movie play"], args)

    async def drawing_mul_pad_enter(self, r: int, g: int, b: int):
        """
        Enter the multiple screen drawing pad or clear the screen.

        Args:
            r (int): Red color component (0-255).
            g (int): Green color component (0-255).
            b (int): Blue color component (0-255).

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info(
            f"Drawing mul pad enter: color=({r},{g},{b}) (0x6f)...")
        args = []
        args += r.to_bytes(1, byteorder='big')
        args += g.to_bytes(1, byteorder='big')
        args += b.to_bytes(1, byteorder='big')
        return await self.communicator.send_command(COMMANDS["drawing mul pad enter"], args)

    def _handle_spc_initialize(self, kwargs: dict) -> list | None:
        device_id = kwargs.get("device_id")
        image_length = kwargs.get("image_length")
        image_data = kwargs.get("image_data")
        if device_id is not None and image_length is not None and image_data is not None:
            return list(device_id.to_bytes(1, byteorder='big')) + \
                   list(image_length.to_bytes(2, byteorder='little')) + \
                   image_data
        self.logger.error("Missing parameters for Initialize sand paint control.")
        return None

    def _handle_spc_reset(self, kwargs: dict) -> list | None:
        return [] # No additional data

    _spc_handlers = {
        SPC_CONTROL_INITIALIZE: _handle_spc_initialize,
        SPC_CONTROL_RESET: _handle_spc_reset,
    }

    async def sand_paint_ctrl(self, control: int, **kwargs):
        """
        Control the sand painting feature.

        Args:
            control (int): The control word (0 for initialize, 1 for reset).
            **kwargs: The arguments for the control word.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info(f"Sand paint control: control={control} (0x34)...")
        args = [control]

        handler = self._spc_handlers.get(control)
        if handler:
            control_args = handler(self, kwargs)
            if control_args is not None:
                args.extend(control_args)
            else:
                return False
        else:
            self.logger.warning(
                f"Unknown control for sand_paint_ctrl: {control}")
            return False
        return await self.communicator.send_command(COMMANDS["sand paint ctrl"], args)

    def _handle_psc_set_scrolling_mode_speed(self, kwargs: dict) -> list | None:
        mode = kwargs.get("mode")
        speed = kwargs.get("speed")
        if mode is not None and speed is not None:
            return list(mode.to_bytes(1, byteorder='big')) + \
                   list(speed.to_bytes(2, byteorder='little'))
        self.logger.error("Missing 'mode' or 'speed' for Setting Scrolling Mode and Speed.")
        return None

    def _handle_psc_sending_image_data(self, kwargs: dict) -> list | None:
        total_length = kwargs.get("total_length")
        pic_id = kwargs.get("pic_id")
        data = kwargs.get("data")
        if total_length is not None and pic_id is not None and data is not None:
            return list(total_length.to_bytes(2, byteorder='little')) + \
                   list(pic_id.to_bytes(1, byteorder='big')) + \
                   data
        self.logger.error("Missing parameters for Sending Image Data.")
        return None

    _psc_handlers = {
        PSC_CONTROL_SET_SCROLLING_MODE_SPEED: _handle_psc_set_scrolling_mode_speed,
        PSC_CONTROL_SENDING_IMAGE_DATA: _handle_psc_sending_image_data,
    }

    async def pic_scan_ctrl(self, control: int, **kwargs):
        """
        Control the multi-screen scrolling effect.

        Args:
            control (int): The control word (0 for setting mode/speed, 1 for sending data).
            **kwargs: The arguments for the control word.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info(f"Picture scan control: control={control} (0x35)...")
        args = [control]

        handler = self._psc_handlers.get(control)
        if handler:
            control_args = handler(self, kwargs)
            if control_args is not None:
                args.extend(control_args)
            else:
                return False
        else:
            self.logger.warning(
                f"Unknown control for pic_scan_ctrl: {control}")
            return False
        return await self.communicator.send_command(COMMANDS["pic scan ctrl"], args)
