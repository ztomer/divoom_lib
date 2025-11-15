### Successful Action: Temperature/Weather Command Functions with `tests.test_temp_weather_functions`

A new test file `tests/test_temp_weather_functions.py` was created to test the `divoom_lib/commands/temp_weather.py` module.

-   All 7 tests within `tests.test_temp_weather_functions.py` passed successfully.
-   This involved refactoring `divoom_lib/commands/temp_weather.py` to remove `asyncio.create_task` calls from `__init__` and property setters, and introducing an explicit `update_temp_weather` async method to resolve `RuntimeError: no running event loop` issues during testing.
-   The tests confirm the correct functionality of:
    *   The `_update_message` method correctly constructing the temperature and weather payload and calling `send_command` with the expected arguments for various temperature values (positive, zero, negative) and weather types.
    *   The `temperature` and `weather` property setters correctly updating the internal state without automatically sending commands.
    *   The `ValueError` being correctly raised for out-of-range temperatures.

This significantly improves the test coverage for the Divoom API's temperature and weather setting capabilities.