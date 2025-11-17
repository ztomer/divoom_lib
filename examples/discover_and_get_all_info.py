import asyncio
import logging
from divoom_lib.divoom import Divoom
from divoom_lib.utils.discovery import discover_device

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
    try:
        work_mode = await divoom.system.get_work_mode()
        logger.info(f"Work Mode (0x13): {work_mode}")
    except Exception as e:
        logger.error(f"Error getting work mode: {e}")

    try:
        device_temp = await divoom.system.get_device_temp()
        logger.info(f"Device Temperature (0x59): {device_temp}")
    except Exception as e:
        logger.error(f"Error getting device temperature: {e}")

    try:
        net_temp_disp = await divoom.system.get_net_temp_disp()
        logger.info(f"Network Temperature Display (0x73): {net_temp_disp}")
    except Exception as e:
        logger.error(f"Error getting network temperature display: {e}")

    try:
        device_name = await divoom.system.get_device_name()
        logger.info(f"Device Name (0x76): {device_name}")
    except Exception as e:
        logger.error(f"Error getting device name: {e}")

    try:
        low_power_switch = await divoom.system.get_low_power_switch()
        logger.info(f"Low Power Switch (0xb3): {low_power_switch}")
    except Exception as e:
        logger.error(f"Error getting low power switch: {e}")

    try:
        auto_power_off = await divoom.system.get_auto_power_off()
        logger.info(f"Auto Power Off (0xac): {auto_power_off} minutes")
    except Exception as e:
        logger.error(f"Error getting auto power off: {e}")

    try:
        sound_control = await divoom.system.get_sound_control()
        logger.info(f"Sound Control (0xa8): {sound_control}")
    except Exception as e:
        logger.error(f"Error getting sound control: {e}")

    # --- Music Play ---
    logger.info("\n--- Music Play ---")
    try:
        sd_play_name = await divoom.music.get_sd_play_name()
        logger.info(f"SD Play Name (0x06): {sd_play_name}")
    except Exception as e:
        logger.error(f"Error getting SD play name: {e}")

    try:
        sd_music_list_total_num = await divoom.music.get_sd_music_list_total_num()
        logger.info(f"SD Music List Total Num (0x7d): {sd_music_list_total_num}")
        if sd_music_list_total_num and sd_music_list_total_num > 0:
            sd_music_list = await divoom.music.get_sd_music_list(0, min(4, sd_music_list_total_num - 1))
            logger.info(f"SD Music List (first 5) (0x07): {sd_music_list}")
    except Exception as e:
        logger.error(f"Error getting SD music list: {e}")

    try:
        volume = await divoom.music.get_volume()
        logger.info(f"Volume (0x09): {volume}")
    except Exception as e:
        logger.error(f"Error getting volume: {e}")

    try:
        play_status = await divoom.music.get_play_status()
        logger.info(f"Play Status (0x0b): {play_status}")
    except Exception as e:
        logger.error(f"Error getting play status: {e}")

    try:
        sd_music_info = await divoom.music.get_sd_music_info()
        logger.info(f"SD Music Info (0xb4): {sd_music_info}")
    except Exception as e:
        logger.error(f"Error getting SD music info: {e}")

    # --- Alarm Memorial ---
    logger.info("\n--- Alarm Memorial ---")
    try:
        alarm_time = await divoom.alarm.get_alarm_time()
        logger.info(f"Alarm Time (0x42): {alarm_time}")
    except Exception as e:
        logger.error(f"Error getting alarm time: {e}")

    try:
        memorial_time = await divoom.alarm.get_memorial_time()
        logger.info(f"Memorial Time (0x53): {memorial_time}")
    except Exception as e:
        logger.error(f"Error getting memorial time: {e}")

    # --- Tool ---
    logger.info("\n--- Tool Information ---")
    try:
        timer_info = await divoom.tool.get_tool_info(0)
        logger.info(f"Timer Info (0x71, mode 0): {timer_info}")
    except Exception as e:
        logger.error(f"Error getting timer info: {e}")
    try:
        score_info = await divoom.tool.get_tool_info(1)
        logger.info(f"Score Info (0x71, mode 1): {score_info}")
    except Exception as e:
        logger.error(f"Error getting score info: {e}")
    try:
        noise_info = await divoom.tool.get_tool_info(2)
        logger.info(f"Noise Info (0x71, mode 2): {noise_info}")
    except Exception as e:
        logger.error(f"Error getting noise info: {e}")
    try:
        countdown_info = await divoom.tool.get_tool_info(3)
        logger.info(f"Countdown Info (0x71, mode 3): {countdown_info}")
    except Exception as e:
        logger.error(f"Error getting countdown info: {e}")

    # --- Sleep ---
    logger.info("\n--- Sleep Settings ---")
    try:
        sleep_scene = await divoom.sleep.get_sleep_scene()
        logger.info(f"Sleep Scene (0xa2): {sleep_scene}")
    except Exception as e:
        logger.error(f"Error getting sleep scene: {e}")

    # --- Light ---
    logger.info("\n--- Light Settings ---")
    try:
        light_mode = await divoom.light.get_light_mode()
        logger.info(f"Light Mode (0x46): {light_mode}")
    except Exception as e:
        logger.error(f"Error getting light mode: {e}")

    try:
        user_define_info = await divoom.light.app_get_user_define_info(0)
        logger.info(f"App Get User Define Info (0x8e): {user_define_info}")
    except Exception as e:
        logger.error(f"Error getting user define info: {e}")


async def discover_and_get_info():
    print_info("Scanning for Divoom devices...")
    device, device_id = await discover_device(logger=logger)
    
    if not device:
        print_info("No Divoom devices found.")
        return

    print_info(f"\nConnecting to {device.name} ({device.address})...")

    divoom = Divoom(mac=device.address, logger=logger)
    
    try:
        await divoom.protocol.connect()
        print_ok(f"Connected to {device.name}.")
        await get_all_divoom_info_logic(divoom)
    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        if divoom.protocol.is_connected:
            await divoom.protocol.disconnect()
            print_info(f"Disconnected from {device.name}.")

if __name__ == "__main__":
    asyncio.run(discover_and_get_info())
