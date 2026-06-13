"""py2app build recipe → a self-contained ``Divoom.app``.

    python setup_app.py py2app          # build dist/Divoom.app
    (driven by scripts/build_release.sh in a dedicated build venv)

What ships: the four runtime packages (divoom_lib / divoom_daemon / divoom_gui /
divoom_menubar) and their package data (web_ui/, fonts/, the native dylib), plus
the third-party runtime deps (bleak, aiohttp, Pillow, pywebview, pyobjc).

What does NOT ship — enforced by `excludes` + listing only the runtime packages:
references/ (the decompiled APK + third-party reference projects), tests/,
scripts/, examples/, docs/. The app must never bundle the reverse-engineered APK.

The Info.plist declares the Bluetooth usage descriptions so the bundle is its own
TCC "responsible process" and macOS shows the normal Allow-Bluetooth prompt
(instead of crashing on first CoreBluetooth touch). See scripts/make_app_bundle.sh
for the background.
"""
from setuptools import setup

VERSION = "0.15.1"
BT_DESC = ("Divoom Control uses Bluetooth to discover and control your Divoom "
           "pixel display.")
AE_DESC = ("Divoom Control reads the now-playing track from Music and Spotify to "
           "show album art on your screen.")

APP = ["divoom_gui/gui_main.py"]

OPTIONS = {
    "argv_emulation": False,
    # Listing the runtime packages as `packages` copies each as a real directory
    # tree (not byte-compiled into the zip), so web_ui/, fonts/ and the native
    # dylib travel with their package and resolve via Path(__file__).parent.
    "packages": [
        "divoom_lib", "divoom_daemon", "divoom_gui", "divoom_menubar",
        "bleak", "aiohttp", "PIL", "webview",
        "objc", "Foundation", "AppKit", "CoreBluetooth", "WebKit", "Quartz",
    ],
    "includes": ["divoom_lib.cli"],   # spawned via -m, so pull it in explicitly
    # Belt-and-suspenders: never let the reverse-engineered APK / dev trees in.
    "excludes": [
        "references", "tests", "scripts", "examples", "docs",
        "pytest", "_pytest", "py2app",
    ],
    "plist": {
        "CFBundleName": "Divoom",
        "CFBundleDisplayName": "Divoom Control",
        "CFBundleIdentifier": "com.divoom.control",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "LSUIElement": False,
        "NSBluetoothAlwaysUsageDescription": BT_DESC,
        "NSBluetoothPeripheralUsageDescription": BT_DESC,
        "NSAppleEventsUsageDescription": AE_DESC,
    },
}

setup(
    name="Divoom",
    app=APP,
    version=VERSION,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
