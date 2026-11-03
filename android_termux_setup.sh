#!/data/data/com.termux/files/usr/bin/bash
# ==============================================================================
# Supreme Court of India Case Monitor — Android Termux Setup
# ==============================================================================
# This script sets up the SCI Case Monitor directly on your Android phone using
# Termux + Termux:API, allowing 100% background monitoring with native Android
# push notifications and wake-lock (runs even with screen turned off).
# ==============================================================================

set -e

echo "🏛️ Setting up Supreme Court Case Monitor on Android (Termux)..."

# 1. Update Termux packages
pkg update -y
pkg install -y python python-pip libjpeg-turbo libpng clang termux-api git

# 2. Install Python dependencies
pip install --upgrade pip
pip install requests beautifulsoup4 lxml Pillow rich prompt_toolkit ddddocr onnxruntime

# 3. Ensure Termux Wake-lock (keeps CPU active in background while screen is off)
termux-wake-lock
echo "✓ Termux wake-lock enabled (CPU will stay active in background)."

# 4. Create convenient alias
ALIAS_CMD="alias scimonitor='python ~/sci-monitor/sci_monitor_cli.py'"
if ! grep -q "alias scimonitor=" ~/.bashrc 2>/dev/null; then
    echo "$ALIAS_CMD" >> ~/.bashrc
    echo "✓ Added 'scimonitor' shortcut to ~/.bashrc"
fi

echo ""
echo "=================================================================="
echo "🎉 Setup Complete!"
echo "To start monitoring your cases right now on your phone, run:"
echo "   python sci_monitor_cli.py"
echo "or simply type:"
echo "   scimonitor"
echo "=================================================================="
