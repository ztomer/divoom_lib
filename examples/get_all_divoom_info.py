import asyncio
import logging
from divoom_protocol import Divoom

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def get_all_divoom_info(
    mac_address: str,
    write_characteristic_uuid: str,
    notify_characteristic_uuid: str,
    read_characteristic_uuid: str
):
    """
    Connects to the Divoom device and fetches all available information.
    """
    divoom = Divoom(
        mac=mac_address,
        logger=logger,
        use_ios_le_protocol=True,
        write_characteristic_uuid=write_characteristic_uuid,
        notify_characteristic_uuid=notify_characteristic_uuid,
        read_characteristic_uuid=read_characteristic_uuid
    )
    await divoom.connect()
    logger.info("Connected to Divoom device. Fetching information...")

    try:
        # --- System Settings ---
        logger.info("\n--- System Settings ---")
        logger.info("Setting brightness to 50...")
        await divoom.system.send_brightness(50)
        logger.info("Brightness set to 50.")

        # # --- Music Play ---
        # logger.info("\n--- Music Play ---")
        # sd_play_name = await divoom.music.get_sd_play_name()
        # logger.info(f"SD Play Name (0x06): {sd_play_name}")

        # # Note: get_sd_music_list requires start_id and end_id, so we'll fetch total num first
        # sd_music_list_total_num = await divoom.get_sd_music_list_total_num()
        # logger.info(f"SD Music List Total Num (0x7d): {sd_music_list_total_num}")
        # if sd_music_list_total_num and sd_music_list_total_num > 0:
        #     # Fetching first 5 songs as an example
        #     sd_music_list = await divoom.get_sd_music_list(0, min(4, sd_music_list_total_num - 1))
        #     logger.info(f"SD Music List (first 5) (0x07): {sd_music_list}")

        # volume = await divoom.get_volume()
        # logger.info(f"Volume (0x09): {volume}")

        # play_status = await divoom.get_play_status()
        # logger.info(f"Play Status (0x0b): {play_status}")

        # sd_music_info = await divoom.get_sd_music_info()
        # logger.info(f"SD Music Info (0xb4): {sd_music_info}")

        # # --- Alarm Memorial ---
        # logger.info("\n--- Alarm Memorial ---")
        # alarm_time = await divoom.get_alarm_time()
        # logger.info(f"Alarm Time (0x42): {alarm_time}")

        # memorial_time = await divoom.get_memorial_time()
        # logger.info(f"Memorial Time (0x53): {memorial_time}")

        # # --- Tool ---
        # logger.info("\n--- Tool Information ---")
        # # Example for Timer (0)
        # timer_info = await divoom.get_tool_info(0)
        # logger.info(f"Timer Info (0x71, mode 0): {timer_info}")
        # # Example for Score (1)
        # score_info = await divoom.get_tool_info(1)
        # logger.info(f"Score Info (0x71, mode 1): {score_info}")
        # # Example for Noise (2)
        # noise_info = await divoom.get_tool_info(2)
        # logger.info(f"Noise Info (0x71, mode 2): {noise_info}")
        # # Example for Countdown (3)
        # countdown_info = await divoom.get_tool_info(3)
        # logger.info(f"Countdown Info (0x71, mode 3): {countdown_info}")

        # # --- Sleep ---
        # logger.info("\n--- Sleep Settings ---")
        # sleep_scene = await divoom.get_sleep_scene()
        # logger.info(f"Sleep Scene (0xa2): {sleep_scene}")

        # # --- Light ---
        # logger.info("\n--- Light Settings ---")
        # light_mode = await divoom.get_light_mode()
        # logger.info(f"Light Mode (0x46): {light_mode}")

        # user_define_info = await divoom.app_get_user_define_info(0)  # Example for user_index 0
        # logger.info(f"App Get User Define Info (0x8e): {user_define_info}")


    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        await divoom.disconnect()
