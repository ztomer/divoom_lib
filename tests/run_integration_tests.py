import asyncio
import logging
import os
import sys

# Add the project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from divoom_lib.divoom_protocol import Divoom
from divoom_lib.utils.discovery import discover_device
from divoom_lib.utils import cache

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("integration_test_runner")

# List of tests to run
tests_to_run = []

def test_case(func):
    """Decorator to register a test case."""
    tests_to_run.append(func)
    return func

@test_case
async def test_set_and_get_brightness():
    """
    Tests setting and then getting the device brightness to verify it was set correctly.
    """
    logger.info("--- Running test: test_set_and_get_brightness ---")
    divoom = None
    original_brightness = None
    try:
        # Discover and connect
        ble_device, device_id = await discover_device(name_substring="Timoo")
        if not ble_device:
            raise ConnectionError("No Divoom device found.")
        
        logger.info(f"Found device: {device_id}")
        divoom = Divoom(mac=device_id, logger=logger)
        await divoom.connect()
        logger.info(f"Successfully connected to {divoom.mac}!")

        # CRITICAL STEP: Probe for the correct characteristics
        logger.info("Probing for working characteristics...")
        write_chars = []
        notify_chars = []
        read_chars = []
        for service in divoom.client.services:
            for char in service.characteristics:
                if "write" in char.properties or "write_without_response" in char.properties:
                    write_chars.append(char)
                if "notify" in char.properties:
                    notify_chars.append(char)
                if "read" in char.properties:
                    read_chars.append(char)
        
        device_cache = cache.load_device_cache(cache.DEFAULT_CACHE_DIR, device_id) or {}
        working_char_uuid = await divoom.probe_write_characteristics_and_try_channel_switch(
            write_chars, notify_chars, read_chars, device_cache, cache.DEFAULT_CACHE_DIR, device_id, []
        )

        if not working_char_uuid and not divoom.WRITE_CHARACTERISTIC_UUID:
             raise ConnectionError("Failed to find a working write characteristic.")
        logger.info(f"Probing complete. Using write characteristic: {divoom.WRITE_CHARACTERISTIC_UUID}")

        # HYPOTHESIS: Send a "setter" command to wake the device before sending a "getter".
        logger.info("Sending a 'show_light' command to wake the device...")
        await divoom.display.show_light(color="0000FF", brightness=100)
        await asyncio.sleep(2) # Give the device a moment to process.
        logger.info("Wake-up command sent.")

        # 1. Get initial brightness
        logger.info("Getting initial brightness...")
        initial_settings = await divoom.light.get_light_mode()
        if initial_settings is None:
            raise AssertionError("Failed to get initial light settings.")
        
        original_brightness = initial_settings.get("system_brightness")
        if original_brightness is None:
            raise AssertionError("Failed to get initial system_brightness.")
        logger.info(f"Initial brightness is: {original_brightness}")

        # 2. Set new brightness
        new_brightness = 50
        if new_brightness == original_brightness:
            new_brightness = 75
        
        logger.info(f"Setting brightness to {new_brightness}...")
        await divoom.system.set_brightness(new_brightness)
        logger.info("Set brightness command sent.")
        
        await asyncio.sleep(3)

        # 3. Get brightness again and verify
        logger.info("Getting brightness again to verify...")
        new_settings = await divoom.light.get_light_mode()
        if new_settings is None:
            raise AssertionError("Failed to get new light settings.")
        
        current_brightness = new_settings.get("system_brightness")
        if current_brightness is None:
            raise AssertionError("Failed to get current system_brightness.")
        logger.info(f"Current brightness is: {current_brightness}")
        
        assert current_brightness == new_brightness, f"Brightness was not set correctly. Expected {new_brightness}, got {current_brightness}."
        
        return True, "Test passed."

    except Exception as e:
        logger.error(f"Test failed with an exception: {e}", exc_info=True)
        return False, str(e)
    finally:
        # 4. Restore original brightness and disconnect
        if divoom and divoom.is_connected:
            if original_brightness is not None:
                logger.info(f"Restoring original brightness to {original_brightness}...")
                await divoom.system.set_brightness(original_brightness)
            await divoom.disconnect()
            logger.info("Disconnected from Divoom device.")

async def main():
    """
    Main function to run all registered test cases.
    This script is used instead of pytest or unittest because those frameworks
    interfere with the bleak library's async notification handling.
    """
    logger.info("Starting Divoom Integration Test Suite")
    results = {}
    all_passed = True

    for test_func in tests_to_run:
        test_name = test_func.__name__
        passed, message = await test_func()
        results[test_name] = {"passed": passed, "message": message}
        if passed:
            logger.info(f"[  OK  ] {test_name}")
        else:
            logger.error(f"[ FAIL ] {test_name}: {message}")
            all_passed = False
    
    logger.info("\n--- Test Summary ---")
    for name, result in results.items():
        status = "OK" if result["passed"] else "FAIL"
        logger.info(f"[{status:^6s}] {name}")

    if not all_passed:
        logger.error("\nSome tests failed.")
        sys.exit(1)
    else:
        logger.info("\nAll tests passed!")
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())
