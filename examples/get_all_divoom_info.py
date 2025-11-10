import asyncio
import logging
from divoom_lib import Divoom
from divoom_lib.utils.discovery import discover_divoom_devices

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def get_all_divoom_info(mac_address: str):
    """
    Connects to the Divoom device and fetches all available information.
    """
    divoom = Divoom(mac=mac_address, logger=logger)
    await divoom.connect()
    logger.info("Connected to Divoom device. Fetching information...")

    try:
        # --- System Settings ---
        logger.info("\n--- System Settings ---")
        logger.info("Setting brightness to 50...")
        await divoom.system.set_brightness(50)
        logger.info("Brightness set to 50.")

        work_mode = await divoom.system.get_work_mode()
        logger.info(f"Work Mode: {work_mode}")

        device_temp = await divoom.system.get_device_temp()
        logger.info(f"Device Temperature: {device_temp}")

        net_temp_disp = await divoom.system.get_net_temp_disp()
        logger.info(f"Network Temperature Display: {net_temp_disp}")

        device_name = await divoom.system.get_device_name()
        logger.info(f"Device Name: {device_name}")

        low_power_switch = await divoom.system.get_low_power_switch()
        logger.info(f"Low Power Switch: {low_power_switch}")

        auto_power_off = await divoom.system.get_auto_power_off()
        logger.info(f"Auto Power Off: {auto_power_off} minutes")

        sound_control = await divoom.system.get_sound_control()
        logger.info(f"Sound Control: {sound_control}")

        # --- Music Play ---
        logger.info("\n--- Music Play ---")
        sd_play_name = await divoom.music.get_sd_play_name()
        logger.info(f"SD Play Name: {sd_play_name}")

        sd_music_list_total_num = await divoom.music.get_sd_music_list_total_num()
        logger.info(f"SD Music List Total Num: {sd_music_list_total_num}")
        if sd_music_list_total_num and sd_music_list_total_num > 0:
            sd_music_list = await divoom.music.get_sd_music_list(0, min(4, sd_music_list_total_num - 1))
            logger.info(f"SD Music List (first 5): {sd_music_list}")

        volume = await divoom.music.get_volume()
        logger.info(f"Volume: {volume}")

        play_status = await divoom.music.get_play_status()
        logger.info(f"Play Status: {play_status}")

        sd_music_info = await divoom.music.get_sd_music_info()
        logger.info(f"SD Music Info: {sd_music_info}")

        # --- Alarm Memorial ---
        logger.info("\n--- Alarm Memorial ---")
        alarm_time = await divoom.alarm.get_alarm_time()
        logger.info(f"Alarm Time: {alarm_time}")

        memorial_time = await divoom.alarm.get_memorial_time()
        logger.info(f"Memorial Time: {memorial_time}")

        # --- Tool ---
        logger.info("\n--- Tool Information ---")
        timer_info = await divoom.tool.get_tool_info(0)
        logger.info(f"Timer Info (mode 0): {timer_info}")
        score_info = await divoom.tool.get_tool_info(1)
        logger.info(f"Score Info (mode 1): {score_info}")
        noise_info = await divoom.tool.get_tool_info(2)
        logger.info(f"Noise Info (mode 2): {noise_info}")
        countdown_info = await divoom.tool.get_tool_info(3)
        logger.info(f"Countdown Info (mode 3): {countdown_info}")

        # --- Sleep ---
        logger.info("\n--- Sleep Settings ---")
        sleep_scene = await divoom.sleep.get_sleep_scene()
        logger.info(f"Sleep Scene: {sleep_scene}")

        # --- Light ---
        logger.info("\n--- Light Settings ---")
        light_mode = await divoom.light.get_light_mode()
        logger.info(f"Light Mode: {light_mode}")

        user_define_info = await divoom.light.app_get_user_define_info(0)
        logger.info(f"App Get User Define Info: {user_define_info}")

    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        await divoom.disconnect()

async def main():
    devices = await discover_divoom_devices(logger=logger)
    if not devices:
        logger.warning("No Divoom devices found.")
        return

    device = devices[0]
    await get_all_divoom_info(device.address)

if __name__ == "__main__":
    asyncio.run(main())
