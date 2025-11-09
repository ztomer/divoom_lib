# divoom_api/constants.py

# Command codes
COMMANDS = {
    "set volume": 0x08,
    "set playstate": 0x0a,
    "set gif speed": 0x16,
    "set game ctrl info": 0x17,
    "set date time": 0x18,
    "app send eq gif": 0x1b,
    "set game ctrl key up info": 0x21,
    "set keyboard": 0x23,
    "set hot": 0x26,
    "set blue password": 0x27,
    "sand paint ctrl": 0x34,
    "pic scan ctrl": 0x35,
    "drawing mul pad ctrl": 0x3a,
    "drawing big pad ctrl": 0x3b,
    "set temp type": 0x2b,
    "set time type": 0x2c,
    "set lightness": 0x32,
    "set sleeptime": 0x40,
    "set sleep scene": 0x41,
    "get alarm time": 0x42,
    "set alarm": 0x43,
    "set light pic": 0x44,
    "set light mode": 0x45,
    "set channel (light mode)": 0x45, # Clarified to avoid ambiguity with "set light mode"
    "get light mode": 0x46,
    "get current channel and brightness": 0x46, # Clarified to avoid ambiguity with "get light mode"
    "app need get music list": 0x47,
    "set light phone gif": 0x49,
    "set alarm gif": 0x51,
    "set temp unit": 0x4c,
    "set boot gif": 0x52,
    "get memorial time": 0x53,
    "set memorial": 0x54,
    "set memorial gif": 0x55,
    "set time manage info": 0x56,
    "set time manage ctrl": 0x57,
    "drawing pad ctrl": 0x58,
    "get device temp": 0x59,
    "drawing pad exit": 0x5a,
    "drawing mul encode single pic": 0x5b,
    "drawing mul encode pic": 0x5c,
    "send net temp": 0x5d,
    "send net temp disp": 0x5e,
    "set temp": 0x5f,
    "set radio frequency": 0x61,
    "drawing mul encode gif play": 0x6b,
    "drawing encode movie play": 0x6c,
    "drawing mul encode movie play": 0x6d,
    "drawing ctrl movie play": 0x6e,
    "drawing mul pad enter": 0x6f,
    "get tool info": 0x71,
    "set tool": 0x72,
    "get net temp disp": 0x73,
    "set brightness": 0x74,
    "set device name": 0x75,
    "get device name": 0x76,
    "get sd music list total num": 0x7d,
    "set alarm vol ctrl": 0x82,
    "set song dis ctrl": 0x83,
    "set light phone word attr": 0x87,
    "set text content": 0x86,
    "send game shark": 0x88,
    "set poweron channel": 0x8a,
    "app new send gif cmd": 0x8b,
    "app new user define": 0x8c,
    "app big64 user define": 0x8d,
    "app get user define info": 0x8e,
    "set game": 0xa0,
    "get sleep scene": 0xa2,
    "set sleep scene listen": 0xa3,
    "set scene vol": 0xa4,
    "set alarm listen": 0xa5,
    "set alarm vol": 0xa6,
    "set sound ctrl": 0xa7,
    "get sound ctrl": 0xa8,
    "set auto power off": 0xab,
    "get auto power off": 0xac,
    "set sleep color": 0xad,
    "set sleep light": 0xae,
    "set user gif": 0xb1,
    "set low power switch": 0xb2,
    "get low power switch": 0xb3,
    "get sd music info": 0xb4,
    "set sd music info": 0xb5,
    "modify user gif items": 0xb6,
    "set rhythm gif": 0xb7,
    "set sd music position": 0xb8,
    "set sd music play mode": 0xb9,
    "set poweron voice vol": 0xbb,
    "set design": 0xbd,
    "set work mode": 0x05,
    "get sd play name": 0x06,
    "get sd music list": 0x07,
    "get volume": 0x09,
    "get play status": 0x0b,
    "set sd play music id": 0x11,
    "set sd last next": 0x12,
    "get work mode": 0x06,
    "send sd list over": 0x14,
    "send sd status": 0x15,
}

# System Work Modes (from system_settings.md)
SPP_DEFINE_MODE_BT = 0
SPP_DEFINE_MODE_FM = 1
SPP_DEFINE_MODE_LINEIN = 2
SPP_DEFINE_MODE_SD = 3
SPP_DEFINE_MODE_USBHOST = 4
SPP_DEFINE_MODE_RECORD = 5
SPP_DEFINE_MODE_RECORDPLAY = 6
SPP_DEFINE_MODE_UAC = 7
SPP_DEFINE_MODE_PHONE = 8
SPP_DEFINE_MODE_DIVOOM_SHOW = 9
SPP_DEFINE_MODE_ALARM_SET = 10
SPP_DEFINE_MODE_GAME = 11

# Light Modes (from light.md)
DIVOOM_DISP_ENV_MODE = 0
DIVOOM_DISP_LIGHT_MODE = 1
DIVOOM_DISP_DIVOOM_MODE = 2
DIVOOM_DISP_SPECIAL_MODE = 3
DIVOOM_DISP_MUISE_MODE = 4
DIVOOM_DISP_USER_DEFINE_MODE = 5
DIVOOM_DISP_SCORE_MODE = 6

# Tool Types (from tool.md)
DIVOOM_DISP_WATCH_MODE = 0
DIVOOM_DISP_SCORE_MODE = 1
DIVOOM_DISP_NOISE_MODE = 2
DIVOOM_DISP_COUNT_TIME_DOWN = 3

# Time Display Types (from node-divoom-timebox-evo/src/types.ts)
class TimeDisplayType:
    FullScreen = 0
    Rainbow = 1
    WithBox = 2
    AnalogSquare = 3
    FullScreenNegative = 4
    AnalogRound = 5

# Lightning Types (from node-divoom-timebox-evo/src/types.ts)
class LightningType:
    PlainColor = 0
    Love = 1
    Plants = 2
    NoMosquitto = 3
    Sleeping = 4

# Weather Types (from node-divoom-timebox-evo/src/types.ts)
class WeatherType:
    Clear = 1
    CloudySky = 3
    Thunderstorm = 5
    Rain = 6
    Snow = 8
    Fog = 9

# VJ Effect Types (from node-divoom-timebox-evo/src/types.ts)
class VJEffectType:
    Sparkles = 0
    Lava = 1
    VerticalRainbowLines = 2
    Drops = 3
    RainbowSwirl = 4
    CMYFade = 5
    RainbowLava = 6
    PastelPatterns = 7
    CMYWave = 8
    Fire = 9
    Countdown = 10
    PinkBlueFade = 11
    RainbowPolygons = 12
    PinkBlueWave = 13
    RainbowCross = 14
    RainbowShapes = 15

# Export constants similar to TIMEBOX_CONST in Node.js library
TIMEBOX_CONST = {
    "TimeType": TimeDisplayType,
    "LightningType": LightningType,
    "WeatherType": WeatherType,
    "VJEffectType": VJEffectType
}