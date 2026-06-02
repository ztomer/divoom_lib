#!/bin/bash
# install_daemon.sh — Installs and loads the Divoom Monthly Best launchd daemon on macOS.

set -e

# Colored Console Log Wrappers
print_info() {
    echo -e "[ ==> ] $1"
}

print_ok() {
    echo -e "\033[32m[ Ok  ]\033[0m $1"
}

print_wrn() {
    echo -e "\033[33m[ Wrn ]\033[0m $1"
}

print_err() {
    echo -e "\033[31m[ Err ]\033[0m $1"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LAUNCH_AGENT_DIR="$HOME/Library/LaunchAgents"
PLIST_FILENAME="com.divoom.monthlybest.plist"
PLIST_SOURCE="$SCRIPT_DIR/$PLIST_FILENAME"
PLIST_TARGET="$LAUNCH_AGENT_DIR/$PLIST_FILENAME"

print_info "Starting Divoom Monthly Best Daemon Installation..."

# 1. Ensure target launch agents directory exists
if [ ! -d "$LAUNCH_AGENT_DIR" ]; then
    print_info "Creating LaunchAgents folder in user's library..."
    mkdir -p "$LAUNCH_AGENT_DIR"
fi

# 2. Check if the plist source template exists
if [ ! -f "$PLIST_SOURCE" ]; then
    print_err "Source template $PLIST_SOURCE does not exist."
    exit 1
fi

# 3. Unload existing launch agent if loaded
if launchctl list | grep -q "com.divoom.monthlybest"; then
    print_info "Unloading active Divoom Monthly Best daemon..."
    launchctl unload "$PLIST_TARGET" || true
fi

# 4. Copy plist template and dynamically interpolate absolute paths
print_info "Copying LaunchAgent plist and updating absolute paths..."
sed "s|/Users/ztomer|$HOME|g" "$PLIST_SOURCE" > "$PLIST_TARGET"
chmod 644 "$PLIST_TARGET"

# 5. Ensure stdout/stderr logs directories are writable
mkdir -p "$PROJECT_ROOT/test_reports"

# 6. Load launch agent
print_info "Loading Divoom Monthly Best launchd agent..."
launchctl load "$PLIST_TARGET"

print_ok "Divoom Monthly Best Daemon installed successfully!"
print_info "Service Label: com.divoom.monthlybest"
print_info "Service Interval: 86400 seconds (24 hours)"
print_info "Standard Logs: $PROJECT_ROOT/test_reports/monthly_best_daemon_stdout.log"
print_info "Error Logs: $PROJECT_ROOT/test_reports/monthly_best_daemon_stderr.log"
print_ok "Installation complete! 🟢"
