
from divoom_lib.models import (
    COMMANDS,
    GLM_CURRENT_LIGHT_EFFECT_MODE, GLM_TEMPERATURE_DISPLAY_MODE, GLM_VJ_SELECTION_OPTION,
    GLM_RGB_COLOR_VALUES_START, GLM_BRIGHTNESS_LEVEL, GLM_LIGHTING_MODE_SELECTION_OPTION,
    GLM_ON_OFF_SWITCH, GLM_MUSIC_MODE_SELECTION_OPTION, GLM_SYSTEM_BRIGHTNESS,
    GLM_TIME_DISPLAY_FORMAT_SELECTION_OPTION, GLM_TIME_DISPLAY_RGB_COLOR_VALUES_START,
    GLM_TIME_DISPLAY_MODE, GLM_TIME_CHECKBOX_MODES_START
)

class Light:
    """
    Provides functionality to control the light of a Divoom device.
    """
    def __init__(self, communicator):
        """
        Initializes the Light controller.

        Args:
            communicator: The communicator object to send commands to the device.
        """
        self.communicator = communicator
        self.logger = communicator.logger

    async def get_light_mode(self):
        """
        Get the current light mode settings from the device.

        This method sends a command (0x46) to the device to retrieve the current
        light mode settings and returns them as a dictionary.

        Returns:
            dict | None: A dictionary containing the light mode settings,
                         or None if the command fails.
        """
        self.logger.info("Getting light mode (0x46)...")
        
        command_id = COMMANDS["get light mode"]
        
        # Set the command we are waiting for and send it with the correct protocol
        self.communicator._expected_response_command = command_id
        async with self.communicator._framing_context(use_ios=True, escape=False):
            await self.communicator.send_command(command_id, [])

        # Wait for the response using the default (Basic) protocol
        response = await self.communicator.wait_for_response(command_id)
        
        # Based on documentation, response has 20 bytes
        if response and len(response) >= 20:
            return {
                "current_light_effect_mode": response[GLM_CURRENT_LIGHT_EFFECT_MODE],
                "temperature_display_mode": response[GLM_TEMPERATURE_DISPLAY_MODE],
                "vj_selection_option": response[GLM_VJ_SELECTION_OPTION],
                "rgb_color_values": [response[GLM_RGB_COLOR_VALUES_START], response[GLM_RGB_COLOR_VALUES_START + 1], response[GLM_RGB_COLOR_VALUES_START + 2]],
                "brightness_level": response[GLM_BRIGHTNESS_LEVEL],
                "lighting_mode_selection_option": response[GLM_LIGHTING_MODE_SELECTION_OPTION],
                "on_off_switch": response[GLM_ON_OFF_SWITCH],
                "music_mode_selection_option": response[GLM_MUSIC_MODE_SELECTION_OPTION],
                "system_brightness": response[GLM_SYSTEM_BRIGHTNESS],
                "time_display_format_selection_option": response[GLM_TIME_DISPLAY_FORMAT_SELECTION_OPTION],
                "time_display_rgb_color_values": [response[GLM_TIME_DISPLAY_RGB_COLOR_VALUES_START], response[GLM_TIME_DISPLAY_RGB_COLOR_VALUES_START + 1], response[GLM_TIME_DISPLAY_RGB_COLOR_VALUES_START + 2]],
                "time_display_mode": response[GLM_TIME_DISPLAY_MODE],
                "time_checkbox_modes": [response[GLM_TIME_CHECKBOX_MODES_START], response[GLM_TIME_CHECKBOX_MODES_START + 1], response[GLM_TIME_CHECKBOX_MODES_START + 2], response[GLM_TIME_CHECKBOX_MODES_START + 3]],
            }
        return None
