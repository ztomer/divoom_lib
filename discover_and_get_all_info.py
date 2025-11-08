import asyncio
import logging
from bleak import BleakScanner, BleakClient
from divoom_protocol import DivoomBluetoothProtocol

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def print_info(message):
    """Prints an informational message."""
    logger.info(f"[ ==> ] {message}")

def print_ok(message):
    """Prints a success message."""
    logger.info(f"[ Ok  ] {message}")

async def get_all_divoom_info_logic(divoom_protocol_instance: DivoomBluetoothProtocol):
    """
    Fetches all available information from the Divoom device using the provided protocol instance.
    """
    logger.info("Fetching information...")

    # --- System Settings ---
    logger.info("\n--- System Settings ---")
    work_mode = await divoom_protocol_instance.get_work_mode()
    logger.info(f"Work Mode (0x13): {work_mode}")

    device_temp = await divoom_protocol_instance.get_device_temp()
    logger.info(f"Device Temperature (0x59): {device_temp}")

    net_temp_disp = await divoom_protocol_instance.get_net_temp_disp()
    logger.info(f"Network Temperature Display (0x73): {net_temp_disp}")

    device_name = await divoom_protocol_instance.get_device_name()
    logger.info(f"Device Name (0x76): {device_name}")

    low_power_switch = await divoom_protocol_instance.get_low_power_switch()
    logger.info(f"Low Power Switch (0xb3): {low_power_switch}")

    auto_power_off = await divoom_protocol_instance.get_auto_power_off()
    logger.info(f"Auto Power Off (0xac): {auto_power_off} minutes")

    sound_control = await divoom_protocol_instance.get_sound_control()
    logger.info(f"Sound Control (0xa8): {sound_control}")

    # --- Music Play ---
    logger.info("\n--- Music Play ---")
    sd_play_name = await divoom_protocol_instance.get_sd_play_name()
    logger.info(f"SD Play Name (0x06): {sd_play_name}")

    sd_music_list_total_num = await divoom_protocol_instance.get_sd_music_list_total_num()
    logger.info(f"SD Music List Total Num (0x7d): {sd_music_list_total_num}")
    if sd_music_list_total_num and sd_music_list_total_num > 0:
        sd_music_list = await divoom_protocol_instance.get_sd_music_list(0, min(4, sd_music_list_total_num - 1))
        logger.info(f"SD Music List (first 5) (0x07): {sd_music_list}")

    volume = await divoom_protocol_instance.get_volume()
    logger.info(f"Volume (0x09): {volume}")

    play_status = await divoom_protocol_instance.get_play_status()
    logger.info(f"Play Status (0x0b): {play_status}")

    sd_music_info = await divoom_protocol_instance.get_sd_music_info()
    logger.info(f"SD Music Info (0xb4): {sd_music_info}")

    # --- Alarm Memorial ---
    logger.info("\n--- Alarm Memorial ---")
    alarm_time = await divoom_protocol_instance.get_alarm_time()
    logger.info(f"Alarm Time (0x42): {alarm_time}")

    memorial_time = await divoom_protocol_instance.get_memorial_time()
    logger.info(f"Memorial Time (0x53): {memorial_time}")

    # --- Tool ---
    logger.info("\n--- Tool Information ---")
    timer_info = await divoom_protocol_instance.get_tool_info(0)
    logger.info(f"Timer Info (0x71, mode 0): {timer_info}")
    score_info = await divoom_protocol_instance.get_tool_info(1)
    logger.info(f"Score Info (0x71, mode 1): {score_info}")
    noise_info = await divoom_protocol_instance.get_tool_info(2)
    logger.info(f"Noise Info (0x71, mode 2): {noise_info}")
    countdown_info = await divoom_protocol_instance.get_tool_info(3)
    logger.info(f"Countdown Info (0x71, mode 3): {countdown_info}")

    # --- Sleep ---
    logger.info("\n--- Sleep Settings ---")
    sleep_scene = await divoom_protocol_instance.get_sleep_scene()
    logger.info(f"Sleep Scene (0xa2): {sleep_scene}")

    # --- Light ---
    logger.info("\n--- Light Settings ---")
    light_mode = await divoom_protocol_instance.get_light_mode()
    logger.info(f"Light Mode (0x46): {light_mode}")

    user_define_info = await divoom_protocol_instance.app_get_user_define_info(0)
    logger.info(f"App Get User Define Info (0x8e): {user_define_info}")


