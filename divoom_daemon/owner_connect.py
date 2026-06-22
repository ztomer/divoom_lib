"""Device acquisition + discovery for the Divoom daemon.

Split out of device_owner.py (R53.8): everything about HOW the daemon acquires,
owns, reports, and discovers a device — connect / disconnect / scan, building and
ensuring the BLE/LAN handle, and the honest connection-state fields. What the
daemon DOES with an owned device (device_call / exclusive / sync_artwork) stays in
device_owner.py. Mixed into DeviceOwner; relies on its instance attributes
(`_device`, `mac`, `_lan_ip`, `_wall`, `_scan_name_cache`, …) and the loop/runner
helpers from OwnerLoopMixin (`_run_device`, `_run_on_loop`).
"""
from __future__ import annotations

import logging
from typing import Optional

from divoom_daemon.owner_util import _json_safe

logger = logging.getLogger("divoom_daemon.device_owner")


class OwnerConnectMixin:
    def _device_connected(self) -> bool:
        # P6 design: the legacy `connected` field reflects the raw is_connected;
        # honest liveness (DEGRADED on a dead-but-cached link) is surfaced via
        # `connection_state` (derive_connection_state → is_alive), not here.
        d = self._device
        return bool(d is not None and getattr(d, "is_connected", False))

    def _owned_devices(self) -> list[dict]:
        """Devices the daemon holds (active + live jobs). A connected BLE peripheral
        stops advertising → scan can't see it → it vanishes from the selector; union
        it back. Name: device_name | scan-cache | raw MAC. BLE only (LAN isn't scan)."""
        def _name(dev, mac):
            return (getattr(dev, "device_name", None)
                    or self._scan_name_cache.get(mac.upper()) or mac)

        owned: dict[str, dict] = {}
        d = self._device
        if d is not None and self.mac and not self._lan_ip:
            owned[self.mac.upper()] = {
                "name": _name(d, self.mac), "address": self.mac, "owned": True}
        # snapshot: the device-loop thread inserts into / pops _live_devices
        # (get_live_device / _release_live_device_if_idle) while a scan runs this
        # on an RPC thread (G2 runs scan off the queue). A bare .items() loop here
        # raised "dict changed size during iteration" → swallowed by scan()'s
        # except → a false empty "no devices found" exactly when streaming. (The
        # one _live_devices read R53.32 missed.)
        for mac, dev in list((getattr(self, "_live_devices", None) or {}).items()):
            if mac and mac.upper() not in owned:
                owned[mac.upper()] = {
                    "name": _name(dev, mac), "address": mac, "owned": True}
        return list(owned.values())

    def _current_target_key(self) -> Optional[str]:
        """Normalized identity of the device the owner currently holds (BLE mac or
        LAN key), so a connect to a DIFFERENT target can be detected."""
        if self._lan_ip:
            return f"LAN:{self._lan_ip}"
        return (self.mac or "").upper() or None

    def _connection_state(self) -> str:
        """P6: the honest dot state + a one-line transition log (a connection
        timeline in the daemon log). See ble_connection.derive_connection_state."""
        from divoom_lib.ble_connection import derive_connection_state
        active = self._device if self._device is not None else self._wall
        state = derive_connection_state(active)
        if state != self._last_conn_state:
            logger.info("connection state: %s -> %s (mac=%s)",
                        getattr(self._last_conn_state, "value", "none"),
                        state.value, self.mac)
            self._last_conn_state = state
        return state.value

    async def _ensure_device_async(self, mac: Optional[str] = None):
        # BLE Hardening P1: a failed reconnect raises a typed reason, never a
        # dead handle the next command silently times out on.
        from divoom_lib.ble_connection import ensure_connected, BleConnectionError
        if self._device is not None:
            # R53.x: if a DIFFERENT known BLE target is requested than the one we
            # hold, release it first and rebuild below — returning the cached
            # device would drive the WRONG screen and report success (the bug
            # _build_device_async already guards on the connect path; device_call
            # reaches us, not that path). Scoped to real BLE macs: a LAN target
            # isn't built here, and mac=None means "the active device".
            req_key = (mac or "").upper() or None
            held_key = self._current_target_key()
            if (req_key and not req_key.startswith("LAN:")
                    and held_key and not held_key.startswith("LAN:")
                    and req_key != held_key):
                logger.info("ensure target changed (%s -> %s); releasing held device",
                            held_key, req_key)
                try:
                    await self._device.disconnect()
                except Exception as e:
                    logger.debug("ensure release-on-switch disconnect failed: %s", e)
                self._device = None
                self._lan_ip = None
            else:
                # R53/HW: re-ensure on a dead-but-cached-connected link (is_alive is
                # honest; is_connected lags True after an OS drop).
                if not getattr(self._device, "is_alive",
                               getattr(self._device, "is_connected", False)) \
                        and hasattr(self._device, "connect"):
                    res = await ensure_connected(self._device)
                    if not res.ok:
                        raise BleConnectionError(res)
                return self._device
        from divoom_lib.divoom import Divoom
        from divoom_lib.utils import discovery
        target = mac or self.mac
        if not target:
            from divoom_daemon.daemon_config import load_daemon_config
            devs = await discovery.discover_all_divoom_devices(
                timeout=load_daemon_config().reconnect_scan_timeout)
            if not devs:
                raise RuntimeError("no Divoom device found")
            target = devs[0]["address"]
        dev = Divoom(mac=target, logger=logger, use_ios_le_protocol=False)
        res = await ensure_connected(dev)
        if not res.ok:
            raise BleConnectionError(res)
        self._device = dev
        # Keep self.mac in lockstep with the held device so _current_target_key
        # reflects reality — otherwise the NEXT ensure(B) would see a stale held
        # key and disconnect/reconnect on every call (churn).
        self.mac = target
        return self._device

    async def _build_device_async(self, args: dict):
        # BLE Hardening P1: honest connect (retry+backoff, verify, typed reason).
        from divoom_lib.ble_connection import ensure_connected, BleConnectionError
        # R53/HW: if a DIFFERENT *known* target is requested than the one we hold,
        # release the current one first — else connecting to B while A is active
        # silently returned A (cached is_connected made it look connected in 0.0s),
        # driving the wrong screen. current_key=None (untracked/injected) → reuse.
        requested = args.get("mac") or (args.get("lan_ip") and f"LAN:{args.get('lan_ip')}")
        requested_key = (requested or "").upper() or None
        current_key = self._current_target_key()
        if self._device is not None and requested_key and current_key and requested_key != current_key:
            logger.info("connect target changed (%s -> %s); releasing current device",
                        current_key, requested_key)
            try:
                await self._device.disconnect()
            except Exception as e:
                logger.debug("release-on-switch disconnect failed (continuing): %s", e)
            self._device = None
            self._lan_ip = None
            self.mac = None
        if self._device is not None:
            # Same target (or a generic "use active" request): re-ensure if the
            # link is not alive, else reuse.
            if not getattr(self._device, "is_alive",
                           getattr(self._device, "is_connected", False)) \
                    and hasattr(self._device, "connect"):
                res = await ensure_connected(self._device, attempts=2, attempt_timeout=8.0)
                if not res.ok:
                    raise BleConnectionError(res)
            return self._device
        from divoom_lib.divoom import Divoom
        lan_ip = args.get("lan_ip")
        if lan_ip:
            from divoom_lib.lan_transport import LanTransport
            token = int(args.get("lan_token", 0) or 0)
            dev = Divoom(mac=None, lan_ip=lan_ip, lan_token=token, logger=logger)
            dev._lan = LanTransport(device_ip=lan_ip, local_token=token, logger=logger)
            if not await dev._lan.probe():
                raise RuntimeError(f"LAN device at {lan_ip} unreachable")
            self._device = dev
            self._lan_ip = lan_ip
            return dev
        mac = args.get("mac")
        if not mac:
            return await self._ensure_device_async(None)
        dev = Divoom(mac=mac, logger=logger, device_name=args.get("device_name"),
                     use_ios_le_protocol=bool(args.get("use_ios_le_protocol", True)))
        res = await ensure_connected(dev, attempts=2, attempt_timeout=8.0)
        if not res.ok:
            raise BleConnectionError(res)   # don't keep a dead handle
        self._device = dev
        self.mac = mac
        return self._device

    def _status_fields(self) -> dict:
        return {
            "connected": self._device_connected(),
            "connection_state": self._connection_state(),   # P6: honest dot state
            "mac": self.mac,
            "lan_ip": self._lan_ip,
            "wall": self._wall is not None,
        }

    def connect(self, args: dict) -> dict:
        from divoom_lib.ble_connection import BleConnectionError
        # Reject an explicitly-empty target (mac="") — a UI bug must not silently
        # grab an arbitrary/last device. mac=None (absent) still means "use active".
        if any(v is not None and not str(v).strip()
               for v in (args.get("mac"), args.get("lan_ip"))):
            return {"success": False, "reason": "invalid_target",
                    "error": "empty target", "message": "No device selected."}
        # BLE Hardening P4: a BLE connect (mac, not LAN) preflights adapter/
        # permission so a powered-off radio / missing grant fails fast with cause.
        if args.get("mac") and not args.get("lan_ip"):
            from divoom_lib.ble_preflight import preflight_bluetooth
            pf = preflight_bluetooth()
            if not pf.ok:
                logger.warning("connect blocked by preflight: %s", pf.reason.value)
                return {"success": False, "error": pf.message,
                        "reason": pf.reason.value, "message": pf.message}
        # G4: taking a wall member as active — relinquish the wall first.
        tgt = args.get("mac") or (args.get("lan_ip") and f"LAN:{args.get('lan_ip')}")
        if tgt and tgt in (getattr(self, "_wall_slots", None) or {}):
            self._drop_current_wall()
            self._wall_slots = {}
        try:
            self._run_device(self._build_device_async(args))
            return {"success": True, **self._status_fields()}
        except BleConnectionError as e:
            logger.warning(f"connect failed: {e.result.reason.value} ({e.result.detail})")
            return {"success": False, "error": str(e),
                    "reason": e.result.reason.value, "message": e.result.message}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def disconnect(self) -> dict:
        # A user disconnect ENDS this device — stop its live jobs first so a poller
        # can't keep ticking on (or resurrect) the link we're about to release.
        # Defaults to the active mac; background jobs on OTHER devices are untouched.
        try:
            self.live_jobs_stop_for({})
        except Exception as e:
            logger.debug("stop live jobs on disconnect: %s", e)
        self.forget_device_activity(self.mac or (self._lan_ip and f"LAN:{self._lan_ip}"))  # G1: no ghost
        d = self._device
        if d is not None and hasattr(d, "disconnect"):
            try:
                self._run_device(d.disconnect())
            except Exception as e:
                logger.debug(f"disconnect: {e}")
        self._device = None
        self._lan_ip = None
        w = self._wall
        if w is not None and hasattr(w, "disconnect"):
            try:
                self._run_device(w.disconnect())
            except Exception as e:
                logger.debug(f"wall disconnect: {e}")
        self._wall = None
        return {"success": True, "connected": False}

    def device_status(self) -> dict:
        return {"success": True, **self._status_fields()}

    def scan(self, args: dict) -> dict:
        from divoom_daemon.daemon_config import load_daemon_config
        cfg = load_daemon_config()
        # 0 is a valid limit ("no cap"); only default when absent/None (not `or`).
        timeout = float(args.get("timeout") or cfg.scan_timeout)
        raw_limit = args.get("limit")
        limit = int(raw_limit if raw_limit is not None else cfg.scan_limit)

        # BLE Hardening P4: preflight so an empty scan carries a cause (denied
        # permission / powered-off adapter) instead of a silent "no devices".
        from divoom_lib.ble_preflight import preflight_bluetooth
        pf = preflight_bluetooth()
        if not pf.ok:
            logger.warning("scan blocked by preflight: %s (%s)", pf.reason.value, pf.detail)
            return {"success": False, "error": pf.message,
                    "reason": pf.reason.value, "message": pf.message, "devices": []}

        async def _scan():
            from divoom_lib.utils import discovery
            # early-exit once `limit` devices are seen (limit<=0 → full window)
            results = await discovery.discover_all_divoom_devices(
                timeout=timeout, expected=limit)
            return results[:limit] if limit > 0 else results

        try:
            # G2: scan off the command queue — it uses the central manager, not the
            # connected peripheral, so it must not serialize behind (and freeze)
            # device I/O / live-widget pushes for the scan's whole duration.
            results = self._run_on_loop(_scan())
            # Cache mac->name (so a non-advertising owned device keeps its name),
            # then union-in owned devices absent from this scan. See _owned_devices.
            for d in results:
                addr, nm = (d.get("address") or "").upper(), d.get("name")
                if addr and nm:
                    self._scan_name_cache[addr] = nm
            seen = {(d.get("address") or "").upper() for d in results}
            for od in self._owned_devices():
                if (od.get("address") or "").upper() not in seen:
                    results.append(od)
            return {"success": True, "devices": _json_safe(results)}
        except Exception as e:
            logger.warning(f"scan failed: {e}")
            return {"success": False, "error": str(e), "devices": []}

    def probe_lan(self) -> dict:
        d = self._device
        lan = getattr(d, "lan", None) if d is not None else None
        if lan is None:
            return {"success": True, "reachable": False, "detail": "no LAN configured"}

        async def _probe():
            return await lan.probe()

        try:
            ok = self._run_device(_probe())
            ip = getattr(lan, "device_ip", None)
            return {"success": True, "reachable": bool(ok), "device_ip": ip}
        except Exception as e:
            return {"success": False, "reachable": False, "error": str(e)}
