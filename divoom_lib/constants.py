# divoom_api/constants.py

# COMMAND CODES
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
    "set channel light": 0x45,
    "get light mode": 0x46,
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
    "get sd music list": 0x07,
    "get volume": 0x09,
    "get play status": 0x0b,
    "set sd play music id": 0x11,
    "set sd last next": 0x12,
    "send sd list over": 0x14,
    "send sd status": 0x15,
    "get work mode": 0x06,
}

# PAYLOAD VALUES
PAYLOAD_START_BYTE_COLOR_MODE = 0x01
PAYLOAD_COLOR_MODE_UNKNOWN_BYTE_1 = 0x00
PAYLOAD_COLOR_MODE_UNKNOWN_BYTE_2 = 0x01
CHANNEL_ID_2 = 0x02
WORK_MODE_CHANNEL_9 = 0x09

# GENERAL CONSTANTS
BOOLEAN_TRUE = 0x01
BOOLEAN_FALSE = 0x00
FIXED_STRING_BYTE = 0x00

# Commands that might be acknowledged by a generic 0x33 response
GENERIC_ACK_COMMANDS = [
    COMMANDS["set light mode"],
    COMMANDS["set work mode"],
    COMMANDS["set poweron channel"],
    COMMANDS["get light mode"], # Device responds with 0x46 to 0x45 commands
]

# WORK MODES (from display.py)
WORK_MODE_DESIGN = 0x05
WORK_MODE_EFFECTS = 0x04
WORK_MODE_VISUALIZATION = 0x04 # Same as effects, but explicit for context

# SUB-COMMANDS
SUB_COMMAND_SET_DESIGN = 0x17

# LIGHTNING CONSTANTS (from display.py)
LIGHTNING_CHANNEL_NUMBER = 0x01
LIGHTNING_TYPE_PLAIN_COLOR = 0x00

# LIGHT PHONE WORD ATTRIBUTE CONTROL WORDS (from light.py)
LPWA_CONTROL_SPEED = 1
LPWA_CONTROL_EFFECTS = 2
LPWA_CONTROL_DISPLAY_BOX = 3
LPWA_CONTROL_FONT = 4
LPWA_CONTROL_COLOR = 5
LPWA_CONTROL_CONTENT = 6
LPWA_CONTROL_IMAGE_EFFECTS = 7

# APP NEW SEND GIF COMMAND CONTROL WORDS (from light.py)
ANSGC_CONTROL_START_SENDING = 0
ANSGC_CONTROL_SENDING_DATA = 1
ANSGC_CONTROL_TERMINATE_SENDING = 2

# SET USER GIF CONTROL WORDS (from light.py)
SUG_CONTROL_START_SAVING = 0
SUG_CONTROL_TRANSMIT_DATA = 1
SUG_CONTROL_TRANSMISSION_END = 2
SUG_DATA_NORMAL_IMAGE = 0
SUG_DATA_LED_EDITOR = 1
SUG_DATA_SAND_PAINTING = 2
SUG_DATA_SCROLL_ANIMATION = 3

# MODIFY USER GIF ITEMS DATA VALUES (from light.py)
MUGI_DATA_GET_COUNT = 0xFF

# APP NEW USER DEFINE CONTROL WORDS (from light.py)
ANUD_CONTROL_START_SENDING = 0
ANUD_CONTROL_SENDING_DATA = 1
ANUD_CONTROL_TERMINATE_SENDING = 2

# APP BIG64 USER DEFINE CONTROL WORDS (from light.py)
ABUD_CONTROL_START_SENDING = 0
ABUD_CONTROL_SENDING_DATA = 1
ABUD_CONTROL_TERMINATE_SENDING = 2
ABUD_CONTROL_DELETE = 3
ABUD_CONTROL_PLAY_ARTWORK = 4
ABUD_CONTROL_DELETE_ALL_BY_INDEX = 5

# DRAWING CONTROL MOVIE PLAY CONTROL WORDS (from light.py)
DCMP_CONTROL_EXIT_MOVIE_MODE = 0
DCMP_CONTROL_START_MOVIE_PLAYBACK = 1

