import asyncio
import logging
import argparse
from divoom_lib.divoom import Divoom
from divoom_lib.models import CHANNEL_ID_TIME, CHANNEL_ID_LIGHTNING, CHANNEL_ID_CLOUD, CHANNEL_ID_VJ_EFFECTS, CHANNEL_ID_VISUALIZATION, CHANNEL_ID_ANIMATION, CHANNEL_ID_SCOREBOARD

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
        await divoom.protocol.connect()
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
            await divoom.device.set_channel(channel_id)
            await asyncio.sleep(5) 

    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        if divoom.protocol.is_connected:
            logger.info("Disconnecting from Divoom device...")
            await divoom.protocol.disconnect()
            logger.info("Disconnected.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rotate through Divoom device channels.")
    parser.add_argument("mac_address", help="MAC address of the Divoom device")
    args = parser.parse_args()
    asyncio.run(rotate_channels(args.mac_address))
