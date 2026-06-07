# Planning: Round 14 — wire up the R13 follow-ups _(2026-06-07)_

> **Input:** "lets do what's possible. upate the docs" — execute the R13
> follow-ups that don't require real-hardware validation. All 4 items
> are lib/JS/packaging work; no device needed.

## Order

1. **§1 — Wire `TempWeatherCommand` → `divoom.weather`** (lib, ~30 LOC + tests)
2. **§2 — Custom routing JSON loader** (lib, ~20 LOC + tests)
3. **§3 — GUI Settings → Devices card** (JS/HTML/CSS, ~150 LOC + tests)
4. **§4 — `pyproject.toml` + console script** (packaging, ~50 LOC)
5. **§5 — Font inventory + consistency report** (survey, no code changes;
   user wants to see the list of fonts and the inconsistencies first)
6. **§6 — Remove all emojis from docs + code** (mechanical sweep)
7. Update SESSION_HANDOFF + CHANGELOG; push.

## §1 — Wire `TempWeatherCommand` → `divoom.weather`

**Current state:** `divoom_lib/system/temp_weather.py` defines
`TempWeatherCommand` (the 0x5F command) but is **not** wired to the
Divoom facade. `divoom.weather` doesn't exist. The class also has a
latent bug: it calls `self._divoom_instance.number2HexString()` which
is not a method on `Divoom` — the function lives at
`divoom_lib/utils/converters.py:number2HexString()`. So even
instantiating it manually would crash at first `update_temp_weather()`.

**Plan:**
- Create `divoom_lib/system/weather.py` — a proper `Weather` class with
  a clean public API: `set_temperature(celsius)`, `set_weather(weather_type)`,
  `update()` (sends the current values), and a fluent `send(temperature, weather_type)`
  convenience.
- Fix the latent `number2HexString` bug by using the module-level
  function directly.
- Wire to the facade: `divoom.py` adds `self.weather = Weather(self)`.
- Add to `divoom_lib/models/__init__.py` exports.
- Add a CLI command `divoom-control set-temperature C --weather TYPE` for symmetry with the other setters.
- Re-add `examples/set_weather.py` now that the wiring exists.
- Update `Capabilities.has_weather` consumers to call `d.weather.send(...)`.
- Tests: `tests/test_weather.py` — covers setter validation, wire-byte
  construction, and the public API.

## §2 — Custom routing JSON loader

**Current state:** `MacAppRouter` uses `DEFAULT_ROUTING` (14 hardcoded
rules). The plan doc said: "users can override by writing a JSON file
at `~/.config/divoom-control/notification_routing.json`" — but the
loader doesn't exist.

**Plan:**
- `MacAppRouter.__init__` (or a class method `MacAppRouter.loaded()`)
  reads `~/.config/divoom-control/notification_routing.json` (override
  via `DIVOOM_CONTROL_ROUTING` env var, same pattern as `DeviceRegistry`).
- JSON format is a list of `[substring, app_type]` pairs (or objects
  with `substr`/`app_type` keys — pick one and stick with it).
- Custom rules are **appended** to `DEFAULT_ROUTING` so the built-in
  defaults still cover the common case; user rules add on top.
- Corrupt-file tolerant (matches the `DeviceRegistry` pattern).
- `MacAppRouter.dump(path)` companion for the GUI's "Save routing"
  button.
- Tests: roundtrip, corrupt-file tolerance, env var override, custom
  rules don't shadow defaults (only add).

## §3 — GUI Settings → Devices card

**Current state:** §3's listener (`gui_api.start_notification_listener`)
is shipped; the JS side just has no UI to expose it. Per the planning
doc: "Settings → Devices card — Mirror macOS notifications toggle +
per-app enable checkboxes".

**Plan:**
- Add a "Notifications" subsection to the Settings → Devices card in
  `gui/web_ui/templates.js`.
- Toggle: "Mirror macOS notifications" → calls
  `api.start_notification_listener()` / `api.stop_notification_listener()`.
- Status badge: "Listening" / "Off" / "Error: <msg>".
- Per-app checkboxes for the 14 default rules (rendered from a static
  list — no need to round-trip the rules through Python for the toggle).
- "Save custom routing" button → opens a small text area for the JSON;
  calls `api.save_notification_routing(json_text)`.
- `gui_api.save_notification_routing(json_text) -> {ok, error?}` —
  validates + writes the JSON to the registry path; reloads the router.
