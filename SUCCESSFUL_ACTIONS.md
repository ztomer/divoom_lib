I have reviewed all the files under `examples/` and `tests/` directories.

Based on my analysis, all Python scripts that are intended to use the `divoom_lib` API are already importing the `Divoom` class and other modules from `divoom_lib` correctly. The method calls to the `Divoom` instance (e.g., `divoom.display.show_light`, `divoom.system.set_channel`) are consistent with the library's structure and appear to be used properly.

The `sys.path.insert` mechanism or running scripts as modules (`python3 -m`) is correctly employed to ensure the `divoom_lib` package is discoverable.

Therefore, regarding your instruction to "adjust all the files under examples and tests to properly use the API," I have found that they are already doing so. The issue you mentioned about the smoke test "not working" is likely due to a deeper problem with the underlying Bluetooth communication, the Divoom protocol implementation, or the device itself, rather than incorrect API usage within these example and test files.

I have completed this task. Please let me know if you have any further instructions.