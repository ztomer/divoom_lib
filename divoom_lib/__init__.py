# divoom_lib/__init__.py

from .exceptions import (
    DivoomError,
    DeviceAddressMissingError,
    CharacteristicConfigError,
    DeviceConnectionError,
)

def __getattr__(name):
    if name == "Divoom":
        from .divoom import Divoom
        return Divoom
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "Divoom",
    "DivoomError",
    "DeviceAddressMissingError",
    "CharacteristicConfigError",
    "DeviceConnectionError",
]
