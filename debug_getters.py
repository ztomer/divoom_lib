import asyncio
import logging
from divoom_api.system import System

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Replace with your Divoom device's MAC address
# You can find this using discover_devices.py
DIVOOOM_MAC_ADDRESS = "XX:XX:XX:XX:XX:XX" # IMPORTANT: Replace with your device's MAC address

async def debug_system_getters():
    logger.info(f"Starting debug session for Divoom System getters on device {DIVOOOM_MAC_ADDRESS}")

    system_device = None
    try:
        # Instantiate the System class, which now inherits from DivoomBase
        system_device = System(mac=DIVOOOM_MAC_ADDRESS, logger=logger)
        
        logger.info("Connecting to Divoom device...")
        await system_device.connect()
        logger.info("Successfully connected to Divoom device.")

        # Test get_work_mode
        work_mode = await system_device.get_work_mode()
        logger.info(f"Work Mode: {work_mode}")

        # Test get_device_temp
        device_temp = await system_device.get_device_temp()
        logger.info(f"Device Temperature: {device_temp}")

        # Test get_net_temp_disp
        net_temp_disp = await system_device.get_net_temp_disp()
        logger.info(f"Network Temperature Display: {net_temp_disp}")

        # Test get_device_name
        device_name = await system_device.get_device_name()
        logger.info(f"Device Name: {device_name}")

        # Test get_low_power_switch
        low_power_switch = await system_device.get_low_power_switch()
        logger.info(f"Low Power Switch: {low_power_switch}")

        # Test get_auto_power_off
        auto_power_off = await system_device.get_auto_power_off()
        logger.info(f"Auto Power Off: {auto_power_off}")

        # Test get_sound_control
        sound_control = await system_device.get_sound_control()
        logger.info(f"Sound Control: {sound_control}")

    except Exception as e:
        logger.error(f"An error occurred during debugging: {e}")
    finally:
        if system_device and system_device.client and system_device.client.is_connected:
            logger.info("Disconnecting from Divoom device...")
            await system_device.disconnect()
            logger.info("Disconnected.")

if __name__ == "__main__":
    asyncio.run(debug_system_getters())
