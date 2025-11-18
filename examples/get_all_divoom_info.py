import asyncio
import logging
import argparse
from divoom_lib.divoom import Divoom

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def get_all_divoom_info(mac_address: str):
    """
    Connects to the Divoom device and fetches all available information.
    """
    # Create a DivoomConfig object with the device's MAC address
    from divoom_lib.models import DivoomConfig
    config = DivoomConfig(mac=mac_address, logger=logger)
    divoom = Divoom(config)
    
    try:
        await divoom.connect()
        logger.info("Connected to Divoom device. Fetching information...")

        # --- System Settings ---
        logger.info("\n--- System Settings ---")
        try:
            logger.info("Setting brightness to 50...")
            await divoom.device.set_brightness(50)
            logger.info("Brightness set to 50.")
        except Exception as e:
            logger.error(f"Error setting brightness: {e}")

        try:
            work_mode = await divoom.device.get_work_mode()
            logger.info(f"Work Mode: {work_mode}")
        except Exception as e:
            logger.error(f"Error getting work mode: {e}")

        try:
            device_temp = await divoom.device.get_device_temp()
            logger.info(f"Device Temperature: {device_temp}")
        except Exception as e:
            logger.error(f"Error getting device temperature: {e}")

        try:
            net_temp_disp = await divoom.device.get_net_temp_disp()
            logger.info(f"Network Temperature Display: {net_temp_disp}")
        except Exception as e:
            logger.error(f"Error getting network temperature display: {e}")

        try:
            device_name = await divoom.device.get_device_name()
            logger.info(f"Device Name: {device_name}")
        except Exception as e:
            logger.error(f"Error getting device name: {e}")

        try:
            low_power_switch = await divoom.device.get_low_power_switch()
            logger.info(f"Low Power Switch: {low_power_switch}")
        except Exception as e:
            logger.error(f"Error getting low power switch: {e}")

        try:
            auto_power_off = await divoom.device.get_auto_power_off()
            logger.info(f"Auto Power Off: {auto_power_off} minutes")
        except Exception as e:
            logger.error(f"Error getting auto power off: {e}")

        try:
            sound_control = await divoom.device.get_sound_control()
            logger.info(f"Sound Control: {sound_control}")
        except Exception as e:
            logger.error(f"Error getting sound control: {e}")

        # --- Music Play ---
        logger.info("\n--- Music Play ---")
        try:
            sd_play_name = await divoom.music.get_sd_play_name()
            logger.info(f"SD Play Name: {sd_play_name}")
        except Exception as e:
            logger.error(f"Error getting SD play name: {e}")

        try:
            sd_music_list_total_num = await divoom.music.get_sd_music_list_total_num()
            logger.info(f"SD Music List Total Num: {sd_music_list_total_num}")
            if sd_music_list_total_num and sd_music_list_total_num > 0:
                sd_music_list = await divoom.music.get_sd_music_list(0, min(4, sd_music_list_total_num - 1))
                logger.info(f"SD Music List (first 5): {sd_music_list}")
        except Exception as e:
            logger.error(f"Error getting SD music list: {e}")

        try:
            volume = await divoom.music.get_volume()
            logger.info(f"Volume: {volume}")
        except Exception as e:
            logger.error(f"Error getting volume: {e}")

        try:
            play_status = await divoom.music.get_play_status()
            logger.info(f"Play Status: {play_status}")
        except Exception as e:
            logger.error(f"Error getting play status: {e}")

        try:
            sd_music_info = await divoom.music.get_sd_music_info()
            logger.info(f"SD Music Info: {sd_music_info}")
        except Exception as e:
            logger.error(f"Error getting SD music info: {e}")

        # --- Alarm Memorial ---
        logger.info("\n--- Alarm Memorial ---")
        try:
            alarm_time = await divoom.alarm.get_alarm_time()
            logger.info(f"Alarm Time: {alarm_time}")
        except Exception as e:
            logger.error(f"Error getting alarm time: {e}")

        try:
            memorial_time = await divoom.alarm.get_memorial_time()
            logger.info(f"Memorial Time: {memorial_time}")
        except Exception as e:
            logger.error(f"Error getting memorial time: {e}")

        # --- Tool ---
        logger.info("\n--- Tool Information ---")
        try:
            timer_info = await divoom.timer.get_tool_info(0)
            logger.info(f"Timer Info (mode 0): {timer_info}")
        except Exception as e:
            logger.error(f"Error getting timer info: {e}")
        try:
            score_info = await divoom.scoreboard.get_tool_info(1)
            logger.info(f"Score Info (mode 1): {score_info}")
        except Exception as e:
            logger.error(f"Error getting score info: {e}")
        try:
            noise_info = await divoom.noise.get_tool_info(2)
            logger.info(f"Noise Info (mode 2): {noise_info}")
        except Exception as e:
            logger.error(f"Error getting noise info: {e}")
        try:
            countdown_info = await divoom.countdown.get_tool_info(3)
            logger.info(f"Countdown Info (mode 3): {countdown_info}")
        except Exception as e:
            logger.error(f"Error getting countdown info: {e}")

        # --- Sleep ---
        logger.info("\n--- Sleep Settings ---")
        try:
            sleep_scene = await divoom.sleep.get_sleep_scene()
            logger.info(f"Sleep Scene: {sleep_scene}")
        except Exception as e:
            logger.error(f"Error getting sleep scene: {e}")

        # --- Light ---
        logger.info("\n--- Light Settings ---")
        try:
            light_mode = await divoom.light.get_light_mode()
            logger.info(f"Light Mode: {light_mode}")
        except Exception as e:
            logger.error(f"Error getting light mode: {e}")

        try:
            user_define_info = await divoom.light.app_get_user_define_info(0)
            logger.info(f"App Get User Define Info: {user_define_info}")
        except Exception as e:
            logger.error(f"Error getting user define info: {e}")

    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        if divoom.is_connected:
            await divoom.disconnect()

async def main():
    parser = argparse.ArgumentParser(description="Get all information from a Divoom device.")
    parser.add_argument("mac_address", help="MAC address of the Divoom device")
    args = parser.parse_args()
    await get_all_divoom_info(args.mac_address)

if __name__ == "__main__":
    asyncio.run(main())
