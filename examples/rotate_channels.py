import asyncio
import logging
from divoom_protocol import Divoom
from divoom_lib.constants import TimeDisplayType, LightningType, VJEffectType

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
            ("Time Channel", divoom.time_channel),
            ("Lightning Channel", divoom.lightning_channel),
            ("VJ Effect Channel", divoom.vj_effect_channel),
            ("Scoreboard Channel", divoom.scoreboard_channel),
            ("Cloud Channel", divoom.cloud_channel),
            ("Custom Channel", divoom.custom_channel),
        ]

        for name, channel_obj in channels:
            logger.info(f"Activating {name}...")
            # For channels that require specific parameters, set them before activation
            if name == "Time Channel":
                channel_obj.type = TimeDisplayType.Rainbow
                channel_obj.show_time = True
                channel_obj.color = "00FF00" # Green
            elif name == "Lightning Channel":
                channel_obj.type = LightningType.Love
                channel_obj.brightness = 75
                channel_obj.color = "FF00FF" # Magenta
                channel_obj.power = True
            elif name == "VJ Effect Channel":
                channel_obj.type = VJEffectType.Fire
            elif name == "Scoreboard Channel":
                channel_obj.red = 10
                channel_obj.blue = 5
            # Cloud and Custom channels don't have specific setters in their __init__
            # Their activation is handled by their __init__ calling _update_message

            # Give some time for the command to be sent and processed
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
