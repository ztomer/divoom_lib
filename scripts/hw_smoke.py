#!/usr/bin/env python3
"""hw_smoke.py — drive a RUNNING daemon over its socket to exercise the BLE
stack on real hardware. Pure socket IPC (DaemonClient) — no BLE in THIS process,
so it can run from any context (incl. an unprivileged shell) without a TCC crash;
the daemon (a granted process) does all the Bluetooth.

Usage:
    divoom-control daemon            # in a BT-granted terminal (or the .app)
    python3 scripts/hw_smoke.py [--scan-timeout N] [--phase discover|connect|stress|all]

Style: Susan Kare icons + restrained Braun colours (matches ~/projects/scripts).
"""
from __future__ import annotations

import argparse
import json
import sys
import time

# ── kare style (TTY-aware) ──────────────────────────────────────────────
_TTY = sys.stdout.isatty()
_I_START, _I_OK, _I_ERR, _I_WARN, _I_STEP = ("→", "✓", "✗", "⚠", "·")
_RESET = "\033[0m" if _TTY else ""
_DIM = "\033[2m" if _TTY else ""
_BOLD = "\033[1m" if _TTY else ""
_GREEN = "\033[0;32m" if _TTY else ""
_RED = "\033[0;31m" if _TTY else ""
_YELLOW = "\033[0;33m" if _TTY else ""
_GRAY = "\033[0;90m" if _TTY else ""


def info(m): print(f"{_GRAY}{_I_START}{_RESET} {_DIM}{m}{_RESET}")
def step(m): print(f"{_GRAY}{_I_STEP}{_RESET} {m}")
def ok(m): print(f"{_GREEN}{_I_OK}{_RESET} {m}")
def err(m): print(f"{_RED}{_I_ERR}{_RESET} {m}")
def warn(m): print(f"{_YELLOW}{_I_WARN}{_RESET} {m}")
def hr(w=60): print(f"{_GRAY}{'─' * w}{_RESET}")
def section(t): print(); hr(); print(f"{_BOLD}  {t}{_RESET}"); hr()


def _client():
    from divoom_daemon.daemon_protocol import DaemonClient
    return DaemonClient()


def discover(c, scan_timeout: float) -> list:
    section("Discover")
    try:
        info(f"daemon-side scan ({scan_timeout:.0f}s)…")
        r = c.scan(timeout=scan_timeout)
        devs = r.get("devices") or r.get("results") or r.get("found") or []
        if devs:
            ok(f"{len(devs)} device(s):")
            for d in devs:
                name = d.get("name") if isinstance(d, dict) else d
                addr = d.get("address") if isinstance(d, dict) else ""
                step(f"{name}  {_GRAY}{addr}{_RESET}")
        else:
            warn(f"no devices advertising. raw={json.dumps(r)[:200]}")
        return devs
    except Exception as e:
        err(f"scan failed: {type(e).__name__}: {e}")
        return []


def _conn_state(c) -> dict:
    try:
        return c.get_connection_state() or {}
    except Exception:
        return {}


def _connect(c, mac: str, name: str) -> tuple[bool, float]:
    """Connect via the daemon; return (ok, seconds). R53: a real device connects
    fast; an asleep/held one fails CLEANLY within the bounded timeout (never hangs)."""
    t0 = time.monotonic()
    try:
        r = c.connect_device(mac=mac)
        dt = time.monotonic() - t0
        good = bool(r.get("success") and r.get("connected"))
        if good:
            ok(f"connected {name} in {dt:.1f}s  {_GRAY}{json.dumps(_conn_state(c))[:90]}{_RESET}")
        else:
            warn(f"{name} not connected in {dt:.1f}s — reason={r.get('reason') or r.get('error')}")
        return good, dt
    except Exception as e:
        dt = time.monotonic() - t0
        err(f"connect {name} raised in {dt:.1f}s: {type(e).__name__}: {e}")
        return False, dt


def cycles(c, devs: list) -> None:
    """Exercise the R53 connect/reconnect/eviction paths on real hardware."""
    section("Connect / reconnect / eviction cycles")
    targets = [(d.get("name"), d.get("address")) for d in devs if isinstance(d, dict) and d.get("address")]
    if not targets:
        warn("no connectable devices; skipping"); return
    a_name, a_mac = targets[0]
    info(f"primary: {a_name}")

    # 1. connect → disconnect → RECONNECT  (validates stop_notify-on-disconnect, C3:
    #    a leaked subscription would make the reconnect's start_notify fail)
    g1, _ = _connect(c, a_mac, a_name)
    if g1:
        try:
            c.disconnect_device(); step("disconnected")
        except Exception as e:
            err(f"disconnect raised: {e}")
        time.sleep(1.0)
        g2, _ = _connect(c, a_mac, a_name)
        ok("reconnect after clean disconnect OK (stop_notify path)") if g2 else err("RECONNECT FAILED — possible notify leak")

    # 2. switch to the OTHER device and back (validates single-owner eviction +
    #    transport-swap teardown — must NOT 16s-timeout on the re-grab)
    if len(targets) > 1:
        b_name, b_mac = targets[1]
        info(f"switching active → {b_name} (evicts {a_name})")
        gb, dtb = _connect(c, b_mac, b_name)
        if gb and dtb < 15:
            ok(f"eviction-switch to {b_name} clean ({dtb:.1f}s, no 16s stall)")
        elif gb:
            warn(f"switch worked but slow ({dtb:.1f}s)")
        info(f"switching back → {a_name}")
        _connect(c, a_mac, a_name)

    try:
        c.disconnect_device(); step("final disconnect")
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan-timeout", type=float, default=12.0)
    ap.add_argument("--phase", choices=["discover", "cycles", "all"], default="discover")
    args = ap.parse_args()

    section("Divoom HW smoke — daemon socket")
    try:
        c = _client()
    except Exception as e:
        err(f"cannot reach daemon: {e}"); return 2

    # status snapshot
    for name, call in (("connection_state", "get_connection_state"),
                       ("device_activity", "get_device_activity")):
        try:
            fn = getattr(c, call, None)
            if fn:
                step(f"{name}: {_DIM}{json.dumps(fn())[:200]}{_RESET}")
        except Exception as e:
            warn(f"{name} unavailable: {e}")

    devs = discover(c, args.scan_timeout)
    if args.phase in ("cycles", "all"):
        cycles(c, devs)
    print()
    ok("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
