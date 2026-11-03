#!/usr/bin/env python3
"""
main.py — Entry point for SCI Case Monitor.

By default, launches the rich terminal application (sci_monitor_cli.py)
which runs seamlessly in macOS Terminal without windowing/Tk rendering bugs.

Usage:
    python3 main.py             # Run terminal monitor (default)
    python3 main.py --reset     # Clear saved cases and reconfigure
    python3 main.py --gui       # Launch graphical UI (if supported)

Or double-click "SCI Monitor.command" in Finder.
"""

import sys
import os
import warnings

# Suppress macOS Tk deprecation warning and LibreSSL notice
os.environ["TK_SILENCE_DEPRECATION"] = "1"
warnings.filterwarnings("ignore", message=".*urllib3.*OpenSSL.*")
warnings.filterwarnings("ignore", message=".*NotOpenSSLWarning.*")

# Ensure the project root is on sys.path when launched from anywhere
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main() -> None:
    # Check if user explicitly requested GUI
    if "--gui" in sys.argv:
        try:
            from app.gui import SCIMonitorApp
            app = SCIMonitorApp()
            app.mainloop()
            return
        except Exception as e:
            print(f"Error launching GUI: {e}")
            print("Falling back to Terminal interface...\n")

    # Default: launch terminal interface
    from sci_monitor_cli import main as cli_main
    cli_main()


if __name__ == "__main__":
    main()
