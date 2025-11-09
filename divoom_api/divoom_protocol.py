from divoom_api.base import DivoomBase
from divoom_api.system import System
from divoom_api.alarm import Alarm
from divoom_api.game import Game
from divoom_api.light import Light
from divoom_api.music import Music
from divoom_api.sleep import Sleep
from divoom_api.timeplan import Timeplan
from divoom_api.tool import Tool
from divoom_api.display import Display # Added Display import
from divoom_api.channels.time import TimeChannel
from divoom_api.channels.lightning import LightningChannel
from divoom_api.channels.vjeffect import VJEffectChannel
from divoom_api.channels.scoreboard import ScoreBoardChannel
from divoom_api.channels.cloud import CloudChannel
from divoom_api.channels.custom import CustomChannel
from divoom_api.commands.brightness import BrightnessCommand
from divoom_api.commands.temp_weather import TempWeatherCommand
from divoom_api.commands.date_time import DateTimeCommand
from divoom_api.drawing.text import DisplayText
from divoom_api.drawing.drawing import DisplayAnimation


class Divoom(DivoomBase):
    """Class Divoom encapsulates the Divoom Bluetooth communication."""
    def __init__(self, mac=None, logger=None, write_characteristic_uuid=None, notify_characteristic_uuid=None, read_characteristic_uuid=None, spp_characteristic_uuid=None, escapePayload=False, use_ios_le_protocol=False, device_name=None):
        super().__init__(mac, logger, write_characteristic_uuid, notify_characteristic_uuid, read_characteristic_uuid, spp_characteristic_uuid, escapePayload, use_ios_le_protocol, device_name=device_name)
        self.logger.debug("Divoom.__init__ called. super().__init__ completed.")
        self.logger.debug(f"Divoom MRO: {Divoom.__mro__}")
        if hasattr(DivoomBase, 'send_command_and_wait_for_response'):
            self.logger.debug("DivoomBase HAS 'send_command_and_wait_for_response' attribute.")
        else:
            self.logger.error("DivoomBase DOES NOT HAVE 'send_command_and_wait_for_response' attribute.")

        if hasattr(self, 'send_command_and_wait_for_response'):
            self.logger.debug("Divoom instance HAS 'send_command_and_wait_for_response' attribute.")
        else:
            self.logger.error("Divoom instance DOES NOT HAVE 'send_command_and_wait_for_response' attribute.")
        self.system = System(self)
        self.alarm = Alarm(self)
        self.game = Game(self)
        self.light = Light(self)
        self.music = Music(self)
        self.sleep = Sleep(self)
        self.timeplan = Timeplan(self)
        self.tool = Tool(self)
        self.display = Display(self) # Added Display instantiation
        self.time_channel = TimeChannel(self)
        self.lightning_channel = LightningChannel(self)
        self.vj_effect_channel = VJEffectChannel(self)
        self.scoreboard_channel = ScoreBoardChannel(self)
        self.cloud_channel = CloudChannel(self)
        self.custom_channel = CustomChannel(self)
        self.brightness_command = BrightnessCommand(self)
        self.temp_weather_command = TempWeatherCommand(self)
        self.date_time_command = DateTimeCommand(self)
        self.display_text = DisplayText(self)
        self.display_animation = DisplayAnimation(self)