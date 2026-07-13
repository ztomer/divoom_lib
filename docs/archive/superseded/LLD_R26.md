# R26 Low-Level Design — Three-Layer Channel-Switch API

## 1. Overview

**Goal:** Implement weather channel push end-to-end through all three layers:
library (`divoom_lib/`) → GUI (`divoom_gui/`) → daemon (`divoom_daemon/`).

**Design principle:** The APK is ground truth. All byte formats follow the
decompiled official app. The existing `DaemonDeviceProxy` + `device_call`
dispatch handles daemon routing without any new registry entries.

---

## 2. Layer 1: Library (`divoom_lib/`)

### 2.1 `Display.set_temperature_channel()` — new method

**File:** `divoom_lib/display/__init__.py`

```python
async def set_temperature_channel(
    self,
    celsius: bool = True,
    color: str | None = "#ffffff",
) -> bool:
    """Switch to TEMPRETURE display mode (channel 1, APK canonical).

    Wire format: 0x45 [0x01, temp_type, R, G, B, 0x00]
    Does NOT push temperature/weather data — use Weather.set() for that.
    """
    temp_type = 0 if celsius else 1
    rgb = self.communicator.convert_color(color or "#ffffff")
    payload = [0x01, temp_type, rgb[0], rgb[1], rgb[2], 0x00]
    return await self.communicator.send_command("set light mode", payload)
```

### 2.2 `Display.set_clock_rich()` — new method

```python
async def set_clock_rich(
    self,
    style: int = 0,
    twentyfour: bool = True,
    humidity: bool = False,
    weather: bool = False,
    date: bool = False,
    color: str | None = "#ffffff",
) -> bool:
    """Set CLOCK channel using the APK C2() 10-byte format.

    Wire format: 0x45 [0x00, time_type, time_show_mode, 1,
                       humidity, weather, date, R, G, B]
    APK-canonical overlay positions (differs from show_clock()).
    """
    rgb = self.communicator.convert_color(color or "#ffffff")
    payload = [
        0x00, int(twentyfour), style & 0xFF, 0x01,
        int(humidity), int(weather), int(date),
        rgb[0], rgb[1], rgb[2],
    ]
    return await self.communicator.send_command("set light mode", payload)
```

### 2.3 `TEMPRETURE_CHANNEL` constant — new alias

**File:** `divoom_lib/models/constants.py`

```python
TEMPRETURE_CHANNEL = 0x01   # APK name (alias for LIGHTNING_CHANNEL_NUMBER)
```

### 2.4 Wire format reference

```
TEMPRETURE channel switch     0x45 [0x01, temp_type,    R,    G,    B,  0x00]
CLOCK rich config             0x45 [0x00, time_type,  style, 0x01, hum, wth, dat, R, G, B]
Weather data push             0x5F [signed_temp, weather_type]
```

The APK is ground truth — device firmware follows the APK layout exactly.

---

## 3. Layer 2: GUI (`divoom_gui/`)

### 3.1 `WidgetsApi.push_weather()` — fix existing method

**File:** `divoom_gui/api/widgets.py`

Current: sends 0x5F only — device may not display data.

Fixed — two-step sequence inside the daemon proxy call:

```python
def push_weather(self) -> bool:
    from divoom_lib.system.weather import Weather
    from divoom_lib.weather_provider import get_weather
    from divoom_lib.models import COMMANDS

    async def _push(d):
        info = await get_weather()
        # Step 1: switch to TEMPRETURE channel, white text, Celsius
        await d.send_command(
            COMMANDS["set light mode"],
            [0x01, 0x00, 0xFF, 0xFF, 0xFF, 0x00],
        )
        # Step 2: push temperature + weather data
        return await Weather(d).set(info.temperature_c, info.weather_type)

    return self._tool_call(_push, "weather")
```

The `d` parameter is a `DaemonDeviceProxy`. Its `send_command()` routes through
the daemon via `device_call("send_command", ["set light mode", [0x01, ...]])`.

### 3.2 `gui_api.py` exposure — add `set_temperature_channel()` bridge method

**File:** `divoom_gui/gui_api.py`

