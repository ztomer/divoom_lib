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
