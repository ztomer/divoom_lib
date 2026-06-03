import os
import sys
import time
from pathlib import Path

# Add paths
ROOT = Path(__file__).parent.parent
sys.path.append(str(ROOT))
sys.path.append(str(ROOT / "gui"))

# Set environment variable to force Mock BLE Client
os.environ["DIVOOM_MOCK_BLE"] = "1"

from gui_main import DivoomGuiAPI
import control_server as cs

def main():
    sock_path = "/tmp/divoom.sock"
    if os.path.exists(sock_path):
        os.unlink(sock_path)

    print("[ ==> ] Starting headless Mock Divoom Control Server...")
    api = DivoomGuiAPI()
    httpd, thread = cs.serve_unix_in_background(api, sock_path)
    print(f"[ Ok  ] Listening on UNIX Domain Socket at {sock_path}")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        print("[ ==> ] Shutting down server...")
        httpd.shutdown()
        if os.path.exists(sock_path):
            os.unlink(sock_path)
        print("[ Ok  ] Goodbye!")

if __name__ == "__main__":
    main()
