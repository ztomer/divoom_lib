# Architecture gap scan #2 — 2026-06-13

Second scan, covering the seams the first pass (`ARCH_GAP_SCAN_2026-06.md`,
G1–G7) didn't: persistence/durability, the GUI RPC surface, the always-on
notification listener, and daemon lifecycle.

Status: **all four shipped** (A2 HW-verified; A1/A3/A4 unit-tested). See CHANGELOG
"Architecture gap scan #2 — A1–A4 (2026-06-13)".

---

## A1 — Inconsistent atomic writes → config corruption on crash (shipped)

After a real corruption incident `save_preset` was made atomic (R42 §5), but it
was the ONLY writer that was. Every other config writer wrote in place
(`open(w)` / `write_text` / `json.dump`), so a crash or power-loss mid-write
truncated the file and lost that config on next launch — credentials
(`config.ini`), wall slots, alarms, presets, hotchannel, lifecycle,
daemon_config, notification routing, the device cache.

**Fix:** a shared `divoom_lib/utils/atomic_io.py` — `atomic_write_text()`
(temp-in-same-dir + fsync + `os.replace`) and `atomic_write_config()` for
ConfigParser — applied across every writer.

## A4 — Cloud credentials in plaintext (shipped, file-perms approach)

`config.ini` (cloud email+password) and `auth_token.json` (token) were
world/group-readable. A local app legitimately needs to read them, so rather than
a heavy keychain migration the atomic writer takes a `mode` arg and writes those
files `0o600` (owner-only). Full macOS-Keychain storage remains a possible future
step but isn't warranted for a single-user local app.

## A3 — `gui_api._run_async` had no timeout (shipped)

`future.result()` had no deadline, so a wedged async chain (daemon stopped
answering, hung device op) blocked the pywebview JS-API thread forever — a frozen
button with no error. Now bounded at 120 s (well beyond any legit op incl. a 60 s
scan); on expiry it cancels the future and raises so the GUI surfaces an error.

## A2 — Live widgets didn't survive a daemon restart (shipped, HW-verified)

The daemon is the single owner; a crash/restart lost all `_live_tasks` and
streaming widgets silently stopped. Now the desired live-job set (mac, kind,
params) is persisted to `~/.config/divoom-control/live_jobs.json` on start and on
user-stop (atomic write); the daemon `rehydrate_live_jobs()` on boot restarts
them. A daemon teardown (`stop_all_live_jobs`) deliberately does NOT clear the
file, so a clean restart resumes; only a user stopping a widget removes it.
HW: started sysmon on the Ditoo, killed the daemon, respawned — the job resumed
and the device was streaming again.

---

## Noted, not actioned

- The daemon remains a single point of failure; A2 covers live jobs, but the
  active device / wall connection is rebuilt on the next client call (already the
  case). Fine for the single-owner model.
