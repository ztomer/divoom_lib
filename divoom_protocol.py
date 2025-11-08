from .divoom_api.base import DivoomBase
from .divoom_api.system import System
from .divoom_api.alarm import Alarm
from .divoom_api.game import Game
from .divoom_api.light import Light
from .divoom_api.music import Music
from .divoom_api.sleep import Sleep
from .divoom_api.timeplan import Timeplan
from .divoom_api.tool import Tool


class Divoom(DivoomBase, System, Alarm, Game, Light, Music, Sleep, Timeplan, Tool):
    """Class Divoom encapsulates the Divoom Bluetooth communication."""
    pass