# SAND PAINT CONTROL WORDS (from light.py)
SPC_CONTROL_INITIALIZE = 0
SPC_CONTROL_RESET = 1

# PIC SCAN CONTROL WORDS (from light.py)
PSC_CONTROL_SET_SCROLLING_MODE_SPEED = 0
PSC_CONTROL_SENDING_IMAGE_DATA = 1

# GET LIGHT MODE RESPONSE INDICES (from light.py)
GLM_CURRENT_LIGHT_EFFECT_MODE = 0
GLM_TEMPERATURE_DISPLAY_MODE = 1
GLM_VJ_SELECTION_OPTION = 2
GLM_RGB_COLOR_VALUES_START = 3
GLM_BRIGHTNESS_LEVEL = 6
GLM_LIGHTING_MODE_SELECTION_OPTION = 7
GLM_ON_OFF_SWITCH = 8
GLM_MUSIC_MODE_SELECTION_OPTION = 9
GLM_SYSTEM_BRIGHTNESS = 10
GLM_TIME_DISPLAY_FORMAT_SELECTION_OPTION = 11
GLM_TIME_DISPLAY_RGB_COLOR_VALUES_START = 12
GLM_TIME_DISPLAY_MODE = 15
GLM_TIME_CHECKBOX_MODES_START = 16

# APP GET USER DEFINE INFO RESPONSE CONTROL WORDS (from light.py)
AGUDI_CONTROL_WORD_SUCCESS = 1
AGUDI_CONTROL_WORD_FAILURE = 2

# SYSTEM CHANNEL IDS (from system.py)
CHANNEL_ID_TIME = 0x00
CHANNEL_ID_LIGHTNING = 0x01
CHANNEL_ID_CLOUD = 0x02
CHANNEL_ID_VJ_EFFECTS = 0x03
CHANNEL_ID_VISUALIZATION = 0x04
CHANNEL_ID_ANIMATION = 0x05
CHANNEL_ID_SCOREBOARD = 0x06
CHANNEL_ID_MIN = 0x00
CHANNEL_ID_MAX = 0x06

# SD STATUS (from system.py)
SD_STATUS_REMOVAL = 0
SD_STATUS_INSERTION = 1

# BOOT GIF ON/OFF (from system.py)
BOOT_GIF_OFF = 0
BOOT_GIF_ON = 1

# DEVICE TEMPERATURE FORMAT (from system.py)
TEMP_FORMAT_CELSIUS = 0
TEMP_FORMAT_FAHRENHEIT = 1

# LOW POWER SWITCH ON/OFF (from system.py)
LOW_POWER_SWITCH_OFF = 0
LOW_POWER_SWITCH_ON = 1

# HOUR TYPE (from system.py)
HOUR_TYPE_12 = 0
HOUR_TYPE_24 = 1
HOUR_TYPE_QUERY = 0xFF

# SONG DISPLAY CONTROL (from system.py)
SONG_DISPLAY_OFF = 0
SONG_DISPLAY_ON = 1
SONG_DISPLAY_QUERY = 0xFF

# BLUETOOTH PASSWORD CONTROL (from system.py)
BT_PASSWORD_CANCEL = 0
BT_PASSWORD_SET = 1
BT_PASSWORD_GET_STATUS = 2

# POWER-ON VOICE VOLUME CONTROL (from system.py)
POVVC_GET = 0
POVVC_SET = 1

# POWER-ON CHANNEL CONTROL (from system.py)
POCC_GET = 0
POCC_SET = 1
POCC_CHANNEL_MIN = 0
POCC_CHANNEL_MAX = 5

# SOUND CONTROL ENABLE (from system.py)
SOUND_CONTROL_DISABLE = 0
SOUND_CONTROL_ENABLE = 1

# GET DEVICE TEMP RESPONSE INDICES (from system.py)
GDT_TEMP_FORMAT = 0
GDT_TEMP_VALUE = 1

