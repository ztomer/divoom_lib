"""Shared pytest configuration.

Several ``test_*_functions.py`` modules are *hardware integration* tests: their
``asyncSetUp`` calls ``discover_device()`` which spins up a real ``BleakScanner``
/ CoreBluetooth central manager. On a machine without granted Bluetooth
permission (e.g. CI, or a sandboxed shell) that triggers a macOS TCC privacy
violation which **aborts the whole interpreter**, taking the rest of the suite
down with it.

To keep the unit-test suite runnable and give a real pass/fail baseline, these
hardware tests are skipped by default. Run them against a real device with::

    pytest --run-hardware
"""

import os
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DYLIB = _REPO_ROOT / "gui" / "libdivoom_compact.dylib"
_BUILD_SCRIPT = _REPO_ROOT / "scripts" / "build_libdivoom.sh"
_C_SOURCES = [
    _REPO_ROOT / "gui" / "compact.c",
    _REPO_ROOT / "divoom_lib" / "native_src" / "downsample.c",
    _REPO_ROOT / "divoom_lib" / "native_src" / "image_encode.c",
    _REPO_ROOT / "divoom_lib" / "native_src" / "image_encode_32.c",
]


def _dylib_is_stale() -> bool:
    """True if the dylib is missing or older than any C source."""
    if not _DYLIB.exists():
        return True
    lib_mtime = _DYLIB.stat().st_mtime
    return any(src.exists() and src.stat().st_mtime > lib_mtime for src in _C_SOURCES)


def pytest_configure(config):
    """Rebuild the native dylib if it's missing or stale, so the dual-impl
    correctness suite (tests/test_encoder_both_impls.py) actually exercises the
    C encoder instead of silently skipping it. This is the anti-drift guarantee:
    a C-source change can't ship untested. No-ops cleanly if there's no compiler.
    Set DIVOOM_SKIP_NATIVE_BUILD=1 to opt out.
    """
    if os.environ.get("DIVOOM_SKIP_NATIVE_BUILD"):
        return
    if not _BUILD_SCRIPT.exists() or not _dylib_is_stale():
        return
    try:
        subprocess.run(
            ["bash", str(_BUILD_SCRIPT)],
            cwd=str(_REPO_ROOT), check=True,
            capture_output=True, text=True, timeout=120,
        )
        print("conftest: rebuilt libdivoom_compact.dylib (was missing/stale)")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        # No compiler / build failure: the native tests will skip; Python still runs.
        print(f"conftest: native dylib build skipped ({type(e).__name__})")


# Modules whose tests require a physically present Divoom device (they call
# divoom_lib.utils.discovery.discover_device() in setUp and connect over BLE).
HARDWARE_TEST_MODULES = frozenset({
    "test_alarm_functions",
    "test_brightness",
    "test_channel_rotation",
    "test_channel_switching",
    "test_display_functions",
    "test_game_functions",
    "test_light_functions",
    "test_music_functions",
    "test_push_protocol_diagnostic",
    "test_sleep_functions",
    "test_system_functions",
    "test_timeplan_functions",
    "test_tool_functions",
    "test_tool_timer_functions",
})


def pytest_addoption(parser):
    parser.addoption(
        "--run-hardware",
        action="store_true",
        default=False,
        help="Run integration tests that require a physically connected Divoom device.",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-hardware"):
        return
    skip_hw = pytest.mark.skip(
        reason="requires a physical Divoom device; run with --run-hardware"
    )
    for item in items:
        if item.module.__name__.split(".")[-1] in HARDWARE_TEST_MODULES:
            item.add_marker(skip_hw)
