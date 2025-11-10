import asyncio
import logging
from divoom_lib import Divoom
from divoom_lib.constants import CHANNEL_ID_TIME, CHANNEL_ID_LIGHTNING, CHANNEL_ID_CLOUD, CHANNEL_ID_VJ_EFFECTS, CHANNEL_ID_VISUALIZATION, CHANNEL_ID_ANIMATION, CHANNEL_ID_SCOREBOARD

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RotateChannels")

async def rotate_channels(mac_address: str):
    """
    Connects to a Divoom device and rotates through its display channels.
    """
    divoom = Divoom(mac=mac_address, logger=logger)

    try:
        logger.info(f"Connecting to Divoom device at {mac_address}...")
        await divoom.connect()
        logger.info("Connected to Divoom device.")

        channels = [
            ("Time Channel", CHANNEL_ID_TIME),
            ("Lightning Channel", CHANNEL_ID_LIGHTNING),
            ("Cloud Channel", CHANNEL_ID_CLOUD),
            ("VJ Effects Channel", CHANNEL_ID_VJ_EFFECTS),
            ("Visualization Channel", CHANNEL_ID_VISUALIZATION),
            ("Animation Channel", CHANNEL_ID_ANIMATION),
            ("Scoreboard Channel", CHANNEL_ID_SCOREBOARD),
        ]

        for name, channel_id in channels:
            logger.info(f"Activating {name}...")
            await divoom.system.set_channel(channel_id)
            await asyncio.sleep(5) 

    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        logger.info("Disconnecting from Divoom device...")
        await divoom.disconnect()
        logger.info("Disconnected.")

if __name__ == "__main__":
    # Replace with your Divoom device's MAC address
    # On macOS, you can find this in System Preferences -> Bluetooth
    # On Linux, use `hcitool dev` or `bluetoothctl`
    DIVOOOM_MAC_ADDRESS = "XX:XX:XX:XX:XX:XX" 

    if DIVOOOM_MAC_ADDRESS == "XX:XX:XX:XX:XX:XX":
        logger.error("Please replace 'XX:XX:XX:XX:XX:XX' with your Divoom device's MAC address.")
    else:
        asyncio.run(rotate_channels(DIVOOOM_MAC_ADDRESS))