- `gui_api.get_notification_listener_status() -> {running, db_path, error?}` —
  exposed to JS for the live status badge.
- `gui/web_ui/settings.js` — wire the new event-delegated handlers
  (matches R9 pattern).
- `gui/web_ui/settings.css` — segmented-pill rules already cover the
  Devices card; no new CSS needed unless we add a custom-control style.
- Tests: `tests/test_gui_api.py` — `save_notification_routing` with
  valid/invalid JSON; `get_notification_listener_status` roundtrip.
- Tests: `tests/test_round6_layout_and_exposure.py` — Devices card now
  contains the "Notifications" subsection + the 14 per-app checkboxes.

## §4 — `pyproject.toml` + console script

**Current state:** no `pyproject.toml`, no `setup.py`. The shell
wrapper `./divoom-control` is a workaround.

**Plan:**
- Create a minimal `pyproject.toml` using setuptools (PEP 621 metadata).
- `[project.scripts]` defines `divoom-control = divoom_lib.cli:main`.
- `[project.optional-dependencies]` for test/CI/dev dependencies
  (mirrors `requirements.txt`).
- Verify `pip install -e .` works and produces a real
  `divoom-control` console script.
- Keep the shell wrapper `./divoom-control` for users who run from
  the working tree without installing (delete is also fine — decide
  at the end).
- No new tests needed; the CLI's `tests/test_cli.py` already
  exercises the entry point via `python -m divoom_lib.cli`.

## Kill criterion

None of the 4 sections hit a wall that requires user judgment. They
all either work (lib) or are JS wiring (deterministic, event-delegated
to existing bridge). The only piece that needs the user to validate
is the visual layout of the Settings → Devices card after §3.

## Open follow-ups (carry to R15+)

