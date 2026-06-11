import asyncio
import logging

logger = logging.getLogger("divoom_daemon.owner_live")

class OwnerLiveMixin:
    def __init__(self):
        self._live_tasks = {}    # (mac, kind) -> asyncio.Task
        self._live_devices = {}  # mac -> connected Divoom/DivoomWall (background jobs)

    def live_job_start(self, args: dict) -> dict:
        mac = args.get("mac")
        kind = args.get("kind")
        params = args.get("params") or {}
        if not mac or not kind:
            return {"success": False, "error": "live_job_start requires 'mac' and 'kind'"}

        # Stop existing job of this kind on this mac
        self.live_job_stop({"mac": mac, "kind": kind})

        # Dynamically import run_* coroutine
        from divoom_daemon import live_jobs
        func = getattr(live_jobs, f"run_{kind}", None)
        if not func:
            return {"success": False, "error": f"unknown live job kind: {kind}"}

        # Make sure the device event loop is started
        if self._loop is None:
            self._device_loop()

        # Submit task creation to the loop
        async def _start():
            task = self._loop.create_task(func(self, mac, params))
            self._live_tasks[(mac, kind)] = task
            logger.info(f"Started live job '{kind}' for {mac}")

        asyncio.run_coroutine_threadsafe(_start(), self._loop).result()
        return {"success": True}

    def live_job_stop(self, args: dict) -> dict:
        mac = args.get("mac")
        kind = args.get("kind")
        if not mac or not kind:
            return {"success": False, "error": "live_job_stop requires 'mac' and 'kind'"}

        key = (mac, kind)
        if key in self._live_tasks:
            task = self._live_tasks.pop(key)
            self._loop.call_soon_threadsafe(task.cancel)
            logger.info(f"Cancelled live job '{kind}' for {mac}")
            self._release_live_device_if_idle(mac)
            return {"success": True, "stopped": True}

        return {"success": True, "stopped": False}

    def _release_live_device_if_idle(self, mac: str) -> None:
        """R44 §6: disconnect + drop a cached BACKGROUND device once no live
        jobs remain for it (the active device is owned elsewhere, never here)."""
        if any(m == mac for (m, _k) in self._live_tasks):
            return
        dev = self._live_devices.pop(mac, None)
        if dev is not None and self._loop is not None:
            async def _disc():
                try:
                    await dev.disconnect()
                except Exception:
                    pass
            asyncio.run_coroutine_threadsafe(_disc(), self._loop)

    def live_job_list(self, args: dict) -> dict:
        mac = args.get("mac")
        jobs = []
        for (m, k), task in list(self._live_tasks.items()):
            if mac is None or m == mac:
                jobs.append({
                    "mac": m,
                    "kind": k,
                    "done": task.done(),
                    "cancelled": task.cancelled()
                })
        return {"success": True, "jobs": jobs}

    def stop_all_live_jobs(self) -> None:
        if not getattr(self, "_live_tasks", None):
            return
        for key, task in list(self._live_tasks.items()):
            self._loop.call_soon_threadsafe(task.cancel)
        self._live_tasks.clear()
        for mac in list(getattr(self, "_live_devices", {})):
            self._release_live_device_if_idle(mac)
        logger.info("Stopped all background live jobs.")

    async def get_live_device(self, mac: str, params: dict):
        # If the active device matches, reuse it
        if getattr(self, "_device", None) is not None:
            active_mac = self.mac or (getattr(self, "_lan_ip", None) and f"LAN:{self._lan_ip}")
            if active_mac == mac:
                return self._device
        # R44 §6: reuse a previously-built BACKGROUND device for this mac so a
        # live job on a non-active device keeps ONE connection alive instead of
        # rebuilding+reconnecting every loop iteration (the symptom would be a
        # constant 5s reconnect churn / "shows last image").
        cached = self._live_devices.get(mac)
        if cached is not None and getattr(cached, "is_alive",
                                          getattr(cached, "is_connected", False)):
            return cached
        # For MatrixWall
        if mac == "MatrixWall":
            if getattr(self, "_wall", None) is not None:
                return self._wall
            # Build wall on the fly
            from divoom_lib.wall import DivoomWall
            slots = params.get("wall_slots") or {}
            configs = []
            cell = params.get("cell_size", 16)
            for sub_mac, s in slots.items():
                cfg = {
                    "mac": sub_mac,
                    "x": int(s.get("x", 0)), "y": int(s.get("y", 0)),
                    "size": int(s.get("size", cell)),
                }
                if "width" in s:
                    cfg["width"] = int(s["width"])
                if "height" in s:
                    cfg["height"] = int(s["height"])
                    configs.append(cfg)
            wall = DivoomWall(configs, custom_logger=logger)
            await wall.connect()
            return wall

        # For LAN device
        if mac.startswith("LAN:"):
            from divoom_lib.lan_transport import LanTransport
            from divoom_lib.divoom import Divoom
            ip = mac.split("LAN:")[1]
            token = int(params.get("lan_token") or 0)
            dev = Divoom(mac=None, lan_ip=ip, lan_token=token, logger=logger)
            dev._lan = LanTransport(device_ip=ip, local_token=token, logger=logger)
            return dev

        # For BLE device — build once, cache, reuse across loop iterations.
        from divoom_lib.divoom import Divoom
        dev = Divoom(
            mac=mac, logger=logger,
            use_ios_le_protocol=bool(params.get("use_ios_le_protocol", True)),
            device_name=params.get("device_name"),
        )
        self._live_devices[mac] = dev
        return dev
