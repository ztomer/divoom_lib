import asyncio
import logging
from divoom_lib import Divoom
from divoom_lib.utils.discovery import discover_divoom_devices

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logging.getLogger("bleak").setLevel(logging.INFO) # Reduce bleak verbosity for cleaner output

async def debug_divoom_getters(device_name: str):
    devices = await discover_divoom_devices(device_name=device_name, logger=logger)
    if not devices:
        logger.error(f"No Divoom devices found with name '{device_name}'.")
        return

    mac_address = devices[0].address
    divoom = Divoom(mac=mac_address, logger=logger)

    try:
        await divoom.connect()
        logger.info("Connected to Divoom device. Fetching information...")

        # --- System Settings ---
        logger.info("\n--- System Settings ---")
        work_mode = await divoom.system.get_work_mode()
        logger.info(f"Work Mode (0x13): {work_mode}")

        device_temp = await divoom.system.get_device_temp()
        logger.info(f"Device Temperature (0x59): {device_temp}")

        net_temp_disp = await divoom.system.get_net_temp_disp()
        logger.info(f"Network Temperature Display (0x73): {net_temp_disp}")

        device_name_from_device = await divoom.system.get_device_name()
        logger.info(f"Device Name (0x76): {device_name_from_device}")

        low_power_switch = await divoom.system.get_low_power_switch()
        logger.info(f"Low Power Switch (0xb3): {low_power_switch}")

        auto_power_off = await divoom.system.get_auto_power_off()
        logger.info(f"Auto Power Off (0xac): {auto_power_off} minutes")

        sound_control = await divoom.system.get_sound_control()
        logger.info(f"Sound Control (0xa8): {sound_control}")

    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        await divoom.disconnect()
        logger.info("Disconnected from Divoom device.")

if __name__ == "__main__":
    asyncio.run(debug_divoom_getters("Timoo"))