```python
def set_temperature_channel(self, celsius: bool = True, color: str = "#ffffff") -> bool:
    """Switch device to TEMPRETURE display mode (GUI bridge)."""
    return self.widgets.set_temperature_channel(celsius, color)

def set_clock_rich(
    self, style: int = 0, twentyfour: bool = True,
    humidity: bool = False, weather: bool = False,
    date: bool = False, color: str = "#ffffff",
) -> bool:
    """Set clock with APK-canonical overlay toggles (GUI bridge)."""
    return self.lighting.set_clock_rich(style, twentyfour, humidity, weather, date, color)
```

### 3.3 `WidgetsApi.set_temperature_channel()` — new bridge method

Calls `Display.set_temperature_channel()` through the daemon proxy:

```python
def set_temperature_channel(self, celsius: bool = True, color: str = "#ffffff") -> bool:
    async def _call(d):
        from divoom_lib.models import COMMANDS
        temp_type = 0 if celsius else 1
        rgb = d.convert_color(color)
        payload = [0x01, temp_type, rgb[0], rgb[1], rgb[2], 0x00]
        return await d.send_command(COMMANDS["set light mode"], payload)
    return self._tool_call(_call, "set_temperature_channel")
```

### 3.4 Weather card — add "Show on Weather Display" button

**File:** `divoom_gui/web_ui/templates_widgets.js`

Add a button to the weather card body, below the preview:

```html
<div class="weather-card-actions" style="display:flex; gap:6px; margin-top:6px;">
    <button class="btn btn-sm" onclick="pushWeatherToDevice()">
        Push to Device
    </button>
</div>
```

**File:** `divoom_gui/web_ui/widgets.js`

JS function to call the bridge:

```javascript
function pushWeatherToDevice() {
    if (!window.pywebview?.api?.push_weather) return;
    window.pywebview.api.push_weather().then(ok => {
        if (ok) showToast("Weather pushed", "success", " BLE");
        else showToast("Weather push failed", "error");
    });
}
```

Also rename the existing auto-push call to use the same function for consistency.

### 3.5 Clock panel — overlay toggle checkboxes (for `set_clock_rich()`)

**File:** `divoom_gui/web_ui/index.html`

In the clock panel (`#panel-clock`), add overlay toggles below the clock face
grid:

```html
<div class="clock-overlay-toggles" style="display:flex; gap:10px; margin-top:8px;">
    <label><input type="checkbox" id="clock-humidity"> Humidity</label>
    <label><input type="checkbox" id="clock-weather-overlay" checked> Weather</label>
    <label><input type="checkbox" id="clock-date"> Date</label>
    <button class="btn btn-sm" onclick="applyClockRich()">Apply</button>
</div>
```

**File:** `divoom_gui/web_ui/channels_core.js`

```javascript
function applyClockRich() {
    if (!window.requireDevice()) return;
    const style = /* get from clock face selection */;
    const twentyfour = /* get from state */;
    const humidity = document.getElementById("clock-humidity")?.checked || false;
    const weather = document.getElementById("clock-weather-overlay")?.checked || false;
    const date = document.getElementById("clock-date")?.checked || false;
    const color = document.getElementById("clock-color-input")?.value || "#ffffff";
    if (window.pywebview?.api?.set_clock_rich) {
        window.pywebview.api.set_clock_rich(style, twentyfour, humidity, weather, date, color)
            .then(ok => {
                if (ok) showToast("Clock updated", "success", " BLE");
                else showToast("Clock update failed", "error");
            });
    }
}
```

---

## 4. Layer 3: Daemon (`divoom_daemon/`)

### 4.1 No new daemon commands needed

The existing dispatch handles everything automatically:

```
JS: pywebview.api.push_weather()
  → gui_api.push_weather()                    [gui_api.py]
  → WidgetsApi.push_weather()                 [widgets.py]
  → DaemonDeviceProxy.__call__()              [daemon_bridge.py:260]
     builds method="send_command"
  → DaemonClient.device_call("send_command",  [daemon_protocol.py:160]
       ["set light mode", [0x01, 0x00, ...]])
  → SocketServer → DivoomDaemon.handle_command [daemon.py:105]
  → DeviceOwner.device_call(args)             [device_owner.py:179]
     method="send_command"
  → DivoomConnection.send_command(...)        [connection.py:119]
  → BLETransport.send_payload(...)            [ble_transport.py:308]
```

No registry changes. No new `DivoomDaemon` methods. The proxy handles routing.