# GET NET TEMP DISP RESPONSE INDICES (from system.py)
GNTD_DISPLAY_MODES_START = 0
GNTD_TIME_MINUTES_START = 5

# GET DEVICE NAME RESPONSE INDICES (from system.py)
GDN_NAME_LENGTH = 0
GDN_NAME_BYTES_START = 1

# ALARM AND MEMORIAL CONSTANTS (from alarm.py)
ALARM_COUNT = 10
MEMORIAL_COUNT = 10

# GET ALARM TIME RESPONSE STRUCTURE (from alarm.py)
GAT_ALARM_INFO_LENGTH = 9
GAT_STATUS = 0
GAT_HOUR = 1
GAT_MINUTE = 2
GAT_WEEK = 3
GAT_MODE = 4
GAT_TRIGGER_MODE = 5
GAT_FM_FREQ_START = 6
GAT_VOLUME = 8

# GET MEMORIAL TIME RESPONSE STRUCTURE (from alarm.py)
GMT_MEMORIAL_INFO_LENGTH = 39
GMT_DIALY_ID = 0
GMT_ON_OFF = 1
GMT_MONTH = 2
GMT_DAY = 3
GMT_HOUR = 4
GMT_MINUTE = 5
GMT_HAVE_FLAG = 6
GMT_TITLE_NAME_START = 7
GMT_TITLE_NAME_END = 39

# GAME CONSTANTS (from game.py)
SHOW_GAME_OFF = 0x00
SHOW_GAME_ON = 0x01

GAME_CONTROL_GO = 0
GAME_CONTROL_LEFT = 1
GAME_CONTROL_RIGHT = 2
GAME_CONTROL_UP = 3
GAME_CONTROL_DOWN = 4
GAME_CONTROL_OK = 5

GAME_CONTROL_MAP = {
    "go": GAME_CONTROL_GO,
    "ok": GAME_CONTROL_OK,
    "left": GAME_CONTROL_LEFT,
    "right": GAME_CONTROL_RIGHT,
    "up": GAME_CONTROL_UP,
    "down": GAME_CONTROL_DOWN,
}

# MUSIC CONSTANTS (from music.py)
# Get SD Play Name Response Indices
GSPN_NAME_LENGTH_START = 0
GSPN_NAME_BYTES_START = 2

# Get SD Music List Response Structure
GSML_MUSIC_ID_LENGTH = 2
GSML_NAME_LENGTH_LENGTH = 2

# Get Volume Response Indices
GV_VOLUME = 0

# Get Play Status Response Indices
GPS_STATUS = 0

# Set SD Last Next Action Values
SDLN_PREVIOUS = 0
SDLN_NEXT = 1

# Get SD Music List Total Num Response Indices
GSMLTN_TOTAL_NUM_START = 0

# Get SD Music Info Response Structure
GSMI_CURRENT_TIME_START = 0
GSMI_TOTAL_TIME_START = 2
GSMI_MUSIC_ID_START = 4
GSMI_STATUS = 6
GSMI_VOLUME = 7
GSMI_PLAY_MODE = 8

# Set SD Music Play Mode Values
SMPM_LIST_LOOP = 1
SMPM_SINGLE_LOOP = 2
SMPM_RANDOM_PLAY = 3

# SLEEP CONSTANTS (from sleep.py)
SHOW_SLEEP_DEFAULT_SLEEPTIME = 120
SHOW_SLEEP_DEFAULT_SLEEPMODE = 0
SHOW_SLEEP_DEFAULT_VOLUME = 100
SHOW_SLEEP_DEFAULT_BRIGHTNESS = 100
SHOW_SLEEP_DEFAULT_ON = 1
SHOW_SLEEP_DEFAULT_COLOR_RGB = [0x00, 0x00, 0x00]

# Get Sleep Scene Response Structure (from sleep.py)
GSS_RESPONSE_LENGTH = 10
GSS_TIME = 0
GSS_MODE = 1
GSS_ON = 2
GSS_FM_FREQ_START = 3
GSS_VOLUME = 5
GSS_COLOR_R = 6
GSS_COLOR_G = 7
GSS_COLOR_B = 8
GSS_LIGHT = 9

