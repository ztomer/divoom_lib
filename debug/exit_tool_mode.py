import asyncio
import logging
import os
import sys

# Add the project root to sys.path to allow importing divoom_api
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from divoom_lib import Divoom
from divoom_lib.utils.discovery import discover_device
from divoom_lib import constants

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("exit_tool_mode")

async def exit_tool_mode():
    divoom = None
    try:
        # Discover the device
        ble_device, device_id = await discover_device(name_substring="Timoo")
        if not ble_device:
            logger.error("No Divoom device found.")
            return
        
        logger.info(f"Found device: {device_id}")

        # Initialize Divoom controller
        divoom = Divoom(mac=device_id, logger=logger)
        await divoom.connect()
        logger.info(f"Successfully connected to {divoom.mac}!")

        # Attempt to cancel any active countdown
        logger.info("Attempting to cancel any active countdown...")
        result_countdown = await divoom.tool.set_tool_info(
            constants.TOOL_TYPE_COUNTDOWN,
            ctrl_flag=constants.STI_CTRL_FLAG_COUNTDOWN_CANCEL,
            minutes=0,
            seconds=0
        )
        if result_countdown:
            logger.info("Successfully sent command to cancel countdown.")
        else:
            logger.warning("Failed to send command to cancel countdown.")

        # Attempt to reset any active timer
        logger.info("Attempting to reset any active timer...")
        result_timer = await divoom.tool.set_tool_info(
            constants.TOOL_TYPE_TIMER,
            ctrl_flag=constants.STI_CTRL_FLAG_TIMER_RESET
        )
        if result_timer:
            logger.info("Successfully sent command to reset timer.")
        else:
            logger.warning("Failed to send command to reset timer.")

        # Attempt to exit Score function (as it has an explicit 'exit' flag)
        logger.info("Attempting to exit Score function (TOOL_TYPE_SCORE) by setting on_off=0...")
        result_score_exit = await divoom.tool.set_tool_info(
            constants.TOOL_TYPE_SCORE,
            on_off=0 # 0 for Exit, 1 for Start
        )
        if result_score_exit:
            logger.info("Successfully sent command to exit Score function.")
        else:
            logger.warning("Failed to send command to exit Score function.")

        # Try setting work mode to a general display mode (DIVOOM_SHOW)
        logger.info("Attempting to set work mode to DIVOOM_SHOW (general display mode)...")
        result_work_mode = await divoom.system.set_work_mode(constants.SPP_DEFINE_MODE_DIVOOM_SHOW)
        if result_work_mode:
            logger.info("Successfully sent command to set work mode to DIVOOM_SHOW.")
        else:
            logger.warning("Failed to send command to set work mode to DIVOOM_SHOW.")

        # Also try switching to a default channel like Time to ensure exit
        logger.info("Switching to Time channel to ensure exit from tool mode...")
        await divoom.system.set_channel(constants.CHANNEL_ID_TIME)
        logger.info("Switched to Time channel.")

    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        if divoom and divoom.is_connected:
            await divoom.disconnect()
            logger.info("Disconnected from Divoom device.")

if __name__ == '__main__':
    asyncio.run(exit_tool_mode())