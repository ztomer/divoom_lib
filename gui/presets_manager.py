import json
import logging
from pathlib import Path
import configparser
import divoom_auth

logger = logging.getLogger("divoom_gui")

class PresetsManagerMixin:
    def save_credentials(self, email: str, password: str) -> bool:
        logger.info(f"GUI Action: Saving cloud credentials for {email}...")
        try:
            config_file = Path(__file__).parent.parent / "config.ini"
            cfg = configparser.ConfigParser()
            if config_file.exists():
                cfg.read(config_file)
            if "divoom" not in cfg:
                cfg["divoom"] = {}
            cfg["divoom"]["email"] = email
            cfg["divoom"]["password"] = password
            
            with open(config_file, "w") as f:
                cfg.write(f)
                
            auth_cache = Path(__file__).parent.parent / "api_scraper" / "divoom_docs" / "auth_token.json"
            if auth_cache.exists():
                auth_cache.unlink()
                
            self.cached_creds = divoom_auth.get_credentials(force_refresh=True)
            return self.cached_creds.is_valid()
        except Exception as e:
            logger.error(f"Failed to save credentials: {e}")
            return False

    def load_config(self) -> str:
        logger.info("GUI Action: Loading configurations...")
        try:
            config_file = Path(__file__).parent.parent / "config.ini"
            cfg = configparser.ConfigParser()
            email = ""
            timeout = 15
            limit = 4
            lan_ip = ""
            lan_token = 0
            
            if config_file.exists():
                cfg.read(config_file)
                email = cfg.get("divoom", "email", fallback="")
                timeout = int(cfg.get("gui", "timeout", fallback="15"))
                limit = int(cfg.get("gui", "limit", fallback="4"))
                lan_ip = cfg.get("lan", "device_ip", fallback="")
                lan_token = int(cfg.get("lan", "local_token", fallback="0"))
                
            presets_file = Path(__file__).parent / "presets.json"
            slots = {}
            if presets_file.exists():
                try:
                    data = json.loads(presets_file.read_text(encoding="utf-8"))
                    slots = data.get("_last_active_slots_", {})
                except Exception:
                    pass
                    
            return json.dumps({
                "email": email,
                "timeout": timeout,
                "limit": limit,
                "slots": slots,
                "lan_ip": lan_ip,
                "lan_token": lan_token,
            })
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return json.dumps({})

    def save_preset(self, name: str, slots_json: str) -> bool:
        logger.info(f"GUI Action: Saving layout preset '{name}'...")
        try:
            presets_file = Path(__file__).parent / "presets.json"
            presets = {}
            if presets_file.exists():
                try:
                    presets = json.loads(presets_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            presets[name] = json.loads(slots_json)
            presets_file.write_text(json.dumps(presets, indent=2), encoding="utf-8")
            return True
        except Exception as e:
            logger.error(f"Failed to save preset: {e}")
            return False

    def load_preset_names(self) -> str:
        logger.info("GUI Action: Loading preset names...")
        try:
            presets_file = Path(__file__).parent / "presets.json"
            if presets_file.exists():
                try:
                    presets = json.loads(presets_file.read_text(encoding="utf-8"))
                    names = [k for k in presets.keys() if k != "_last_active_slots_"]
                    return json.dumps(names)
                except Exception:
                    pass
            return json.dumps([])
        except Exception as e:
            logger.error(f"Failed to load preset names: {e}")
            return json.dumps([])

    def load_preset_by_name(self, name: str) -> str:
        logger.info(f"GUI Action: Loading preset '{name}'...")
        try:
            presets_file = Path(__file__).parent / "presets.json"
            if presets_file.exists():
                try:
                    presets = json.loads(presets_file.read_text(encoding="utf-8"))
                    slots = presets.get(name, {})
                    return json.dumps(slots)
                except Exception:
                    pass
            return json.dumps({})
        except Exception as e:
            logger.error(f"Failed to load preset '{name}': {e}")
            return json.dumps({})

    def load_lan_devices(self) -> str:
        logger.info("GUI Action: Loading LAN devices...")
        try:
            presets_file = Path(__file__).parent / "presets.json"
            devices = []
            if presets_file.exists():
                try:
                    presets = json.loads(presets_file.read_text(encoding="utf-8"))
                    devices = presets.get("lan_devices", [])
                except Exception:
                    pass
            return json.dumps(devices)
        except Exception as e:
            logger.error(f"Failed to load LAN devices: {e}")
            return json.dumps([])

    def add_lan_device(self, ip: str, token: int) -> bool:
        logger.info(f"GUI Action: Adding LAN device ip={ip} token={token}...")
        try:
            presets_file = Path(__file__).parent / "presets.json"
            presets = {}
            if presets_file.exists():
                try:
                    presets = json.loads(presets_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            devices = presets.get("lan_devices", [])
            if not any(d.get("ip") == ip for d in devices):
                devices.append({"ip": ip, "token": token})
            presets["lan_devices"] = devices
            presets_file.write_text(json.dumps(presets, indent=2), encoding="utf-8")
            return True
        except Exception as e:
            logger.error(f"Failed to add LAN device: {e}")
            return False

    def delete_lan_device(self, ip: str) -> bool:
        logger.info(f"GUI Action: Deleting LAN device ip={ip}...")
        try:
            presets_file = Path(__file__).parent / "presets.json"
            presets = {}
            if presets_file.exists():
                try:
                    presets = json.loads(presets_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            devices = presets.get("lan_devices", [])
            devices = [d for d in devices if d.get("ip") != ip]
            presets["lan_devices"] = devices
            presets_file.write_text(json.dumps(presets, indent=2), encoding="utf-8")
            return True
        except Exception as e:
            logger.error(f"Failed to delete LAN device: {e}")
            return False

