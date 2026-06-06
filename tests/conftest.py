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

import pytest

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