# Set Sleep Color Constants (from sleep.py)
SET_SLEEP_COLOR_RGB_LENGTH = 3

# DIVOOM BASE CONSTANTS (from base.py)
DEFAULT_DEVICE_TYPE = "Ditoo"
DEFAULT_SCREEN_SIZE = 16
DEFAULT_CHUNK_SIZE = 200
DEFAULT_MAX_RECONNECT_ATTEMPTS = 5
DEFAULT_RECONNECT_DELAY = 0.5
DEFAULT_SPP_CHARACTERISTIC_UUID = "49535343-6daa-4d02-abf6-19569aca69fe"

# NOTIFICATION HANDLER CONSTANTS (from base.py)
# iOS LE Protocol
IOS_LE_MIN_DATA_LENGTH = 13
IOS_LE_HEADER = [0xFE, 0xEF, 0xAA, 0x55]
IOS_LE_DATA_LENGTH_START = 4
IOS_LE_DATA_LENGTH_END = 6
IOS_LE_COMMAND_IDENTIFIER = 6
IOS_LE_PACKET_NUMBER_START = 7
IOS_LE_PACKET_NUMBER_END = 11
IOS_LE_CHECKSUM_LENGTH = 2
IOS_LE_DATA_OFFSET = 11

# Basic Protocol
BASIC_PROTOCOL_MIN_DATA_LENGTH = 6
BASIC_PROTOCOL_START_BYTE = 0x01
BASIC_PROTOCOL_END_BYTE = 0x02
BASIC_PROTOCOL_LENGTH_START = 1
BASIC_PROTOCOL_LENGTH_END = 3
BASIC_PROTOCOL_PAYLOAD_OFFSET = 3
BASIC_PROTOCOL_CHECKSUM_OFFSET = -3
BASIC_PROTOCOL_CHECKSUM_LENGTH = 2

# ACK-like patterns
ACK_PATTERN_BYTE_1 = 0x04
ACK_PATTERN_BYTE_3 = 0x55

# Escape Payload Constants (from base.py)
ESCAPE_BYTE_1 = 0x01
ESCAPE_BYTE_2 = 0x02
ESCAPE_BYTE_3 = 0x03
ESCAPE_SEQUENCE_1 = [0x03, 0x04]
ESCAPE_SEQUENCE_2 = [0x03, 0x05]
ESCAPE_SEQUENCE_3 = [0x03, 0x06]

# Make Message Constants (from base.py)
MESSAGE_CHECKSUM_LENGTH = 2
MESSAGE_START_BYTE = 0x01
MESSAGE_END_BYTE = 0x02

# Make Message iOS LE Constants (from base.py)
IOS_LE_MESSAGE_HEADER = [0xFE, 0xEF, 0xAA, 0x55]
IOS_LE_MESSAGE_CMD_ID_LENGTH = 1
IOS_LE_MESSAGE_PACKET_NUM_LENGTH = 4
IOS_LE_MESSAGE_CHECKSUM_LENGTH = 2

# TOOL CONSTANTS (from tool.py)
# Tool Types
TOOL_TYPE_TIMER = 0
TOOL_TYPE_SCORE = 1
TOOL_TYPE_NOISE = 2
TOOL_TYPE_COUNTDOWN = 3
TOOL_TYPE_NOT_IN_GAME_MODE = 0xFF

# Get Tool Info Response Parsing - Timer
GTI_TIMER_STATUS = 0
GTI_TIMER_STATUS_PAUSED = 0
GTI_TIMER_STATUS_STARTED = 1
GTI_TIMER_STATUS_RESET = 2
GTI_TIMER_STATUS_ENTERING_STOPWATCH = 3

# Get Tool Info Response Parsing - Score
GTI_SCORE_ON_OFF = 0
GTI_SCORE_RED_SCORE_START = 1
GTI_SCORE_RED_SCORE_LENGTH = 2
GTI_SCORE_BLUE_SCORE_START = 3
GTI_SCORE_BLUE_SCORE_LENGTH = 2

