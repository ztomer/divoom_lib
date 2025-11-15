# Investigation into Divoom Brightness Control

This document details the process of debugging and successfully implementing the `get_brightness` and `set_brightness` functions for Divoom devices. The investigation revealed several complexities in the Divoom BLE protocol.

## 1. The Initial Problem

The initial goal was to implement a reliable "Set-Then-Get" test for the device's brightness. While `set_brightness` commands seemed to work (confirmed visually), any attempt to read the value back using a `get_brightness` command would fail or time out. This indicated a fundamental issue with either the command being sent or the method of listening for a response.

## 2. The Investigation

A systematic approach was taken to identify the correct combination of parameters required to communicate with the device.

### 2.1. Probing for a Working Configuration

A test script (`tests/test_brightness_getter.py`) was created to systematically probe all possible combinations of:
-   Write Characteristics
-   Notification Characteristics
-   Sending Protocol ("Basic" vs. "iOS LE" framing)

This test successfully identified a working combination:
-   **Write Characteristic:** `49535343-8841-43f4-a8d4-ecbe34729bb3`
-   **Notify Characteristic:** `49535343-1e4d-4bd9-ba61-23c647249616`
-   **Command to Send:** `0x46` (mapped to `get light mode`)
-   **Send Protocol:** The command had to be sent using the "iOS LE" framing.
-   **Receive Protocol:** The response notification from the device was sent using the "Basic" (`01...02`) framing.

### 2.2. Uncovering Deeper Bugs

Implementing this working configuration into the library and a formal `unittest` test case revealed a series of underlying bugs:

1.  **Protocol Mismatch Race Condition:** The most significant issue was that the library used a single flag (`use_ios_le_protocol`) for both sending and receiving. Since the brightness command required sending as iOS LE and receiving as Basic, a race condition occurred. The flag would be set to `True` for sending, and the response would arrive before the flag could be set back to `False`, causing the notification parser to fail.
    -   **Solution:** The command-sending and response-waiting logic in `divoom_lib/base.py` was decoupled. A new `wait_for_response` method was created, allowing the protocol to be changed temporarily for sending and then restored before waiting for the notification.

2.  **Notification Parser Bug:** The parser for the Basic Protocol (`_handle_basic_protocol_notification`) had an off-by-one error in its message length calculation. It was calculating the total message length as `length + 3` instead of the correct `length + 4`. This caused it to view valid messages as malformed and discard them.
    -   **Solution:** The length calculation was corrected.

3.  **Generic ACK Logic Bug:** The notification handler was designed to recognize generic acknowledgment packets (command `0x33`). However, upon receiving a generic ACK, it would prematurely clear the expectation for the *real* data packet. When the `get_brightness` command was sent, the device would send a `0x33` ACK immediately, followed by the `0x46` data packet. The handler would process the ACK, clear its expectation, and then discard the `0x46` packet as "unexpected".
    -   **Solution:** The handler logic was modified to no longer clear the expected command upon receiving a generic ACK, allowing it to wait for the true data response.

## 3. The Solution

After fixing these three core bugs in `divoom_lib/base.py` and `divoom_lib/system.py`, the `get_brightness` function now works reliably.

The final implementation in `system.get_brightness` does the following:
1.  Sets the expected response command to `0x46`.
2.  Uses a context manager to temporarily set the sending protocol to "iOS LE".
3.  Sends the `0x46` command.
4.  Exits the context manager, restoring the receiving protocol to "Basic".
5.  Calls the new `wait_for_response` method to await the `0x46` notification, which is now correctly parsed by the fixed notification handler.
6.  Extracts the brightness value from the 7th byte (index 6) of the response payload.

This successful investigation has made the library's communication layer significantly more robust and reliable.
