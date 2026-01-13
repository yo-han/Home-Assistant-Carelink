#!/usr/bin/env bash
set -e

echo "Starting Carelink Token Generator..."

# Start virtual display for headless Firefox
echo "Starting Xvfb virtual display..."
Xvfb :99 -screen 0 1024x768x24 &
export DISPLAY=:99

# Wait for display to be ready
sleep 2

# Start the Flask web server
echo "Starting web server on port 8099..."
cd /app
exec python3 server.py
