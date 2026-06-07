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
