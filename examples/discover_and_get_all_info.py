import asyncio
import logging
from divoom_lib import Divoom
from divoom_lib.utils.discovery import discover_divoom_devices

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def print_info(message):
    """Prints an informational message."""
    logger.info(f"[ ==> ] {message}")

def print_ok(message):
    """Prints a success message."""
    logger.info(f"[ Ok  ] {message}")

async def get_all_divoom_info_logic(divoom: Divoom):
    """
    Fetches all available information from the Divoom device using the provided protocol instance.
    """
    logger.info("Fetching information...")

    # --- System Settings ---
    logger.info("\n--- System Settings ---")
    work_mode = await divoom.system.get_work_mode()
    logger.info(f"Work Mode (0x13): {work_mode}")

    device_temp = await divoom.system.get_device_temp()
    logger.info(f"Device Temperature (0x59): {device_temp}")

    net_temp_disp = await divoom.system.get_net_temp_disp()
    logger.info(f"Network Temperature Display (0x73): {net_temp_disp}")

    device_name = await divoom.system.get_device_name()
    logger.info(f"Device Name (0x76): {device_name}")

    low_power_switch = await divoom.system.get_low_power_switch()
    logger.info(f"Low Power Switch (0xb3): {low_power_switch}")

    auto_power_off = await divoom.system.get_auto_power_off()
    logger.info(f"Auto Power Off (0xac): {auto_power_off} minutes")

    sound_control = await divoom.system.get_sound_control()
    logger.info(f"Sound Control (0xa8): {sound_control}")

    # --- Music Play ---
    logger.info("\n--- Music Play ---")
    sd_play_name = await divoom.music.get_sd_play_name()
    logger.info(f"SD Play Name (0x06): {sd_play_name}")

    sd_music_list_total_num = await divoom.music.get_sd_music_list_total_num()
    logger.info(f"SD Music List Total Num (0x7d): {sd_music_list_total_num}")
    if sd_music_list_total_num and sd_music_list_total_num > 0:
        sd_music_list = await divoom.music.get_sd_music_list(0, min(4, sd_music_list_total_num - 1))
        logger.info(f"SD Music List (first 5) (0x07): {sd_music_list}")

    volume = await divoom.music.get_volume()
    logger.info(f"Volume (0x09): {volume}")

    play_status = await divoom.music.get_play_status()
    logger.info(f"Play Status (0x0b): {play_status}")

    sd_music_info = await divoom.music.get_sd_music_info()
    logger.info(f"SD Music Info (0xb4): {sd_music_info}")

    # --- Alarm Memorial ---
    logger.info("\n--- Alarm Memorial ---")
    alarm_time = await divoom.alarm.get_alarm_time()
    logger.info(f"Alarm Time (0x42): {alarm_time}")

    memorial_time = await divoom.alarm.get_memorial_time()
    logger.info(f"Memorial Time (0x53): {memorial_time}")

    # --- Tool ---
    logger.info("\n--- Tool Information ---")
    timer_info = await divoom.tool.get_tool_info(0)
    logger.info(f"Timer Info (0x71, mode 0): {timer_info}")
    score_info = await divoom.tool.get_tool_info(1)
    logger.info(f"Score Info (0x71, mode 1): {score_info}")
    noise_info = await divoom.tool.get_tool_info(2)
    logger.info(f"Noise Info (0x71, mode 2): {noise_info}")
    countdown_info = await divoom.tool.get_tool_info(3)
    logger.info(f"Countdown Info (0x71, mode 3): {countdown_info}")

    # --- Sleep ---
    logger.info("\n--- Sleep Settings ---")
    sleep_scene = await divoom.sleep.get_sleep_scene()
    logger.info(f"Sleep Scene (0xa2): {sleep_scene}")

    # --- Light ---
    logger.info("\n--- Light Settings ---")
    light_mode = await divoom.light.get_light_mode()
    logger.info(f"Light Mode (0x46): {light_mode}")

    user_define_info = await divoom.light.app_get_user_define_info(0)
    logger.info(f"App Get User Define Info (0x8e): {user_define_info}")


async def discover_and_get_info():
    print_info("Scanning for Divoom devices...")
    devices = await discover_divoom_devices(logger=logger)
    
    if not devices:
        print_info("No Divoom devices found.")
        return

    selected_device = devices[0]
    print_info(f"\nConnecting to {selected_device.name} ({selected_device.address})...")

    divoom = Divoom(mac=selected_device.address, logger=logger)
    
    try:
        await divoom.connect()
        print_ok(f"Connected to {selected_device.name}.")
        await get_all_divoom_info_logic(divoom)
    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        if divoom.is_connected:
            await divoom.disconnect()
            print_info(f"Disconnected from {selected_device.name}.")

if __name__ == "__main__":
    asyncio.run(discover_and_get_info())
