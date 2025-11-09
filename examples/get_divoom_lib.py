import requests

def print_info(message):
    """Prints an informational message."""
    print(f"[ ==> ] {message}")

def print_ok(message):
    """Prints a success message."""
    print(f"[ Ok  ] {message}")

def get_pixoo_lib():
    """Downloads the pixoo.py library from GitHub."""
    url = "https://raw.githubusercontent.com/virtualabs/pixoo-client/master/pixoo.py"
    print_info(f"Downloading pixoo.py from {url}...")
    response = requests.get(url)
    with open("pixoo.py", "w") as f:
        f.write(response.text)
    print_ok("pixoo.py downloaded successfully.")

if __name__ == "__main__":
    get_pixoo_lib()