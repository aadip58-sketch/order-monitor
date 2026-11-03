"""
notifier.py — macOS native desktop notification via AppleScript.
"""

from __future__ import annotations

import subprocess
import shlex


def send_mac_notification(
    title: str,
    message: str,
    subtitle: str = "",
    sound: str = "Glass",
    action_url: str = "",
) -> None:
    """
    Fire a native notification across platforms:
    - Android (Termux): termux-notification with sound, high priority, and optional URL action
    - macOS: osascript
    - Linux: notify-send
    """
    import shutil

    # 1. Android via Termux
    if shutil.which("termux-notification"):
        cmd = [
            "termux-notification",
            "--title", title,
            "--content", message,
            "--priority", "high",
            "--sound",
            "--vibrate", "500,200,500",
        ]
        if action_url:
            cmd.extend(["--action", f"xdg-open '{action_url}'"])
        try:
            subprocess.run(cmd, capture_output=True, timeout=5)
            return
        except Exception:
            pass

    # 2. macOS via AppleScript
    if shutil.which("osascript"):
        def _esc(s: str) -> str:
            return s.replace("\\", "\\\\").replace('"', '\\"')

        parts = [f'display notification "{_esc(message)}"']
        parts.append(f'with title "{_esc(title)}"')
        if subtitle:
            parts.append(f'subtitle "{_esc(subtitle)}"')
        if sound:
            parts.append(f'sound name "{_esc(sound)}"')

        script = " ".join(parts)
        try:
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=10,
            )
            return
        except Exception:
            pass

    # 3. Linux via notify-send
    if shutil.which("notify-send"):
        try:
            subprocess.run(
                ["notify-send", "-u", "critical", title, message],
                capture_output=True,
                timeout=5,
            )
            return
        except Exception:
            pass

