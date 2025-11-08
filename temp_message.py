from pixoo import Pixoo
import inspect

def print_info(message):
    """Prints an informational message."""
    print(f"[ ==> ] {message}")

def print_ok(message):
    """Prints a success message."""
    print(f"[ Ok  ] {message}")

print_info("Inspecting pixoo.Pixoo class for available methods...")
methods = [method_name for method_name, _ in inspect.getmembers(Pixoo, predicate=inspect.isfunction) if not method_name.startswith('_')]
print_ok("Available commands:")
for method in sorted(methods):
    print(f"  - {method}")