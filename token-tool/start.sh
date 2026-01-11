#!/bin/bash

echo ""
echo "=============================================="
echo "   Carelink Token Tool"
echo "=============================================="
echo ""
echo "1. Open browser for login:"
echo "   http://localhost:6080/vnc.html?autoconnect=true"
echo ""
echo "2. Copy/paste tip: use the clipboard panel"
echo "   (click arrow on the left side)"
echo ""
echo "=============================================="
echo ""

# Wait for X server to be ready
sleep 3

# Wait for noVNC to be ready
while ! curl -s http://localhost:6080 > /dev/null 2>&1; do
    echo "Waiting for noVNC to start..."
    sleep 1
done

echo "noVNC is ready! Opening browser..."
echo ""

# Change to output directory so logindata.json is saved there
cd /output

# Run the login script (reads CARELINK_REGION from environment)
python /app/carelink_login.py
LOGIN_RESULT=$?

echo ""
echo "=============================================="

if [ -f /output/logindata.json ]; then
    echo ""
    echo "  SUCCESS!"
    echo ""
    echo "  Download your token file:"
    echo "  http://localhost:8000/logindata.json"
    echo ""
    echo "  Or find it in: ./output/logindata.json"
    echo ""
    echo "=============================================="
else
    echo ""
    echo "  LOGIN FAILED"
    echo ""
    echo "  Please check the browser window for errors."
    echo ""
    echo "=============================================="
fi

echo ""
echo "Press Ctrl+C to stop the container"
echo ""

# Keep container running so user can download the file
tail -f /dev/null
