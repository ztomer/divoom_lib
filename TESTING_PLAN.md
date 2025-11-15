# Divoom API Testing Plan

This document outlines the strategy for testing the `divoom-control` Python library to ensure all API commands function correctly.

## 1. Test Structure and Framework

-   **Test Suite:** All tests will be located within the `/tests` directory.
-   **Modular Design:** Tests will be organized into separate files based on API functionality (e.g., `test_light.py`, `test_system.py`, `test_display.py`). This improves readability and maintenance.
-   **Test Runner:** A central test runner script (`tests/test_runner.py`) will be used to discover and execute all tests in the suite.
-   **Base Test Case:** A base test class can be created to handle common setup and teardown logic, such as device connection and disconnection.

## 2. Testing Strategy

The core of the testing strategy revolves around verifying that the device's state changes as expected after an API call.

### For Setter/Getter Pairs

For APIs that have both a "setter" (a command to change a value) and a "getter" (a command to read a value), the tests will follow a "Set-Then-Get" pattern:

1.  **Get Initial State:** Read and store the original value of the setting (e.g., current brightness).
2.  **Set New Value:** Send a command to update the setting to a new, known value.
3.  **Verify Change:** Read the value back from the device and assert that it matches the new value.
4.  **Restore Initial State:** Restore the setting to its original value to ensure the device is left in a clean state.

*Example: Brightness Test*
- `get_brightness()` -> returns `50`
- `set_brightness(80)`
- `get_brightness()` -> assert returns `80`
- `set_brightness(50)`

### For Action Commands

For commands that trigger an action without a corresponding getter (e.g., showing a VJ effect, displaying a temporary image), the test will focus on command success.

1.  **Send Command:** Execute the API command.
2.  **Verify Success:** The primary assertion is that the command executes without raising any exceptions (e.g., protocol errors, connection failures).
3.  **Visual Confirmation:** The test logs will note that visual confirmation on the device is required for full verification.

### For Commands with Notifications

For commands that trigger an asynchronous notification from the device, the test procedure is more complex:

1.  **Subscribe to Notifications:** The test must first subscribe to the relevant Bluetooth characteristic to listen for incoming data.
2.  **Send Command:** Send the command that is expected to trigger the notification.
3.  **Wait and Validate:** The test will wait for a specified timeout period to receive the notification.
4.  **Assert Payload:** Once received, the payload of the notification will be parsed and validated against the expected outcome.

## 3. Implementation Plan

1.  **Proof of Concept (PoC):** **(COMPLETED)** - Start by expanding the existing `tests/api_test.py` to fully test a single, simple feature like brightness control, implementing the "Set-Then-Get" pattern. This will validate the overall testing methodology.
    -   **Outcome:** This PoC was highly successful. It not only validated the "Set-Then-Get" approach but also uncovered several critical bugs in the underlying communication library (`divoom_lib/base.py`) related to protocol handling, packet parsing, and acknowledgment logic. Fixing these bugs was essential for any reliable getter-style command. A full summary of this investigation can be found in `docs/brightness_investigation.md`.

2.  **Refactor into Test Suite:** Once the PoC is successful, refactor the test into a dedicated file (e.g., `tests/test_system.py` for brightness).
    -   **Outcome:** **(COMPLETED)** - A permanent, async-native test file `tests/test_system_functions.py` was created using `unittest.IsolatedAsyncioTestCase`.

3.  **Expand Coverage:** Incrementally create new test files and test cases for each category of the API (Light, Display, Time, etc.), following the strategies outlined above.

4.  **Develop Test Runner:** Implement `tests/test_runner.py` to automate the execution of the entire test suite.
