import asyncio
import logging
from divoom_lib import Divoom

# Configure logging for the entire application
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

async def main():
    MAC_ADDRESS = "F90D2CC9-420E-65F9-9E06-F9554470FCED"

    divoom = Divoom(mac=MAC_ADDRESS)

    try:
        await divoom.connect()
        
        # Attempt to get work mode
        current_mode = await divoom.system.get_work_mode()
        if current_mode is not None:
            logging.info(f"Successfully retrieved work mode: {current_mode}")
        else:
            logging.warning("Failed to retrieve work mode.")

    except Exception as e:
        logging.error(f"An error occurred: {e}")
    finally:
        await divoom.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
