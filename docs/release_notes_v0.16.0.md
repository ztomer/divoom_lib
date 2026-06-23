# Divoom Control v0.16.0 — hardware-validated daemon fixes (2026-06-22)

This release packages a batch of fixes that were **validated against real
hardware** (a live Pixoo-1, driven through the daemon over the socket), plus the
revival of the native image-encoder fast path. It is the ground-truth Python
release cut immediately before the native-daemon port work begins (see
`docs/PLANNING_NATIVE_PORT.md`).

Since v0.15.2:

## Fixes (HW-validated)

- **Read-backs restored (iOS-LE ACK revert).** `device.get_brightness` /
  `device.get_device_name` had regressed to a 5.26 s timeout -> `null` on a real
  Pixoo while writes still worked. Root cause: an R53.35 change kept the response
  scalar on the generic 0x33 ACK, which broke the 0x46 protocol autoprobe and
  mis-detected the Basic-only device as iOS-LE. Reverted; read-backs return in
  ~60 ms again. (`b1e9770`, `56c2554`)

- **Exclusive steal-reject — no more 30 s hang-then-steal.** A competing
  `exclusive_start` used to block for the full 30 s idle deadline and then
  silently steal the lock (reporting success). The acquire was being routed
  through the gated command queue — a lock-acquire gated by the lock it seeks.
  New `CommandQueue.acquire_now()` rejects a foreign owner immediately
  (HW: 0.00 s, honest error). (`ae58e62`)

- **ACK != device-confirmed honesty.** Custom-art and hot-update pushes reported
  bare `success: true` on GATT write-ACKs with no device confirmation. 0x8E
  `query_page` is HW-confirmed unreliable on the Pixoo (4 s timeout), so verifying
  is impossible — the results now surface honest status instead:
  `custom_art_push` returns `device_confirmed: false` (GUI says "sent" not
  "pushed"); `hot_update` marks each served file `confirmed` and reports a
  `confirmed` count. (`9e9defe`)

- **0x8B animation retransmit dead path fixed.** During the chunk loop and
  retransmit window the response scalar was cleared by the start-ACK, so the
  handler dropped every device retransmit request and a lost chunk was silently
  unrecoverable. The streamer now listens for 0x8B for the stream duration so
  retransmit frames queue without consuming the scalar. HW: animation push
  unaffected. (`0db1760`)

- **Native C image encoder — divergence fixed and fast path revived.** The C
  static encoder emitted a 6-byte header (the NN palette-count byte was clobbered
  by the palette memcpy) vs Python's correct 7-byte header. Separately, both
  native wrappers under-allocated the output buffer (1 bit/pixel vs the needed
  8 bits/pixel), so the C returned an error for any real frame and silently fell
  back to Python — the native image encoders were effectively dead. Both fixed;
  the dylib was rebuilt and is now byte-identical to the Python reference across
  all sizes/colours and actually reached. (`053bd36`)

## Notes

- Suite: 1700 passed (native parity tests now run and validate the encoder fix).
- New socket-protocol response fields are additive: `device_confirmed`
  (custom-art) and `confirmed` (hot-update). Existing clients are unaffected.
- No GUI/menubar behavior changes beyond the custom-art toast wording
  ("sent" vs "pushed" when unconfirmed).
