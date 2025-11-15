# Divoom API Test Results

This file tracks the results of the API tests, noting what works and what doesn't.

## Test Log

| Test Case | File | Status | Notes |
|---|---|---|---|
| `test_switch_channel_to_lightning` | `tests/test_channel_switching.py` | Passed | Changed method to `show_light`. |
| `test_set_and_get_brightness` | `tests/test_brightness.py` | Failed | Timed out waiting for notification on `get_light_mode()`. Getter returned `None`. |