- **R12 §A visual pass** (user-run `python3 gui/gui_main.py`).
- **R12 §B hardware verification** (user-run).
- **Task #20** — get_* read-backs gate SD player UI and everything else.
- **Channel-switch hardware bug** (Divoom Max).
- **Timeplan hardware verification** (deferred R12 §D).
- **Cloud HTTP round** (auth broken).
- **Pywebview drag fix** (#1820 still open).
- **GUI §3 visual pass** (after R14 lands).

## Outcome / what shipped (R14 §1-§4)

**Status:** all four R13 follow-up sections complete. **+74 tests**,
suite now 829 passed / 75 skipped. Ready to commit + push.

### §1 — `Weather` facade — SHIPPED

- New `divoom_lib/system/weather.py` with a clean `Weather` class.
  Methods: `set(temperature, weather_type)`, `set_temperature(t)`,
  `set_weather(wt)`, with internal state tracking. Range -127..128,
  negative encoding via `(256 + c) & 0xFF`.
- Wired to the Divoom facade as `self.weather = Weather(self)` in
  `divoom_lib/divoom.py:113`.
- The old `TempWeatherCommand` in `divoom_lib/system/temp_weather.py`
  is now a thin shim that delegates to `Weather`. Fixes the latent
  bug where the old class called `self._divoom_instance.number2HexString()`
  (a function in `divoom_lib/utils/converters.py`, not a method on
  Divoom — would have crashed at first call).
- CLI `set-temperature` subcommand added with `--weather {clear,cloudy,
  thunderstorm,rain,snow,fog}` choice.
- Re-added `examples/set_weather.py` (R13 §2 had deferred this).
- Tests: `tests/test_weather.py` (21 tests — encoding matrix,
  wire bytes for positive/negative/zero, range validation, hot
  setters, shim regression, facade wiring). `tests/test_cli.py` +4
  tests (handler + dispatch + out-of-range + capability gate).

### §2 — Custom routing JSON loader — SHIPPED

- `load_routing_table(path=None)` /
  `save_routing_table(rules, path=None)` in
  `gui/macos_notifications.py`. Path resolution: env var
  `DIVOOM_CONTROL_ROUTING` first, then
  `~/.config/divoom-control/notification_routing.json` (same
  XDG-convention dir as `devices.json`).
- Corrupt-file tolerant: invalid JSON / non-list root / no valid
  entries → warn + fall back to `DEFAULT_ROUTING`. App_type
  validation: must be in `NOTIFICATION_APPS` (1-14); bad entries
  dropped with a warning, not crashed.
- Atomic save via `.tmp` + `replace()` — partial writes can't
  corrupt the live config.
- `MacAppRouter.from_file(path)` classmethod.
- `MacNotificationMonitor.__init__` gains a `routing_path` arg
  (default: load from the user's custom file; fall back to
  defaults silently if it's corrupt or missing).
- Tests: `tests/test_routing_loader.py` (19 tests — load with
  valid/missing/corrupt/non-list/empty file, save roundtrip,
  atomic write, env var override, validation, MacAppRouter
  integration).

### §3 — GUI Settings → Devices card — SHIPPED

- New "macOS Notifications" card under Settings → Devices in
  `gui/web_ui/templates.js` (right after the existing manual
  "Notification" card). Toggle, live status pill (running /
  stopped / error / unsupported), counters, and a routing JSON
  editor (textarea + Save / Reset to defaults).
- `gui_api` adds:
  - `get_notification_listener_status()` — rich status dict
    (`platform_supported`, `running`, `db_path`, `routing_path`,
    `rules`, `counters {seen, routed, dropped}`, `error`).
  - `save_notification_routing(json_text)` — parses, saves,
    **hot-reloads** the running monitor's router (no listener
    restart), returns `{rules, error}`.
- JS in `gui/web_ui/settings.js`: 5s polling for live counters,
  dirty-state detection on the textarea, toast on errors.
- CSS in `gui/web_ui/settings.css`: `.status-pill` with 4 states
  (running / stopped / error / unsupported), monospace
  status detail block, details/summary toggle styles. All
  fonts use `var(--font-mono)` (R14 §5 invariant).
- **Decision:** chose JSON editor over per-app checkboxes
  because (a) the rules ARE JSON, (b) a checkbox matrix would
  be a parallel state to keep in sync, (c) developers can paste
  rules from a config file, (d) keeps the card under 80 lines.
- Tests: `tests/test_gui_api.py` +5 tests (status shape,
  unsupported-off-macos, save roundtrip + hot-reload, bad
  JSON, all-bad entries silently dropped).

### §4 — `pyproject.toml` — SHIPPED

- First packaging file in the repo. setuptools backend
  (`>=68`), PEP 621 metadata, version `0.14.0`,
  `requires-python = ">=3.10"`.
- Core deps from `requirements.txt`: `bleak`, `aiohttp`,
  `pillow`, `tomli`/`tomli-w`. `[gui]` extra: `pywebview` +
  `pyobjc-framework-Cocoa` (darwin-gated). `[test]` and
  `[dev]` extras for the standard two-bucket setup.
- `[project.scripts]` registers `divoom-control =
  divoom_lib.cli:main` — real console script.
- `tool.setuptools.package-data` ships the
  `libdivoom_compact.dylib` + `web_ui/*` with the `gui`
  package so the installed package is self-contained.
- Verified `pip install -e .` succeeds on Python 3.14,
  and the resulting `/opt/homebrew/bin/divoom-control`
  entry point works (`divoom-control --help` lists
  `set-temperature` correctly).
- **The legacy shell wrapper `./divoom-control` is kept**
  for in-tree dev without an editable install.
- Tests: `tests/test_pyproject.py` (12 tests — TOML valid,
  metadata sane, entry point declared and callable, deps
  match `requirements.txt`, GUI extra is darwin-gated,
  package discovery + package-data, shell wrapper still
  present and invokes the python module).

### Cross-cutting decisions

- **Errors → warnings, not crashes.** Both the routing loader
  and `save_routing_table` prefer to log a warning and fall
  back to a safe default. A bad user config should never take
  down the listener; a bad user config should never block a
  save.
- **Hot-reload over restart.** The routing JSON is editable
  while the listener runs; save() replaces the monitor's
  router in place. Restarting the polling thread is more
  work, more disruptive, and unnecessary.
- **Atomics for the routing save.** Routed to a `.tmp` sibling
  + `Path.replace()` (POSIX-atomic). A crash mid-write can't
  leave a half-written JSON file that the next start would
  reject.
- **Latent bug fixed in the process.** The `TempWeatherCommand`
  → `number2HexString()` call would have crashed at first use
  (the function is a module-level function, not a method on
  the Divoom instance). The new `Weather` class doesn't use it
  at all — encoding is a one-line `(256 + c) & 0xFF` expression.

### Verified

- `python3 -m pytest` → **829 passed, 75 skipped, 0 failed**
  in ~92s.
- `pip install -e .` → clean install.
- `divoom-control --help` → entry point works, lists
  `set-temperature` correctly.
- `divoom-control set-temperature --help` → new subcommand
  help renders with the right `--weather` choices.
