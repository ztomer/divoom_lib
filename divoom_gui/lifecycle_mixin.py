"""Lifecycle settings surfaced to the web UI (pywebview js_api).

The dashboard, the native menu-bar agent, and the device daemon share a
lifecycle governed by two flags in ``~/.config/divoom-control/config.ini``:

  * ``keep_daemon_alive`` — keep the daemon (+ menu bar) running after the
    dashboard quits (independent lifecycles). Default off = shared lifecycle.
  * ``quit_menubar_on_exit`` — when the lifecycle is shared, also terminate the
    native menu-bar agent on quit so it doesn't orphan to launchd. Default on.

These must live on the top-level API class (a mixin, not a composed sub-API) so
pywebview exposes them directly as ``api.get_*()`` — nested objects aren't
bridged. The storage/decision logic lives in :mod:`divoom_lib.lifecycle_config`.
"""
from __future__ import annotations


class LifecycleSettingsMixin:
    """get/set for the two menu-bar/daemon lifecycle flags."""

    def get_keep_daemon_alive(self) -> bool:
        from divoom_lib.lifecycle_config import get_keep_daemon_alive
        return get_keep_daemon_alive()

    def set_keep_daemon_alive(self, value) -> bool:
        from divoom_lib.lifecycle_config import set_keep_daemon_alive
        return set_keep_daemon_alive(bool(value))

    def get_quit_menubar_on_exit(self) -> bool:
        from divoom_lib.lifecycle_config import get_quit_menubar_on_exit
        return get_quit_menubar_on_exit()

    def set_quit_menubar_on_exit(self, value) -> bool:
        from divoom_lib.lifecycle_config import set_quit_menubar_on_exit
        return set_quit_menubar_on_exit(bool(value))
