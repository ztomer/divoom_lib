# PLANNING_ROUND61 — release cut + doc pruning + Timoo re-verify + Cloud HTTP + coverage gate

**Date:** 2026-07-13
**Head before round:** `6f9327f` (R60 + follow-up CI fix; working tree clean)
**Carried from R60:** roadmap's 7 items DONE at the remote-verifiable level; checkpoint
`v0.22.8`. Follow-up CI fix (`tests/test_gui_api.py::test_connect_single_device`) committed.

## Goal

Five tasks, in this order:

1. **Commit + tag a release** of the R60 + CI-fix work.
2. **Prune stale docs** — `docs/` has accumulated many executed/obsolete planning files
   that are now noise; remove or consolidate so the tree reflects reality.
3. **Re-verify Timoo-light-4** for R60 #2 (cloud-decode `show_image` push + no-stick) —
   device was out of BLE range during R60; user reports it is available now.
4. **Divoom Cloud HTTP work** — the long-deferred round: fix `UserNewGuest` `RC=10`
   (auth flow changed) and stand up a cloud HTTP client with a **clock-face store**
   endpoint + 1–2 more, with parity (Python + `divoomd` Rust) and tests.
5. **Verify > 95% coverage** on `source = [divoom_lib, divoom_gui, divoom_daemon]`.

## Method

- Verify against code + real hardware (Timoo) before claiming done.
- Commit per logical change; update `SESSION_HANDOFF.md` + `CHANGELOG.md` each round.
- Tag the release only after steps 2–5 are committed (tagging *before* the cloud work
  would exclude it from the release — deviation from the literal list order, noted
  here so the shipped tag contains everything in this batch).

---

## 1. Release: commit + tag

- Bump `pyproject.toml` `version` `0.22.8 → 0.22.9` (R60 was a substantial round; the
  follow-up CI fix is an additional patch on top of the `v0.22.8` checkpoint).
- Commit the version bump. Tag `v0.22.9`. `git push` + `git push --tags`.
- Bump the Homebrew tap Cask (`~/Projects/homebrew-tap/Casks/divoom-control.rb`) to
  `0.22.9` (version + SHA) so the published formula matches.
- **Kill:** `git tag` lists `v0.22.9`; `git push --tags` done; Cask pinned to `0.22.9`.

## 2. Doc pruning (remove/update stale docs)

Inventory `docs/` and decide per file:
- **KEEP (load-bearing):** `AGENTS.md`, `CHANNEL_ARCHITECTURE.md`, `SESSION_HANDOFF.md`
  (rewrite concise — it's 1200+ lines of history), `CHANGELOG.md`.
- **CONSOLIDATE:** `ROADMAP.md` is currently **empty** — either fill it from
  `PLANNING_NEXT_PHASE.md` + deferred items, or delete it and point readers to
  `SESSION_HANDOFF.md`.
- **REMOVE (executed, now noise):** old `PLANNING_ROUND{n}.md` for rounds fully shipped
  and superseded (verify no open item references them). Keep the most recent 1–2 as
  historical anchors only if they carry non-obvious rationale.
- **UPDATE:** `PLANNING_NATIVE_PORT_HARDENING.md` — confirm Phase-5 wording already says
  "archive, not delete" (R60 #6); strip any remaining "Python is the default" claims.
- **Kill:** no doc in `docs/` asserts a stale/deferred state that contradicts code;
  `grep -rn "not ported\|TODO\|FIXME\|deferred" docs/` returns only intentional notes.

## 3. Timoo re-verify (R60 #2)

- Scan (`divoom_gui` / `divoomd` discover) and confirm `Timoo-light-4` is in range.
- Connect; `display.show_image` with a cloud-decoded payload (magic 9/18/26/0xAA) on
  Timoo; post-push `get_brightness` read-back → assert **no device-stick**.
- If Timoo still absent, note it and re-run when reachable (don't fake success).
- **Kill:** Timoo push verified + no-stick; `PLANNING_ROUND60.md` #2 updated to
  "all 4 devices".

## 4. Divoom Cloud HTTP work

### 4a. Diagnose `UserNewGuest` `RC=10`
- Decompiled APK (`LoginServer.java:368 q()`) shows the current guest flow:
  `APPGetServerUTC` → build `BlueDeviceNewDeviceRequest{utc, utcEncrypt=P2.a.a(utc)}`
  → `UserNewGuest` → `LoginServer.l(userId, token, "", false)` (GetAllInfo).
- Python `divoom_lib/divoom_auth.py:_login_guest` sends
  `{"Command":"User/NewGuest","UTC":utc,"UTCEncrypt":hmac,"Token":0,"UserId":0}`.
- Diff the APK `BlueDeviceNewDeviceRequest` fields + `P2.a.a` HMAC vs `_hmac_md5`
  (`HMAC_KEY = "DivoomBluetoothDevice<>?"`) to find what `RC=10` means / what's missing
  (likely a device-bind field, or the server now requires `DeviceId`/`DevicePassword`
  we already load from `virtual_device.json`). Rust `divoomd/src/cloud.rs` mirrors the
  Python flow — fix both or share the corrected request.
- **Kill:** guest login returns `RC=0` against a mocked HTTP endpoint (record/replay the
  APK-shaped request/response), or the blocker is documented with the exact server
  behavior if it's truly server-side.

### 4b. Cloud HTTP client + clock-face store
- Stand up a thin cloud HTTP client (Python `divoom_lib/cloud.py` if not present; extend
  `divoomd/src/cloud_cmds.rs`) exposing:
  - **clock-face store**: list clock faces from the cloud (e.g.
    `GetCategoryFileListV2` / clock-face category) — cache to disk, return list.
  - **1–2 more endpoints**: TBD from the clock-face store's natural dependencies
    (e.g. fetch a single clock-face file by id; user's uploaded faces).
- Wire to GUI only if it unblocks a visible feature; otherwise keep it library/daemon
  surface + tests (avoid scope creep into UI).
- **Kill:** client returns parsed data in offline/mock mode; Python + Rust handlers
  agree on the wire shape; tests green.

## 5. Coverage > 95%

- Baseline: full `coverage run -m pytest` (run in progress, pid 45514, →
  `coverage report`). Record TOTAL.
- Raise to ≥ 95% by:
  - Adding unit tests for uncovered library/API paths (cloud client, auth, device_call
    facade, BLE-read retry/cache, GUI API mixins, daemon parity).
  - Adding `pragma: no cover` / `[tool.coverage.report] exclude_lines` + a sensible
    `[tool.coverage.run] omit` for genuinely-untestable surface: CLI entrypoints,
    `if __name__ == "__main__"` blocks, platform-only branches, `web_ui/*.js` (not
    Python), and hardware-only paths gated by `markers.hardware`.
- **Kill:** `coverage report` TOTAL ≥ 95% on the configured source; report the number
  and the omit list so it's honest, not gamed.

---

## Risks / open questions

- **`RC=10` may be server-side** (guest login disabled). Fallback: ship the clock-face
  store using cached/email creds and document the guest blocker; don't pretend guest
  works.
- **95% coverage** across a GUI + BLE + daemon tree is a large test-writing effort; the
  `omit`/exclusion list must be defensible (platform/hardware/CLI/JS), not a cover for
  lazy gaps. Will report the real TOTAL.
- **Timoo** may again be out of range → re-run later, don't fabricate.

## Deferred (explicitly NOT this round)

- R12 visual pass / R12 hardware verification (user-driven, needs direction).
- Full 200+ cloud endpoint surface — this round stands up the client + clock-face store
  + auth fix only; remaining endpoints are follow-on rounds.