# Get Tool Info Response Parsing - Noise
GTI_NOISE_STATUS = 0
GTI_NOISE_STATUS_START = 1
GTI_NOISE_STATUS_STOP = 2

# Get Tool Info Response Parsing - Countdown
GTI_COUNTDOWN_STATUS = 0
GTI_COUNTDOWN_STATUS_START = 0
GTI_COUNTDOWN_STATUS_CANCEL = 1
GTI_COUNTDOWN_MINUTES = 1
GTI_COUNTDOWN_SECONDS = 2

# Set Tool Info Control Flags
STI_CTRL_FLAG_TIMER_PAUSED = 0
STI_CTRL_FLAG_TIMER_STARTED = 1
STI_CTRL_FLAG_TIMER_RESET = 2
STI_CTRL_FLAG_TIMER_ENTERING_STOPWATCH = 3

STI_CTRL_FLAG_NOISE_START = 1
STI_CTRL_FLAG_NOISE_STOP = 2

STI_CTRL_FLAG_COUNTDOWN_START = 0
STI_CTRL_FLAG_COUNTDOWN_CANCEL = 1

# Set Tool Info Score On/Off
STI_SCORE_OFF = 0
STI_SCORE_ON = 1

# TIMEPLAN CONSTANTS (from timeplan.py)
# Set Time Manage Info Parameter Offsets and Lengths
STMI_STATUS = 0
STMI_HOUR = 1
STMI_MINUTE = 2
STMI_WEEK = 3
STMI_MODE = 4
STMI_TRIGGER_MODE = 5
STMI_FM_FREQ_START = 6
STMI_FM_FREQ_LENGTH = 2
STMI_VOLUME = 8
STMI_TYPE = 9
STMI_ANIMATION_ID = 10
STMI_ANIMATION_SPEED = 11
STMI_ANIMATION_DIRECTION = 12
STMI_ANIMATION_FRAME_COUNT = 13
STMI_ANIMATION_FRAME_DELAY = 14
STMI_ANIMATION_FRAME_DATA_START = 15

# Set Time Manage Info Type Values
STMI_TYPE_0 = 0
STMI_TYPE_1 = 1

# Set Time Manage Control Parameter Values
STMC_STATUS = 0
STMC_INDEX = 1

# SYSTEM WORK MODES (from system_settings.md)
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

# LIGHT MODES (from light.md)
DIVOOM_DISP_ENV_MODE = 0
DIVOOM_DISP_LIGHT_MODE = 1
DIVOOM_DISP_DIVOOM_MODE = 2
DIVOOM_DISP_SPECIAL_MODE = 3
DIVOOM_DISP_MUISE_MODE = 4
DIVOOM_DISP_USER_DEFINE_MODE = 5
DIVOOM_DISP_SCORE_MODE = 6

# TOOL TYPES (from tool.md)
DIVOOM_DISP_WATCH_MODE = 0
DIVOOM_DISP_SCORE_MODE = 1
DIVOOM_DISP_NOISE_MODE = 2
DIVOOM_DISP_COUNT_TIME_DOWN = 3

# TIME DISPLAY TYPES (from node-divoom-timebox-evo/src/types.ts)
class TimeDisplayType:
    FullScreen = 0
    Rainbow = 1
    WithBox = 2
    AnalogSquare = 3
    FullScreenNegative = 4
    AnalogRound = 5

# LIGHTNING TYPES (from node-divoom-timebox-evo/src/types.ts)
class LightningType:
    PlainColor = 0
    Love = 1
    Plants = 2
    NoMosquitto = 3
    Sleeping = 4

# WEATHER TYPES (from node-divoom-timebox-evo/src/types.ts)
class WeatherType:
    Clear = 1
    CloudySky = 3
    Thunderstorm = 5
    Rain = 6
    Snow = 8
    Fog = 9

# VJ EFFECT TYPES (from node-divoom-timebox-evo/src/types.ts)
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