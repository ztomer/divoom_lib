import asyncio
import logging
from divoom import Divoom

# Configure logging for the entire application
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

async def main():
    MAC_ADDRESS = "F90D2CC9-420E-65F9-9E06-F9554470FCED"
    WRITE_CHARACTERISTIC_UUID = "49535343-8841-43f4-a8d4-ecbe34729bb3"
    NOTIFY_CHARACTERISTIC_UUID_1 = "49535343-aca3-481c-91ec-d85e28a60318"
    NOTIFY_CHARACTERISTIC_UUID_2 = "49535343-1e4d-4bd9-ba61-23c647249616"

    # Create an instance of the DivoomBluetoothProtocol
    # We'll pass the notify characteristics as a list, though the class currently only uses one.
    # This might need adjustment if multiple notify characteristics are relevant for responses.
    divoom = Divoom(
        mac=MAC_ADDRESS,
        write_characteristic_uuid=WRITE_CHARACTERISTIC_UUID,
    )

    try:
        await divoom.connect()
        
        # Attempt to get work mode
        current_mode = await divoom.get_work_mode()
        if current_mode is not None:
            logging.info(f"Successfully retrieved work mode: {current_mode.hex()}")
        else:
            logging.warning("Failed to retrieve work mode.")

    except Exception as e:
        logging.error(f"An error occurred: {e}")
    finally:
        await divoom.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
