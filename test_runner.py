import subprocess

def run_script(script_name):
    try:
        result = subprocess.run(['python3', script_name], capture_output=True, text=True, check=True)
        print(result.stdout)
    except FileNotFoundError:
        print(f"Error: The script '{script_name}' was not found.")
    except subprocess.CalledProcessError as e:
        print(f"Error running script: {script_name}")
        print(f"Return code: {e.returncode}")
        print(f"Output:\n{e.stdout}")
        print(f"Error output:\n{e.stderr}")

if __name__ == "__main__":
    run_script('discover_devices.py')
