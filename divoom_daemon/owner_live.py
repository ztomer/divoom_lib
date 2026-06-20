import asyncio
import logging

logger = logging.getLogger("divoom_daemon.owner_live")

class OwnerLiveMixin:
    def __init__(self):
        self._live_tasks = {}    # (mac, kind) -> asyncio.Task
        self._live_devices = {}  # mac -> connected Divoom/DivoomWall (background jobs)
        self._device_activity = {}  # R46 #3: mac -> {name, kind, at} (menubar previews)
        self._live_params = {}   # A2: (mac, kind) -> params, persisted for rehydration

    # ── A2: persist + rehydrate live jobs across a daemon restart ────────────
    # The daemon is the single owner; if it crashes/restarts, in-memory live jobs
    # were lost and streaming widgets silently stopped. Persist the desired set so
    # the daemon resumes them on boot.
    def _live_jobs_path(self):
        from pathlib import Path
        return Path.home() / ".config" / "divoom-control" / "live_jobs.json"

    def _save_live_jobs(self) -> None:
        import json
        from divoom_lib.utils.atomic_io import atomic_write_text
        try:
            jobs = [{"mac": m, "kind": k, "params": p}
                    for (m, k), p in getattr(self, "_live_params", {}).items()]
            atomic_write_text(self._live_jobs_path(), json.dumps(jobs, indent=2))
        except Exception as e:
            logger.debug(f"persist live jobs failed: {e}")

    def rehydrate_live_jobs(self) -> None:
        """Restart the live jobs persisted before the last shutdown/crash."""
        import json
        path = self._live_jobs_path()
        if not path.exists():
            return
        try:
            jobs = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"could not read persisted live jobs: {e}")
            return
        for j in jobs or []:
            mac, kind = j.get("mac"), j.get("kind")
            if not mac or not kind:
                continue
            try:
                self.live_job_start({"mac": mac, "kind": kind, "params": j.get("params") or {}})
                logger.info("rehydrated live job %s for %s", kind, mac)
            except Exception as e:
                logger.warning("rehydrate %s/%s failed: %s", kind, mac, e)

    # ── R46 #3: per-device activity registry (for the menubar previews) ──────
    def set_device_activity(self, args: dict) -> dict:
        """Record what a device is currently showing (kind: clock / eq / vj /
        scoreboard / ambient / text / design / sysmon / stocks / weather /
        music / idle). The GUI pushes this from its setDeviceActivity; the
        daemon also sets it from its own live jobs (below). The menubar pulls
        get_device_activity to render one tile per device."""
        import time
        mac = args.get("mac")
        if not mac:
            return {"success": False, "error": "set_device_activity requires 'mac'"}
        if getattr(self, "_device_activity", None) is None:
            self._device_activity = {}
        entry = self._device_activity.get(mac, {})
        name = args.get("name") or self._resolve_device_name(mac)
        if name:
            entry["name"] = name
        # An empty kind means "thumbnail-only update" (a live frame whose
        # semantic kind the daemon's own live job already set) — keep that kind.
        kind = args.get("kind")
        if kind:
            entry["kind"] = kind
        elif not entry.get("kind"):
            entry["kind"] = "idle"
        # R50: optional rasterized PNG thumbnail (data URL) for the menubar tile.
        preview = args.get("preview")
        if preview:
            entry["preview"] = preview
        entry["at"] = time.time()
        self._device_activity[mac] = entry
        return {"success": True}

    def _resolve_device_name(self, mac):
        """Best-effort friendly name for a mac from the devices the daemon owns
        (so a live job started without a name still shows 'Ditoo', not the raw
        MAC, in the menubar / GUI)."""
        if mac == getattr(self, "mac", None) and getattr(self, "_device", None) is not None:
            nm = getattr(self._device, "device_name", None)
            if nm:
                return nm
        bg = getattr(self, "_live_devices", {}).get(mac)
        if bg is not None and getattr(bg, "device_name", None):
            return bg.device_name
        existing = getattr(self, "_device_activity", {}).get(mac, {})
        return existing.get("name")

    def get_device_activity(self, _args: dict) -> dict:
        self._prune_device_activity()
        self._stamp_live_health()
        return {"success": True, "activity": getattr(self, "_device_activity", {}) or {}}

    def _stamp_live_health(self) -> None:
        """G5: a background live-widget device that drops gets self-healed but its
        health was invisible (connection_state only watches the ACTIVE device).
        Stamp each owned device's honest state onto its activity entry so the
        R47 selector dot can show a degraded/streaming device."""
        act = getattr(self, "_device_activity", None)
        if not act:
            return
        from divoom_lib.ble_connection import derive_connection_state
        for mac, dev in (getattr(self, "_live_devices", {}) or {}).items():
            if mac in act:
                act[mac]["state"] = derive_connection_state(dev).value
        # the active device's own state (if it's tracked as an activity entry)
        active = getattr(self, "_active_key", lambda: None)()
        if active and active in act and getattr(self, "_device", None) is not None:
            act[active]["state"] = derive_connection_state(self._device).value

    # G1: keep the registry honest. Without teardown an entry survives disconnect /
    # wall tear-down / stop-all, so the R47 selector + menubar keep showing a
    # device that's no longer owned ("ghost"). forget on a hard drop; idle on a
    # soft stop; TTL-prune anything stale that's neither active nor streaming.
    _ACTIVITY_TTL = 600  # seconds; an idle, non-active, job-less entry older than
                         # this is stale (the device left and never came back).

    def forget_device_activity(self, mac) -> None:
        act = getattr(self, "_device_activity", None)
        if act and mac:
            act.pop(mac, None)

    def _idle_device_activity(self, mac) -> None:
        if mac:
            self.set_device_activity({"mac": mac, "kind": "idle"})

    def _prune_device_activity(self) -> None:
        import time
        act = getattr(self, "_device_activity", None)
        if not act:
            return
        now = time.time()
        active = getattr(self, "mac", None)
        lan_ip = getattr(self, "_lan_ip", None)
        active_lan = f"LAN:{lan_ip}" if lan_ip else None
        live_macs = {m for (m, _k) in getattr(self, "_live_tasks", {})}
        for mac in list(act.keys()):
            # Never prune the active device or a mac with a running live job —
            # a long-running widget sets `at` once at start, so age alone lies.
            if mac in (active, active_lan) or mac in live_macs:
                continue
            entry = act.get(mac) or {}
            if now - entry.get("at", now) >= self._ACTIVITY_TTL:
                act.pop(mac, None)

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
        self.set_device_activity({"mac": mac, "kind": kind, "name": params.get("device_name")})
        if getattr(self, "_live_params", None) is None:
            self._live_params = {}
        self._live_params[(mac, kind)] = params   # A2: remember for rehydration
        self._save_live_jobs()
        return {"success": True}

    def live_job_stop(self, args: dict) -> dict:
        mac = args.get("mac")
        kind = args.get("kind")
        if not mac or not kind:
            return {"success": False, "error": "live_job_stop requires 'mac' and 'kind'"}

        key = (mac, kind)
        if self._loop is None or key not in self._live_tasks:
            return {"success": True, "stopped": False}

        # R53: cancel AND AWAIT the task's death on the loop thread, before doing
        # anything else. The old fire-and-forget cancel let a stopped poller push
        # one more frame, let _release_live_device_if_idle run while the dying task
        # could still resurrect the device, and let live_job_start momentarily run
        # two pollers. Popping inside the coroutine also keeps _live_tasks mutation
        # confined to the loop thread.
        async def _stop_on_loop():
            t = self._live_tasks.pop(key, None)
            if t is None:
                return False
            t.cancel()
            await asyncio.gather(t, return_exceptions=True)   # wait for it to die
            return True

        try:
            stopped = asyncio.run_coroutine_threadsafe(
                _stop_on_loop(), self._loop).result(timeout=10)
        except Exception as e:
            logger.warning("live_job_stop: await-cancel failed for %s/%s: %s", mac, kind, e)
            self._live_tasks.pop(key, None)   # best effort
            stopped = True
        if not stopped:
            return {"success": True, "stopped": False}

        logger.info(f"Cancelled live job '{kind}' for {mac}")
        self._release_live_device_if_idle(mac)   # safe now — the task is dead
        # A2: a user-stopped widget is no longer desired — drop it from the
        # persisted set so it doesn't resurrect on the next daemon start.
        if getattr(self, "_live_params", None) is not None:
            self._live_params.pop(key, None)
            self._save_live_jobs()
        # R46 #3: no more jobs of this kind — mark idle unless another job runs.
        if not any(m == mac for (m, _k) in self._live_tasks):
            self.set_device_activity({"mac": mac, "kind": "idle"})
        return {"success": True, "stopped": True}

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
            # AWAIT it (bounded) — fire-and-forget let device_owner.stop()'s loop
            # teardown kill the disconnect before it ran, leaking the OS-level link
            # (the same window R53.20 closed for stop_all_live_jobs).
            try:
                asyncio.run_coroutine_threadsafe(_disc(), self._loop).result(timeout=10)
            except Exception as e:
                logger.debug("release-device disconnect failed/timed out for %s: %s", mac, e)

    def live_jobs_stop_for(self, args: dict) -> dict:
        """Stop ALL live jobs for a device (default: the active device, ``self.mac``).
        A channel / clock / VJ / visualizer switch takes over the screen and is
        mutually exclusive with a streaming widget — without stopping the widget
        first, its next tick re-pushes its frame and clobbers the switch
        (HW-confirmed: switch to Clock while sysmon runs → screen stays on the
        sysmon frame)."""
        mac = (args or {}).get("mac") or getattr(self, "mac", None)
        if not mac:
            return {"success": True, "stopped": 0}
        kinds = [k for (m, k) in list(self._live_tasks.keys()) if m == mac]
        for kind in kinds:
            self.live_job_stop({"mac": mac, "kind": kind})
        return {"success": True, "stopped": len(kinds)}

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
        macs = {m for (m, _k) in self._live_tasks}

        # R53.20: cancel AND AWAIT every poller, then disconnect the cached
        # background devices — ALL on the loop thread in one shot. The old
        # fire-and-forget `call_soon_threadsafe(task.cancel)` let a dying poller
        # resurrect a device after release (the same bug R53.4 fixed for
        # live_job_stop), and the fire-and-forget device disconnect could be
        # killed by device_owner.stop()'s loop teardown before it ran (leaked
        # OS-level connection). Awaiting here closes both windows.
        async def _stop_all_on_loop():
            tasks = list(self._live_tasks.values())
            self._live_tasks.clear()
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            devs = list(self._live_devices.values())
            self._live_devices.clear()
            for d in devs:
                try:
                    await d.disconnect()
                except Exception:
                    pass

        if self._loop is not None:
            try:
                asyncio.run_coroutine_threadsafe(
                    _stop_all_on_loop(), self._loop).result(timeout=10)
            except Exception as e:
                logger.warning("stop_all_live_jobs await-cancel failed: %s", e)
                self._live_tasks.clear()
        else:
            self._live_tasks.clear()
        # G1: the screens are no longer streaming — mark idle so the menubar /
        # selector stop showing them as live (the active one stays selectable).
        for mac in macs:
            self._idle_device_activity(mac)
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
                configs.append(cfg)   # once per slot — was wrongly nested under `if height`
            wall = DivoomWall(configs, custom_logger=logger)
            await wall.connect()
            # Cache it: without this a background wall live job rebuilt + reconnected
            # EVERY tick — a full multi-device BLE connect storm (the exact churn the
            # cache exists to prevent). DivoomWall.is_alive drives the reuse gate above;
            # _release_live_device_if_idle disconnects it on stop. (Only reached when
            # self._wall is None, so this never aliases the ACTIVE wall.)
            self._live_devices[mac] = wall
            return wall

        # For LAN device. NB: NOT cached — a LAN device is connectionless (per-request
        # HTTP), so rebuilding the transport object each tick is cheap, and caching it
        # would mis-report under the BLE is_alive/is_connected liveness model (it would
        # read as degraded). Rebuild is the pragmatic choice for this niche path.
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
