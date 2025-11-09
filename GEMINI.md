## Project Context: Divoom Control Program

This project aims to develop a Python program to control Divoom devices via Bluetooth. The primary goals are:
1.  Connect to Divoom devices.
2.  Reset their Bluetooth connections.
3.  Update their hot channel top designs.

### Current Status

The `divoom_control.py` script has been created with a basic structure, including helper functions for logging and a `DivoomDevice` class with methods for connecting, disconnecting, sending commands, and placeholder methods for `reset_bluetooth` and `update_hot_channel_design`.

The `reset_bluetooth` and `update_hot_channel_design` functionalities are currently placeholders because the specific Bluetooth commands for these actions need to be reverse-engineered from the Divoom app's communication protocol.

A `README.md` file has also been created, outlining the project's purpose, installation instructions, and usage.

### Next Steps

The immediate next step is to investigate and reverse-engineer the Bluetooth commands for resetting Bluetooth connections and updating hot channel designs. This will likely involve analyzing existing community projects or capturing Bluetooth traffic from the official Divoom app.

### Gemini's Role

Gemini's role is to act as an interactive CLI agent, assisting with software engineering tasks. This includes:
*   Understanding and implementing user requests.
*   Utilizing available tools (e.g., file system operations, shell commands, web search) to achieve project goals.
*   Adhering to project conventions, style, and structure.
*   Proactively adding tests and verifying changes.
*   Providing explanations and clarifications when needed.

### Authoritative Sources

The `DIVOOM_API_DOC.md` file serves as the primary internal authoritative source for the Divoom Bluetooth protocol, derived from the official Divoom API documentation available at [https://docin.divoom-gz.com/web/#/5/146](https://docin.divoom-gz.com/web/#/5/146). This external link is the original source for the protocol details.

### Recent Progress: MVP for Blue Light Control

We have successfully established a working MVP (Minimum Viable Product) for controlling a Divoom device (specifically "Timoo-light-4") to set its light channel to a solid blue color. This was achieved through the `api_test.py` script, leveraging the `divoom_api` library.

**Key Findings and Working Parameters:**

*   **Device:** Timoo-light-4
*   **Working Write Characteristic UUID:** `49535343-8841-43f4-a8d4-ecbe34729bb3`
*   **Working Notify Characteristic UUID:** `49535343-1e4d-4bd9-ba61-23c647249616`
*   **Protocol Framing:** iOS LE protocol (`use_ios_le_protocol = True`)
*   **Payload Escaping:** No escaping (`escapePayload = False`)
*   **Command for Blue Light:**
    *   **Command Code:** `0x45` (Light Mode)
    *   **Payload Arguments:** `[0x01, 0x00, 0x00, 0xFF, 0x64, 0x00, 0x01]`
        *   `0x01`: Light Mode (solid color)
        *   `0x00, 0x00, 0xFF`: RGB values for Blue
        *   `0x64` (decimal 100): Brightness (100%)
        *   `0x00`: Effect Mode
        *   `0x01`: Power State (on)

**Significance:**

This successful implementation confirms the ability to connect to and send functional commands to the Divoom device using the `bleak` library and the `divoom_api` structure. It provides a solid foundation for further development, allowing us to expand control to other light modes, colors, and eventually other functionalities like resetting Bluetooth or updating channel designs, by building upon these identified working parameters.