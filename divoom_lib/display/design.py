"""Set design (0xBD) sub-cmd dispatch (Round 4 — Phase E.6).

The 0xBD command is a multi-purpose design dispatcher. Each
sub-command has its own payload format. Sourced from
futpib/src/protocol/extended_command.rs:11-15 and
hass-divoom/devices/ditooMic.py:15-27 (EQ 0x1E).

Sub-commands implemented:
  0x14  set_user_define_time   (futpib) — payload format TBD per Divoom docs
  0x15  get_user_define_time   (futpib)
  0x1E  set_eq                 (Ditoo-Mic)  — 3 bytes [dynamic, mode, stream]
  0x26  set_language           (futpib)    — 1 byte language code

Reference: https://github.com/futpib/divoom-ditoo-pro-controller
           https://github.com/d03n3rfr1tz3/hass-divoom
"""
from __future__ import annotations

import logging

from divoom_lib.sender_protocol import CommandSender
from divoom_lib.models import COMMANDS

logger = logging.getLogger("divoom_lib")

# Sub-command IDs (per futpib extended_command.rs + hass-divoom ditoomic.py)
SUB_USER_DEFINE_TIME_SET = 0x14
SUB_USER_DEFINE_TIME_GET = 0x15
SUB_EQ = 0x1E
SUB_LANGUAGE = 0x26


class Design:
    """0xBD sub-cmd dispatcher.

    Usage::

        await divoom.design.set_eq(dynamic=True, mode=0, stream=False)
        await divoom.design.set_language(lang=0)
    """

    def __init__(self, divoom: CommandSender):
        self.communicator = divoom
        self.logger = divoom.logger

    async def _send_subcmd(self, subcmd: int, args: list) -> bool:
        """Send a 0xBD command with the given subcmd + args."""
        full_args = [subcmd] + args
        return await self.communicator.send_command(
            COMMANDS["set design"], full_args
        )

    async def set_eq(
        self, dynamic: bool = False, mode: int = 0, stream: bool = False
    ) -> bool:
        """Set the EQ/equalizer (0xBD 0x1E, Ditoo-Mic).

        Args:
            dynamic: dynamic EQ mode (1) vs static (0).
            mode: EQ mode 0-7 (specific to firmware).
            stream: streaming mode (1) vs single-shot (0).
        """
        self.logger.info(
            f"Setting EQ dynamic={dynamic} mode={mode} stream={stream} (0xBD 0x1E)..."
        )
        args = [
            0x01 if dynamic else 0x00,
            int(mode) & 0xFF,
            0x01 if stream else 0x00,
        ]
        return await self._send_subcmd(SUB_EQ, args)

    async def set_language(self, lang: int) -> bool:
        """Set the device language (0xBD 0x26).

        Args:
            lang: 0=English, 1=Chinese, etc. (per Divoom firmware).
        """
        self.logger.info(f"Setting language to {lang} (0xBD 0x26)...")
        return await self._send_subcmd(SUB_LANGUAGE, [int(lang) & 0xFF])

    async def set_user_define_time(
        self, hour: int, minute: int, second: int = 0
    ) -> bool:
        """Set user-define time (0xBD 0x14).

        Payload: [hour, minute, second] — exact format per Divoom
        firmware. Verified by futpib (extended_command.rs:11) but
        not live-tested on Timoo.
        """
        self.logger.info(
            f"Setting user-define time {hour:02d}:{minute:02d}:{second:02d} (0xBD 0x14)..."
        )
        return await self._send_subcmd(
            SUB_USER_DEFINE_TIME_SET,
            [hour & 0xFF, minute & 0xFF, second & 0xFF],
        )

    async def get_user_define_time(self) -> dict | None:
        """Get user-define time (0xBD 0x15)."""
        self.logger.info("Getting user-define time (0xBD 0x15)...")
        response = await self.communicator.send_command_and_wait_for_response(
            COMMANDS["set design"], [SUB_USER_DEFINE_TIME_GET]
        )
        if not response or len(response) < 3:
            return None
        return {
            "hour": response[0],
            "minute": response[1],
            "second": response[2] if len(response) > 2 else 0,
        }
