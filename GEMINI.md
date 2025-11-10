## Project Context: Divoom Control Library

This project is focused on developing a Python library, `divoom-control`, for interacting with Divoom devices over Bluetooth Low Energy (BLE). The library aims to provide a high-level API for controlling various device features, including the display, channels, system settings, and more.

The project has evolved from initial scripts and reverse-engineering efforts into a more structured Python library. The core logic is encapsulated within the `divoom_lib` package, which is designed to be extensible and easy to use.

### Gemini's Role

Gemini's role is to act as an interactive CLI agent, assisting with software engineering tasks. This includes:
*   Understanding and implementing user requests.
*   Utilizing available tools (e.g., file system operations, shell commands, web search) to achieve project goals.
*   Adhering to project conventions, style, and structure.
*   Proactively adding tests and verifying changes.
*   Providing explanations and clarifications when needed.

### Authoritative Sources

The `docs/DIVOOM_API_DOC.md` file serves as the primary internal authoritative source for the Divoom Bluetooth protocol, derived from various open-source projects and community discussions.

### Recent Progress: Library Refactoring

The project has recently undergone a significant refactoring to improve its structure and usability. The key changes include:

*   **`divoom_lib` Package:** The core logic has been organized into a `divoom_lib` package with modules for different functionalities (e.g., `display`, `light`, `system`).
*   **`Divoom` Class:** A central `Divoom` class in `divoom_lib/__init__.py` provides a simplified interface for interacting with Divoom devices.
*   **Improved Examples:** The example scripts have been updated to use the new library structure.
*   **Documentation:** The documentation has been updated to reflect the new library structure and API.

This refactoring provides a solid foundation for further development and makes it easier to add new features and support for more Divoom devices.
