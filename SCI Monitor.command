#!/usr/bin/env bash
# =============================================================================
# SCI Monitor.command — Double-click launcher for macOS
# =============================================================================
# Place this file in the sci-monitor folder.
# Right-click → Open (first time) to bypass Gatekeeper.
# After that: just double-click.
# =============================================================================

# Change to the directory containing this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export TK_SILENCE_DEPRECATION=1

VENV_PY="$SCRIPT_DIR/venv/bin/python"

# Check if setup has been run
if [[ ! -f "$VENV_PY" ]]; then
    echo "═══════════════════════════════════════════════"
    echo "  First-time setup required."
    echo "  Please run in Terminal:"
    echo "    bash \"$SCRIPT_DIR/setup.sh\""
    echo "═══════════════════════════════════════════════"
    echo ""
    echo "Press any key to open Terminal for setup…"
    read -r -n 1
    open -a Terminal "$SCRIPT_DIR/setup.sh"
    exit 0
fi

# Launch the app
exec "$VENV_PY" "$SCRIPT_DIR/main.py" "$@"