### 4.2 BLE interleaving risk

The two-step weather sequence (0x45 channel switch + 0x5F data push) executes
sequentially inside a single daemon proxy call, on the daemon's single-threaded
device event loop. The existing `_write_lock` provides 50ms minimum inter-write
spacing. No concurrent device operations are possible through `DeviceOwner`.

**Risk: negligible.** A daemon-level command queue is deferred to R27 for
multi-phase protection (0x8B animation sequences), not needed for the
two-step weather push.

---

## 5. Test Strategy

### 5.1 Library-level tests (in `tests/test_e2e_mock_device.py`)

```python
async def test_temperature_channel_switch_apk_format():
    """R26: Display.set_temperature_channel() sends APK-canonical 0x45."""
    dev = MockCommunicator()
    disp = Display(dev)
    await disp.set_temperature_channel(celsius=True, color="#ffffff")
    cmd = dev.last_command
    assert cmd["command_id"] == COMMANDS["set light mode"]
    assert list(cmd["payload"]) == [0x01, 0x00, 0xFF, 0xFF, 0xFF, 0x00]

async def test_temperature_channel_fahrenheit_red():
    """R26: Fahrenheit + red produce correct bytes."""
    dev = MockCommunicator()
    disp = Display(dev)
    await disp.set_temperature_channel(celsius=False, color="#FF0000")
    cmd = dev.last_command
    assert list(cmd["payload"]) == [0x01, 0x01, 0xFF, 0x00, 0x00, 0x00]

async def test_clock_rich_apk_format():
    """R26: Display.set_clock_rich() sends APK C2() 0x45."""
    dev = MockCommunicator()
    disp = Display(dev)
    await disp.set_clock_rich(style=3, twentyfour=True,
                              humidity=True, weather=False, date=True)
    cmd = dev.last_command
    assert cmd["command_id"] == COMMANDS["set light mode"]
    assert list(cmd["payload"]) == [
        0x00, 0x01, 0x03, 0x01, 0x01, 0x00, 0x01, 0xFF, 0xFF, 0xFF,
    ]
```

### 5.2 GUI-level tests (in `tests/test_e2e_mock_device.py`)

Re-add the daemon-proxy roundtrip test with correct APK byte order:

```python
async def test_weather_push_switches_channel_before_data():
    """R26: push_weather sends 0x45 (APK) before 0x5F through daemon proxy."""
    dev = MockCommunicator()
    disp = Display(dev)
    proxy = DaemonDeviceProxy(...)  # or test via WidgetsApi._tool_call
    # ... assert 0x45 [0x01, 0x00, 0xFF, 0xFF, 0xFF, 0x00] precedes 0x5F
```

### 5.3 Expected counts

| Suite | Before | After | Delta |
|-------|--------|-------|-------|
| E2E mock device | 15 | 18 | +3 |
| Full suite | 1022 | 1025 | +3 |

---

## 6. Implementation Order

| Step | File | Change |
|------|------|--------|
| **P1** | `divoom_lib/models/constants.py` | Add `TEMPRETURE_CHANNEL = 0x01` |
| **P2** | `divoom_lib/display/__init__.py` | Add `set_temperature_channel()`, `set_clock_rich()` |
| **P3** | `divoom_gui/api/widgets.py` | Fix `push_weather()` — two-step sequence with channel switch |
| **P4** | `divoom_gui/gui_api.py` | Add `set_temperature_channel()` and `set_clock_rich()` bridge methods |
| **P5** | `divoom_gui/web_ui/templates_widgets.js` | Add "Push to Device" button to weather card |
| **P6** | `divoom_gui/web_ui/widgets.js` | Add `pushWeatherToDevice()` JS function |
| **P7** | `tests/test_e2e_mock_device.py` | Add 3 new tests, re-add channel-switch test |

---

## 7. Non-goals (R27+)

- **Daemon-level command queue** — multi-phase 0x8B protection.
- **LAN path for channel switches** — different mechanism, deferred.
- **`show_clock()` overlay reorder** — would break backward compat.
  `set_clock_rich()` provides the APK layout alongside.
- **Clock face overlay toggles in JS** — the HTML/JS for overlay
  checkboxes is sketched but deferred to P2 to keep R26 focused on
  the weather channel fix.
