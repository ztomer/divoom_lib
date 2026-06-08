"""divoom_menubar — macOS status bar agent for divoom-control."""

from divoom_menubar.menubar_client import MenubarClient
from divoom_menubar.menubar_client import (
    STATE_ACTIVE,
    STATE_IDLE,
    STATE_ERROR,
    format_status_title,
    status_color,
    hex_to_rgb01,
    open_notifications_command,
)

__all__ = [
    "MenubarClient",
    "STATE_ACTIVE",
    "STATE_IDLE",
    "STATE_ERROR",
    "format_status_title",
    "status_color",
    "hex_to_rgb01",
    "open_notifications_command",
]