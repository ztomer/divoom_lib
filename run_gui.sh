#!/bin/bash
# run_gui.sh — Launcher for Divoom Desktop GUI controller & display coordinator

echo "[ ==> ] Starting Divoom Desktop Controller Center..."
echo "[ ==> ] Bootstrapping pywebview premium cyber dashboard..."

# Execute GUI main script using python3 as requested
python3 divoom_gui/gui_main.py

echo "[ Ok  ] Divoom Desktop Controller closed."
