# Planning: Round 10 — BLE notification mirroring (ANCS) _(2026-06-06)_

> Continues the R9 frontier list. R9 shipped screen orientation; the next
> headline APK feature (APK report §3, marked HIGH) is **notification
> mirroring** via `SPP_SET_ANDROID_ANCS`.

---

## §1 Verified protocol (decompiled, NOT the report's prose)

The APK report §3 claimed cmd `0x60` with payload `[type, R, G, B]`. **Both are
wrong** — confirmed against `SppProc$CMD_TYPE.java` + `CmdManager.java`:

- `SPP_SET_ANDROID_ANCS` = **80 = 0x50** (report said 0x60 — that's 96).
- There is no RGB-color payload. Two real wire forms:
  1. **`CmdManager.a0(int i9)`** (line 1085): payload = `[i9']`, a single byte,
     where `i9' = i9 + 1 if i9 >= 8 else i9` (one slot is skipped). This is the
     canonical "show the notification icon/blink for app type N" trigger.
  2. **`CmdManager.V(int type, String text)`** (line 935): payload =
     `[type, len, ...utf8(text)]`, `len = min(128, utf8.length)`. Shows the app
     icon plus a text string.
- `SPP_SECOND_SUPPORT_MORE_ANCS` (EXT 39) is a capability enable, not needed for
  a basic trigger.
- `SPP_SET_ANCS_NOTICE_PIC` = 60 (0x3C) is a separate (icon-picture) path — out
  of scope.

### App types (APK report §3, `NOTIFICATION_APPS`)

```
KAKAO=1 INSTAGRAM=2 SNAPCHAT=3 FACEBOOK=4 TWITTER=5 WHATSAPP=6
TEXT_MESSAGE=7 SKYPE=8 LINE=9 WECHAT=10 QQ=11 VIBER=12 MESSENGER=13 OK=14
```

> The `>=8 → +1` skip in `a0` means app types ≥ 8 are shifted by one on the wire.
> We replicate that exactly in the lib so the device lights the intended icon.

## §2 Scope (Kare + Rams)

**Ship:** a **manual notification trigger** — pick an app type (+ optional text)
and send. Honest, low-risk, demonstrates the headline feature, no new infra.

**Defer:** auto-sourcing real macOS notifications (Notification Center has no
clean public push-observer API; would need a helper app / private API / polling
the NotificationCenter SQLite db) — its own project, out of R10.

## §3 Step-by-step

**Step 1 — lib**
- `models/commands.py`: `"set android ancs": 0x50`.
- `models/constants.py` (+ `__init__` exports): `NOTIFICATION_APPS` dict.
- `divoom_lib/tools/notification.py` → `class Notification`:
  - `async show_notification(self, app_type: int) -> bool` → byte = `app_type+1
    if app_type >= 8 else app_type`; `send_command(0x50, [byte & 0xFF])`.
  - `async show_notification_text(self, app_type: int, text: str) -> bool` →
    `utf8 = text.encode()[:128]`; `send_command(0x50, [app_type & 0xFF, len(utf8),
    *utf8])`.
- Facade `divoom.py`: `self.notification = Notification(self)`.
- Tests (`tests/`): byte-exact for both forms incl. the ≥8 skip and a >128-byte
  truncation; facade-registered.

**Step 2 — GUI**
- `gui_api.py`: `send_notification(self, app_type, text="")` → if text, call
  `show_notification_text`, else `show_notification`. Coerce/validate type 1-14.
- `templates.js` Tools→Device: **Notification** card — app `<select>` (14 names),
  optional text input, **Send** button.
- `settings.js`: wire `#notif-send` → `send_notification`.
- Tests: bridge mock (text vs no-text path) + static UI presence.

**Step 3 — verify + close** (core rule): full suite green; update
SESSION_HANDOFF, CHANGELOG, this doc's outcome; commit (no push unless asked).

## §4 Risk

- Device-capability-dependent (not all models mirror notifications) → fire-and-
  forget, set-only, no read-back (task #20 still open).
- Exact icon set per app type is firmware-defined; the dropdown labels follow the
  APK's enum and can be relabeled without protocol change.

## §5 Implementation outcome — shipped 2026-06-06

Shipped the manual notification trigger (auto-source deferred as planned).

1. **lib**: `models/commands.py` `"set android ancs": 0x50`;
   `models/constants.py` `NOTIFICATION_APPS` (14 apps, exported);
   `divoom_lib/tools/notification.py` → `Notification.show_notification(type)`
   (icon-only, ≥8 wire skip) + `show_notification_text(type, text)`
   (`[type, len, *utf8≤128]`). Facade `d.notification`. 6 byte-exact tests.
2. **bridge** `gui_api.send_notification(app_type, text="")` — text→text form,
   else icon; refuses app_type outside 1-14. 2 tests.
3. **UI** Tools→Device **Notification** card: app `<select>` (14 names), optional
   text, Send. `settings.js` wiring. 3 static UI/exposure tests.

**Protocol corrections found by verifying the decompiled source** (the APK report
§3 prose was wrong on both): command is **0x50** (not 0x60), and there is **no
RGB payload** — the real forms are single-byte index (with the ≥8 skip) and
type+length+utf8 text.

Full suite: **538 passed / 0 failed / 73 skipped**.

Deferred (R11+): auto-source real macOS notifications; the cloud HTTP surface
(clock-face store, weather city search, pomodoro, white-noise, TTS); SD player /
game / drawing (lib→GUI exposure).
