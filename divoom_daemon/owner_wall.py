"""Wall ownership for the daemon owner.

The daemon owns at most one DivoomWall. This mixin holds its lifecycle:
build/teardown, the active-device-vs-wall single-ownership rule (G4), and the
delta reconfigure that keeps shared screens connected across a layout change
(G7). Split out of `device_owner.py` to keep that file under the 500-LOC cap.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("divoom_daemon.device_owner")


class OwnerWallMixin:
    def _drop_current_wall(self) -> None:
        """Disconnect + drop the current wall's BLE links. Without this, clearing
        or RECONFIGURING a wall leaked every screen's connection (HW-confirmed:
        the next build then times out reconnecting devices the daemon still
        held)."""
        w = self._wall
        if w is not None and hasattr(w, "disconnect"):
            try:
                self._run_device(w.disconnect())
            except Exception as e:
                logger.debug(f"wall teardown disconnect: {e}")
        self._wall = None
        self.forget_device_activity("MatrixWall")  # G1: drop wall tile after teardown

    def _active_key(self):
        ip = getattr(self, "_lan_ip", None)
        return getattr(self, "mac", None) or (ip and f"LAN:{ip}")

    def _relinquish_active_if_in(self, slots: dict) -> None:
        """G4: a screen is owned by the active link OR the wall, not both. If the
        active mac is also a wall slot, drop it — else the wall takes the BLE link
        and the orphaned handle wastes a ~5s reconnect-timeout on every call."""
        key = self._active_key()
        if not key or key not in slots:
            return
        d = getattr(self, "_device", None)
        if d is not None and hasattr(d, "disconnect"):
            try:
                self._run_device(d.disconnect())
            except Exception as e:
                logger.debug(f"relinquish active disconnect: {e}")
        self._device = self.mac = self._lan_ip = None
        self.forget_device_activity(key)
        logger.info("relinquished active device %s — claimed by the wall", key)

    def _wall_configs(self, slots: dict, cell: int) -> list:
        configs = []
        for mac, s in slots.items():
            cfg = {"mac": mac, "x": int(s.get("x", 0)), "y": int(s.get("y", 0)),
                   "size": int(s.get("size", cell))}
            if "width" in s:
                cfg["width"] = int(s["width"])
            if "height" in s:
                cfg["height"] = int(s["height"])
            configs.append(cfg)
        return configs

    def wall_configure(self, args: dict) -> dict:
        slots = args.get("slots") or {}
        cell = int(args.get("cell_size", 16) or 16)
        if not slots:
            self._drop_current_wall()
            self._wall_slots = {}
            return {"success": True, "wall": False}
        if (self._wall is not None and slots == self._wall_slots
                and getattr(self._wall, "is_connected", False)):
            return {"success": True, "wall": True}
        # G7: if the new layout OVERLAPS the current wall, reconfigure by delta —
        # keep the shared screens connected, only disconnect removed + connect
        # added (a full rebuild reconnected ALL members; HW: +14s for a 3rd).
        if self._wall_delta(slots, cell):
            return {"success": True, "wall": True}
        self._drop_current_wall()    # release the old wall before rebuilding
        self._relinquish_active_if_in(slots)   # G4: don't double-own a slot mac
        self._wall_slots = slots
        configs = self._wall_configs(slots, cell)

        async def _build():
            from divoom_lib.wall import DivoomWall
            wall = DivoomWall(configs, custom_logger=logger)
            await wall.connect()
            return wall

        try:
            self._wall = self._run_device(_build())
            return {"success": True, "wall": True}
        except Exception as e:
            logger.warning(f"wall_configure failed: {e}")
            self._wall = None
            return {"success": False, "error": str(e), "wall": False}

    def _wall_delta(self, slots: dict, cell: int):
        """G7: reuse the screens shared between the old and new wall. Returns True
        when it handled the reconfigure, or None to fall back to a full rebuild
        (no existing wall, or no overlap)."""
        old_wall = getattr(self, "_wall", None)
        old_macs = set(getattr(self, "_wall_slots", None) or {})
        new_macs = set(slots)
        if old_wall is None or not (old_macs & new_macs):
            return None
        self._relinquish_active_if_in(slots)   # G4 still applies on a delta
        configs = self._wall_configs(slots, cell)
        removed = old_macs - new_macs

        async def _rebuild():
            from divoom_lib.wall import DivoomWall
            old_by_mac = {s.device.mac: s.device for s in old_wall.devices}
            new_wall = DivoomWall(configs, custom_logger=logger)
            # Transplant the already-connected screens shared with the old wall —
            # ensure_connected short-circuits on a live link, so they fast-verify
            # (~0s) instead of a full reconnect. Only added screens connect.
            for slot in new_wall.devices:
                keep = old_by_mac.get(slot.device.mac)
                if keep is not None:
                    slot.device = keep
            for mac in removed:           # release the screens dropped from the layout
                dev = old_by_mac.get(mac)
                if dev is not None:
                    try:
                        await dev.disconnect()
                    except Exception:
                        pass
            await new_wall.connect()
            return new_wall

        try:
            self._wall = self._run_device(_rebuild())
            self._wall_slots = slots
            return True
        except Exception as e:
            logger.warning(f"wall delta reconfigure failed: {e}; full rebuild")
            self._drop_current_wall()
            return None
