#!/usr/bin/env bash
# =============================================================================
# setup.sh — One-time bootstrap for SCI Case Monitor
# =============================================================================
# Installs:
#   1. Homebrew (if not present — prompts user)
#   2. tesseract OCR engine (via brew)
#   3. Python venv in ./venv
#   4. All Python dependencies from requirements.txt
#   5. Makes the launcher executable
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "┌─────────────────────────────────────────────────┐"
echo "│         SCI Case Monitor — Setup Script         │"
echo "└─────────────────────────────────────────────────┘"
echo ""

# -----------------------------------------------------------------------------
# 1. Homebrew check
# -----------------------------------------------------------------------------
if ! command -v brew &>/dev/null; then
    echo "⚠  Homebrew is not installed."
    echo "   Homebrew is required to install tesseract (OCR engine)."
    echo ""
    read -r -p "   Install Homebrew now? [y/N] " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        echo "   Installing Homebrew…"
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        # Add brew to PATH for Apple Silicon
        if [[ -f /opt/homebrew/bin/brew ]]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
        fi
    else
        echo "   Skipping Homebrew install. tesseract will not be available."
        echo "   CAPTCHA solving will be disabled."
    fi
fi

# -----------------------------------------------------------------------------
# 2. tesseract
# -----------------------------------------------------------------------------
if command -v brew &>/dev/null; then
    if ! command -v tesseract &>/dev/null; then
        echo "📦 Installing tesseract via Homebrew…"
        brew install tesseract
    else
        echo "✓  tesseract already installed: $(tesseract --version 2>&1 | head -1)"
    fi
fi

# -----------------------------------------------------------------------------
# 3. Python check
# -----------------------------------------------------------------------------
PYTHON=""
for candidate in python3.12 python3.11 python3.10 python3.9 python3; do
    if command -v "$candidate" &>/dev/null; then
        PYTHON="$candidate"
        break
    fi
done

if [[ -z "$PYTHON" ]]; then
    echo "✗  Python 3 not found. Please install Python 3.9+ from python.org"
    exit 1
fi

PY_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "✓  Using Python $PY_VERSION ($PYTHON)"

# -----------------------------------------------------------------------------
# 4. Virtual environment
# -----------------------------------------------------------------------------
if [[ ! -d "$SCRIPT_DIR/venv" ]]; then
    echo "🐍 Creating virtual environment in ./venv …"
    "$PYTHON" -m venv "$SCRIPT_DIR/venv"
fi

VENV_PY="$SCRIPT_DIR/venv/bin/python"
VENV_PIP="$SCRIPT_DIR/venv/bin/pip"

echo "📦 Installing Python dependencies…"
"$VENV_PIP" install --upgrade pip --quiet
"$VENV_PIP" install -r "$SCRIPT_DIR/requirements.txt"

echo ""
echo "✅ All Python dependencies installed."

# Verify imports
echo ""
echo "🔍 Verifying installations…"
"$VENV_PY" -c "
import sys
ok = True
packages = [('requests','requests'), ('PIL','Pillow'), ('bs4','beautifulsoup4'),
            ('lxml','lxml'), ('customtkinter','customtkinter'),
            ('cv2','opencv-python-headless'), ('pytesseract','pytesseract')]
for mod, name in packages:
    try:
        __import__(mod)
        print(f'  ✓  {name}')
    except ImportError:
        print(f'  ✗  {name}  ← MISSING')
        ok = False
sys.exit(0 if ok else 1)
"

# -----------------------------------------------------------------------------
# 5. Make launcher executable
# -----------------------------------------------------------------------------
chmod +x "$SCRIPT_DIR/SCI Monitor.command" 2>/dev/null || true

echo ""
echo "┌─────────────────────────────────────────────────┐"
echo "│              ✅  Setup complete!                │"
echo "│                                                 │"
echo "│  To launch the app, double-click:               │"
echo "│    SCI Monitor.command                          │"
echo "│  Or run:                                        │"
echo "│    bash 'SCI Monitor.command'                   │"
echo "└─────────────────────────────────────────────────┘"
echo ""