async def discover_and_get_info():
    print_info("Scanning for Divoom devices...")
    devices = await BleakScanner.discover()
    
    divoom_devices = []
    divoom_keywords = ["Timoo", "Tivoo", "Pixoo", "Ditoo"]
    for device in devices:
        if device.name and any(keyword in device.name for keyword in divoom_keywords):
            divoom_devices.append(device)
            print_ok(f"Found Divoom device: {device.name} ({device.address})")

    if not divoom_devices:
        print_info("No Divoom devices found.")
        return

    selected_device = divoom_devices[0]
    print_info(f"\nConnecting to {selected_device.name} ({selected_device.address})...")

    async with BleakClient(selected_device.address) as client:
        if client.is_connected:
            print_ok(f"Connected to {selected_device.name}.")
            
            # Instantiate DivoomBluetoothProtocol with the connected client
            # You might need to discover the write_characteristic_uuid and notify_characteristic_uuid
            # for your specific device. For now, we'll use a placeholder or default.
            # In a real scenario, you'd get these from client.services
            
            # Placeholder UUIDs - REPLACE WITH ACTUAL UUIDS FROM YOUR DEVICE IF KNOWN
            # You can find these by running discover_characteristics.py and inspecting the output
            WRITE_CHARACTERISTIC_UUID = "YOUR_WRITE_CHARACTERISTIC_UUID" # e.g., "49535343-8841-4e4d-9e4a-951ad7780000"
            NOTIFY_CHARACTERISTIC_UUID = "YOUR_NOTIFY_CHARACTERISTIC_UUID" # e.g., "49535343-1e4d-4bd9-ba61-23c647249616"

            # Attempt to find the SPP characteristic UUID from the discovered characteristics
            spp_characteristic_uuid = None
            for service in client.services:
                for char in service.characteristics:
                    if "spp" in char.uuid.lower() or "49535343" in char.uuid.lower(): # Common Divoom SPP UUID prefix
                        spp_characteristic_uuid = char.uuid
                        break
                if spp_characteristic_uuid:
                    break
            
            if not spp_characteristic_uuid:
                print_info("Could not find a suitable SPP characteristic UUID. Using default.")
                spp_characteristic_uuid = DivoomBluetoothProtocol.SPP_CHARACTERISTIC_UUID # Fallback to default

            # If specific UUIDs are not found, you might need to manually set them
            # or implement a more robust discovery of these specific characteristics.
            # For this example, we'll assume the default SPP_CHARACTERISTIC_UUID is the write characteristic
            # if a specific write UUID isn't provided.
            if WRITE_CHARACTERISTIC_UUID == "YOUR_WRITE_CHARACTERISTIC_UUID":
                print_info("Using SPP characteristic as WRITE_CHARACTERISTIC_UUID (placeholder).")
                WRITE_CHARACTERISTIC_UUID = spp_characteristic_uuid
            if NOTIFY_CHARACTERISTIC_UUID == "YOUR_NOTIFY_CHARACTERISTIC_UUID":
                print_info("Using SPP characteristic as NOTIFY_CHARACTERISTIC_UUID (placeholder).")
                NOTIFY_CHARACTERISTIC_UUID = spp_characteristic_uuid


            divoom_protocol_instance = DivoomBluetoothProtocol(
                mac=selected_device.address,
                logger=logger,
                client=client,
                write_characteristic_uuid=WRITE_CHARACTERISTIC_UUID,
                notify_characteristic_uuid=NOTIFY_CHARACTERISTIC_UUID,
                spp_characteristic_uuid=spp_characteristic_uuid
            )
            
            await get_all_divoom_info_logic(divoom_protocol_instance)

        else:
            print_info(f"Failed to connect to {selected_device.name}.")

if __name__ == "__main__":
    asyncio.run(discover_and_get_info())
