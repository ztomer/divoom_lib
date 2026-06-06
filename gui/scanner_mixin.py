# gui/scanner_mixin.py

import os
import json
import logging
import asyncio
from pathlib import Path
from divoom_lib.utils import discovery

logger = logging.getLogger("divoom_gui")

class ScannerMixin:
    """Mixin for Bluetooth scanning, discovery, and device selection."""
    def save_scan_settings(self, timeout: int, limit: int) -> bool:
        try:
            import configparser
            config_file = Path.home() / ".config" / "divoom-control" / "config.ini"
            config_file.parent.mkdir(parents=True, exist_ok=True)
            cfg = configparser.ConfigParser()
            if config_file.exists():
                cfg.read(config_file)
            if "gui" not in cfg:
                cfg["gui"] = {}
            cfg["gui"]["timeout"] = str(int(timeout))
            cfg["gui"]["limit"] = str(int(limit))
            with open(config_file, "w") as f:
                cfg.write(f)
            return True
        except Exception as e:
            logger.warning(f"Failed to save scan config: {e}")
            return False

    def scan_devices(self, timeout: int = 15, limit: int = 4) -> str:
        logger.info(f"GUI Action: Scanning devices with timeout={timeout}, limit={limit}...")
        self.save_scan_settings(timeout, limit)

        if os.environ.get("DIVOOM_MOCK_BLE") in ("1", "true", "yes"):
            mock = [{"name": "Pixoo-Mock", "address": "AA:BB:CC:DD:EE:FF"}]
            try:
                cache_file = Path.home() / ".config" / "divoom-control" / "discovered_devices.json"
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(json.dumps(mock), encoding="utf-8")
            except Exception:
                pass
            return json.dumps(mock)

        try:
            if limit > 0:
                discovered = []
                divoom_keywords = ["timoo", "tivoo", "timebox", "pixoo", "ditoo", "backpack", "timegate"]
                
                def detection_callback(device, advertisement_data):
                    if device.name:
                        name_lower = device.name.lower()
                        is_divoom = any(kw in name_lower for kw in divoom_keywords)
                        if is_divoom:
                            if not any(d["address"] == device.address for d in discovered):
                                discovered.append({
                                    "name": device.name,
                                    "address": device.address
                                })
                                logger.info(f"Scanner: Found Divoom device: {device.name} ({device.address})")
                
                async def run_scan():
                    from gui_main import BleakScanner
                    scanner = BleakScanner(detection_callback=detection_callback)
                    await scanner.start()
                    elapsed = 0.0
                    while elapsed < timeout and len(discovered) < limit:
                        await asyncio.sleep(0.5)
                        elapsed += 0.5
                    await scanner.stop()
                    return discovered
                    
                results = self._run_async(run_scan())
                if not results:
                    results = self._run_async(discovery.discover_all_divoom_devices(timeout=float(timeout)))
                    results = results[:limit]
            else:
                results = self._run_async(discovery.discover_all_divoom_devices(timeout=float(timeout)))
                
            self.discovered_list = results
            try:
                cache_file = Path.home() / ".config" / "divoom-control" / "discovered_devices.json"
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
                logger.info(f"Scanner: Cached {len(results)} discovered devices to discovered_devices.json")
                
                import configparser
                config_file = Path.home() / ".config" / "divoom-control" / "config.ini"
                cfg = configparser.ConfigParser()
                if config_file.exists():
                    cfg.read(config_file)
                if "gui" not in cfg:
                    cfg["gui"] = {}
                cfg["gui"]["last_detected_count"] = str(len(results))
                with open(config_file, "w") as f:
                    cfg.write(f)
            except Exception as ce:
                logger.warning(f"Failed to cache discovered devices or count: {ce}")
            return json.dumps(results)
        except Exception as e:
            logger.error(f"Device scan failed: {e}")
            return json.dumps([])

    def connect_single_device(self, address: str) -> bool:
        logger.info(f"GUI Action: Connecting to single device {address}...")
        try:
            connected = False
            if address == "MatrixWall":
                self.current_target_mode = "wall"
                logger.info("Switched to multi-screen display wall mode.")
                connected = True
            else:
                self.current_target_mode = "single"
                if self.current_divoom and self.current_divoom.is_connected:
                    self._run_async(self.current_divoom.disconnect())
                    
                if address.startswith("LAN:"):
                    ip = address.split("LAN:")[1]
                    local_token = 0
                    
                    presets_file = self._get_presets_file()
                    if presets_file.exists():
                        try:
                            presets = json.loads(presets_file.read_text(encoding="utf-8"))
                            devices = presets.get("lan_devices", [])
                            for d in devices:
                                if d.get("ip") == ip:
                                    local_token = int(d.get("token", 0))
                                    break
                        except Exception:
                            pass
                    
                    from gui_main import Divoom
                    self.current_divoom = Divoom(mac=None, lan_ip=ip, lan_token=local_token, logger=logger)
                    from divoom_lib.lan_transport import LanTransport
                    self.current_divoom._lan = LanTransport(device_ip=ip, local_token=local_token, logger=logger)
                    
                    reachable = self._run_async(self.current_divoom._lan.probe())
                    if not reachable:
                        logger.error(f"LAN Device at {ip} is unreachable")
                        self.current_divoom = None
                        return False
                    connected = True
                else:
                    client = None
                    if os.environ.get("DIVOOM_MOCK_BLE") in ("1", "true", "yes"):
                        import sys as _sys
                        _sys.path.append(str(Path(__file__).parent.parent / "scripts"))
                        from mock_device import MockBleakClient
                        client = MockBleakClient(address)
                        logger.info("DIVOOM_MOCK_BLE: using MockBleakClient")
                    device_name = None
                    for d in self.discovered_list:
                        if d.get("address") == address:
                            device_name = d.get("name")
                            break
                    if not device_name:
                        try:
                            import json
                            from pathlib import Path
                            cache_file = Path.home() / ".config" / "divoom-control" / "discovered_devices.json"
                            if cache_file.exists():
                                devices = json.loads(cache_file.read_text(encoding="utf-8"))
                                for d in devices:
                                    if d.get("address") == address:
                                        device_name = d.get("name")
                                        break
                        except Exception:
                            pass

                    from gui_main import Divoom
                    self.current_divoom = Divoom(mac=address, client=client, logger=logger, use_ios_le_protocol=True, device_name=device_name)
                    self._run_async(self.current_divoom.connect())
                    connected = True

            if connected:
                try:
                    import configparser
                    from pathlib import Path
                    config_file = Path.home() / ".config" / "divoom-control" / "config.ini"
                    config_file.parent.mkdir(parents=True, exist_ok=True)
                    cfg = configparser.ConfigParser()
                    if config_file.exists():
                        cfg.read(config_file)
                    if "gui" not in cfg:
                        cfg["gui"] = {}
                    cfg["gui"]["last_connected_device"] = address
                    with open(config_file, "w") as f:
                        cfg.write(f)
                    logger.info(f"Saved last active connection: {address}")
                except Exception as save_err:
                    logger.warning(f"Failed to persist active connection: {save_err}")
                return True
            return False
        except Exception as e:
            logger.error(f"Single connect failed: {e}")
            self.current_divoom = None
            return False

    def update_wall_slots(self, slots_json: str) -> None:
        logger.info(f"GUI Action: Syncing free-form layout slots: {slots_json}")
        self.wall_slots = json.loads(slots_json)
        self.wall_instance = None
        
        try:
            presets_file = self._get_presets_file()
            presets = {}
            if presets_file.exists():
                try:
                    presets = json.loads(presets_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            presets["_last_active_slots_"] = self.wall_slots
            presets_file.write_text(json.dumps(presets, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to save last active slots: {e}")

    def _rebuild_wall_instance(self, cell_size: int = 16) -> bool:
        if not self.wall_slots:
            return False
            
        if self.wall_instance and self.wall_instance.is_connected:
            return True
            
        logger.info("Rebuilding free-form DivoomWall coordinator instance...")
        configs = [{
            "mac": mac,
            "x": int(s.get("x", 0)), "y": int(s.get("y", 0)),
            "size": int(s.get("size", cell_size)),
            "width": int(s.get("width", 120)), "height": int(s.get("height", 120))
        } for mac, s in self.wall_slots.items()]
            
        try:
            from gui_main import DivoomWall
            self.wall_instance = DivoomWall(configs, custom_logger=logger)
            self._run_async(self.wall_instance.connect())
            return True
        except Exception as e:
            logger.error(f"Failed to build display wall: {e}")
            self.wall_instance = None
            return False
