#!/usr/bin/env python3
"""
sci_monitor_cli.py — Supreme Court of India Case Monitor
Terminal application with rich live display.

Usage:
    python sci_monitor_cli.py          # interactive setup + start monitoring
    python sci_monitor_cli.py --reset  # clear saved cases and reconfigure

Features:
  • Interactive case setup (up to 3 cases) with arrow-key selection
  • Rich live terminal dashboard — case status, countdown, order count
  • Auto CAPTCHA solving via OCR (with retry)
  • Delta checking — notifies only on NEW orders
  • macOS native desktop notifications via osascript
  • Config persisted in ~/.sci_monitor/config.json
  • Ctrl+C to stop cleanly at any time
"""

from __future__ import annotations

import os
import sys
import time
import json
import signal
import warnings
import threading
import queue
from datetime import datetime
from pathlib import Path

# ── Silence noisy warnings ────────────────────────────────────────────────────
warnings.filterwarnings("ignore", message=".*urllib3.*OpenSSL.*")
warnings.filterwarnings("ignore", message=".*NotOpenSSLWarning.*")
os.environ["TK_SILENCE_DEPRECATION"] = "1"

# ── Add project root to path ──────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Dependency check ──────────────────────────────────────────────────────────
def _check_deps():
    missing = []
    for mod in ["requests", "PIL", "bs4", "lxml", "cv2", "pytesseract", "rich"]:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        print(f"Missing packages: {missing}")
        print("Please run: bash setup.sh")
        sys.exit(1)

_check_deps()

# ── Imports ───────────────────────────────────────────────────────────────────
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich.rule import Rule
from rich import box
from prompt_toolkit import prompt
from prompt_toolkit.completion import WordCompleter

from app.state import (
    load_config, save_config, load_seen_orders, save_seen_orders, make_case_key,
    DATA_DIR
)
from app.scraper import check_case, CASE_TYPE_NAMES, CASE_TYPES
from app.notifier import send_mac_notification
from app.captcha import solve_captcha

console = Console()

CHECK_INTERVAL = 120  # seconds
MAX_LOG_LINES = 30

# ── Sorted case type list for interactive selection ───────────────────────────
SORTED_CASE_TYPES = sorted(CASE_TYPE_NAMES.items(), key=lambda x: int(x[0]))
CASE_TYPE_NUMS = [k for k, _ in SORTED_CASE_TYPES]
CASE_TYPE_LABELS = [f"{k}. {v}" for k, v in SORTED_CASE_TYPES]


# ──────────────────────────────────────────────────────────────────────────────
# Interactive Setup
# ──────────────────────────────────────────────────────────────────────────────

def prompt_case(idx: int) -> dict | None:
    """Interactively prompt for one case. Returns None to skip."""
    console.print(f"\n[bold cyan]── Case {idx} ─────────────────────────────────────[/]")
    console.print("[dim]Press Enter with no input to skip this slot.[/]\n")

    # Case type
    console.print("[bold]Available Case Types:[/]")
    for i, label in enumerate(CASE_TYPE_LABELS, 1):
        console.print(f"  [cyan]{i:>2}[/]. {label.split('. ', 1)[1]}")

    raw = prompt(
        f"  Enter number (1–{len(CASE_TYPE_LABELS)}) or leave blank to skip: "
    ).strip()
    if not raw:
        return None

    try:
        choice = int(raw)
        if not (1 <= choice <= len(CASE_TYPE_LABELS)):
            raise ValueError
        ct_key = CASE_TYPE_NUMS[choice - 1]
        ct_label = CASE_TYPE_LABELS[choice - 1].split(". ", 1)[1]
    except ValueError:
        console.print("[red]Invalid choice. Skipping this slot.[/]")
        return None

    console.print(f"  Selected: [green]{ct_label}[/]")

    # Case number
    cn = prompt("  Case Number (e.g. 1234): ").strip()
    if not cn:
        console.print("[red]No case number entered. Skipping.[/]")
        return None

    # Year
    current_year = str(datetime.now().year)
    yr = prompt(f"  Filing Year (e.g. {current_year}): ").strip()
    if not yr or not yr.isdigit() or len(yr) != 4:
        console.print("[red]Invalid year. Skipping.[/]")
        return None

    return {"case_type": ct_key, "case_no": cn, "year": yr}


def interactive_setup(force: bool = False) -> dict:
    """
    Load or interactively collect case configuration.
    Returns the config dict with 1–3 configured cases.
    """
    config = load_config()
    existing_cases = [
        c for c in config.get("cases", [])
        if c.get("case_type") and c.get("case_no") and c.get("year")
    ]

    if existing_cases and not force:
        console.print(
            Panel(
                "\n".join(
                    f"  [cyan]{i+1}.[/] [bold]{CASE_TYPES.get(c['case_type'], c['case_type'])} "
                    f"{c['case_no']}/{c['year']}[/]"
                    for i, c in enumerate(existing_cases)
                ),
                title="[bold green]✓ Saved Cases Found[/]",
                expand=False,
                border_style="green",
            )
        )
        use_saved = prompt("\nUse these saved cases? [Y/n]: ").strip().lower()
        if use_saved in ("", "y", "yes"):
            return config

    # Fresh setup
    console.print(
        Panel(
            "[bold]Supreme Court of India — Case Monitor Setup[/]\n\n"
            "You can monitor up to [cyan]3 cases[/] simultaneously.\n"
            "Enter case details below. Leave blank to skip a slot.",
            border_style="cyan",
        )
    )

    new_cases: list[dict] = [{}, {}, {}]
    configured_count = 0
    for i in range(3):
        result = prompt_case(i + 1)
        if result:
            new_cases[i] = result
            configured_count += 1

    if configured_count == 0:
        console.print("[red bold]\nNo cases configured. Exiting.[/]")
        sys.exit(0)

    config["cases"] = new_cases
    config["check_interval"] = CHECK_INTERVAL
    save_config(config)
    console.print(f"\n[green]✓ Configuration saved to {DATA_DIR/'config.json'}[/]\n")
    return config


# ──────────────────────────────────────────────────────────────────────────────
# Live Dashboard Renderer
# ──────────────────────────────────────────────────────────────────────────────

class Dashboard:
    """Thread-safe state container + rich renderer for the live display."""

    def __init__(self, cases: list[dict]):
        self._lock = threading.Lock()
        self._cases = cases
        self._case_statuses = ["Initialising…"] * 3
        self._case_colors = ["yellow"] * 3
        self._case_order_counts = [0] * 3
        self._case_new_counts = [0] * 3
        self._last_checked = [None] * 3      # datetime
        self._logs: list[str] = []
        self._next_check: float = time.time() + CHECK_INTERVAL
        self._cycle = 0
        self._running = True

    def set_status(self, idx: int, status: str, color: str = "cyan") -> None:
        with self._lock:
            self._case_statuses[idx] = status
            self._case_colors[idx] = color

    def set_counts(self, idx: int, total: int, new: int = 0) -> None:
        with self._lock:
            self._case_order_counts[idx] = total
            self._case_new_counts[idx] = new
            self._last_checked[idx] = datetime.now()

    def set_next_check(self, ts: float) -> None:
        with self._lock:
            self._next_check = ts

    def log(self, msg: str) -> None:
        with self._lock:
            ts = datetime.now().strftime("%H:%M:%S")
            self._logs.append(f"[dim]{ts}[/]  {msg}")
            if len(self._logs) > MAX_LOG_LINES:
                self._logs.pop(0)

    def inc_cycle(self) -> None:
        with self._lock:
            self._cycle += 1

    def render(self) -> Panel:
        with self._lock:
            remaining = max(0, int(self._next_check - time.time()))
            mins, secs = divmod(remaining, 60)
            is_running = self._running

            # ── Header info ──────────────────────────────────────────────────
            header_text = Text()
            header_text.append("🏛  SCI Case Monitor", style="bold white")
            header_text.append(
                f"   Cycle #{self._cycle}   "
                f"Next check: {mins:02d}:{secs:02d}   "
                f"Interval: {CHECK_INTERVAL}s   ",
                style="dim",
            )
            status_label = "[bold green]● MONITORING[/]" if is_running else "[bold red]● STOPPED[/]"

            # ── Per-case cards ────────────────────────────────────────────────
            case_panels = []
            active_cases = [
                c for c in self._cases
                if c.get("case_type") and c.get("case_no") and c.get("year")
            ]
            for i, case in enumerate(self._cases):
                ct = case.get("case_type", "")
                cn = case.get("case_no", "")
                yr = case.get("year", "")

                if not (ct and cn and yr):
                    p = Panel(
                        "[dim]─ Not configured ─[/]",
                        title=f"[dim]Case Slot {i+1}[/]",
                        border_style="dim",
                    )
                else:
                    short = f"{CASE_TYPES.get(ct, ct)} {cn}/{yr}"
                    checked = (
                        self._last_checked[i].strftime("%H:%M:%S")
                        if self._last_checked[i]
                        else "Pending"
                    )
                    new_badge = (
                        f"  [bold red blink]🔔 +{self._case_new_counts[i]} NEW[/]"
                        if self._case_new_counts[i] > 0
                        else ""
                    )
                    body = (
                        f"[bold]{short}[/]\n"
                        f"[{self._case_colors[i]}]{self._case_statuses[i]}[/]\n"
                        f"Orders logged: [bold cyan]{self._case_order_counts[i]}[/]{new_badge}\n"
                        f"Last checked: [dim]{checked}[/]"
                    )
                    p = Panel(
                        body,
                        title=f"[bold]Case {i+1}[/]",
                        border_style=self._case_colors[i],
                    )
                case_panels.append(p)

            # ── Log panel ────────────────────────────────────────────────────
            log_lines = self._logs[-14:] if self._logs else ["[dim]No activity yet… waiting for check cycle[/]"]
            log_text = "\n".join(log_lines)
            log_panel = Panel(
                log_text,
                title="[bold]📋 Live Activity Log[/]",
                border_style="cyan",
            )

            # ── Compose layout ───────────────────────────────────────────────
            from rich.console import Group

            top_panel = Panel(
                Columns(case_panels, equal=True, expand=True),
                title=f"{header_text}  {status_label}",
                border_style="bright_blue",
            )

            return Group(top_panel, log_panel)


# ──────────────────────────────────────────────────────────────────────────────
# Monitor Logic
# ──────────────────────────────────────────────────────────────────────────────

def run_monitor(config: dict, dashboard: Dashboard) -> None:
    """
    Background daemon thread that runs check cycles.
    """
    seen = load_seen_orders()
    first_run = True

    while dashboard._running:
        cycle_start = time.time()
        dashboard.inc_cycle()
        dashboard.log("[bold]─── Starting check cycle ───[/]")

        cases = config.get("cases", [])
        for idx, case in enumerate(cases):
            if not dashboard._running:
                break

            ct = case.get("case_type", "")
            cn = case.get("case_no", "")
            yr = case.get("year", "")
            if not (ct and cn and yr):
                continue

            short = f"{CASE_TYPES.get(ct, ct)} {cn}/{yr}"
            key = make_case_key(ct, cn, yr)
            dashboard.set_status(idx, "🔄 Checking…", "yellow")
            dashboard.log(f"[cyan]Checking {short}…[/]")

            def sub_log(msg: str) -> None:
                dashboard.log(f"  {msg}")

            orders = check_case(ct, cn, yr, log_fn=sub_log)
            known_uids = set(seen.get(key, []))

            if first_run:
                seen[key] = [o.uid() for o in orders]
                dashboard.set_status(idx, f"✓ Baseline: {len(orders)} orders", "green")
                dashboard.set_counts(idx, len(orders), 0)
                dashboard.log(
                    f"  [green]Baseline set: {len(orders)} existing order(s) indexed.[/]"
                )
            else:
                new_orders = [o for o in orders if o.uid() not in known_uids]
                all_uids = [o.uid() for o in orders]

                if new_orders:
                    for o in new_orders:
                        dashboard.log(f"  [bold red]🔔 NEW ORDER: {o.label}[/]")
                        send_mac_notification(
                            title="SCI Monitor — New Order",
                            message=f"{short}\n{o.label}",
                            subtitle=o.date or "New order uploaded",
                        )
                    seen[key] = list(known_uids | set(all_uids))
                    dashboard.set_status(
                        idx, f"🔔 {len(new_orders)} NEW order(s)!", "bold red"
                    )
                    dashboard.set_counts(idx, len(seen[key]), len(new_orders))
                else:
                    dashboard.set_status(idx, "✓ No new orders", "green")
                    dashboard.set_counts(idx, len(seen.get(key, [])), 0)
                    dashboard.log(f"  [green]No new orders for {short}.[/]")

        first_run = False
        save_seen_orders(seen)

        elapsed = time.time() - cycle_start
        sleep_secs = max(0, CHECK_INTERVAL - elapsed)
        next_check = time.time() + sleep_secs
        dashboard.set_next_check(next_check)
        dashboard.log(f"[dim]Cycle done. Next in {int(sleep_secs)}s.[/]")

        deadline = time.time() + sleep_secs
        while time.time() < deadline and dashboard._running:
            time.sleep(0.5)

    dashboard.log("[bold red]Monitor stopped.[/]")


# ──────────────────────────────────────────────────────────────────────────────
# Entry Point
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    force_reset = "--reset" in sys.argv

    console.rule("[bold cyan]Supreme Court of India — Case Monitor[/]")
    console.print()

    # 1. Setup / load cases
    config = interactive_setup(force=force_reset)
    cases = config.get("cases", [])
    active = [c for c in cases if c.get("case_type") and c.get("case_no") and c.get("year")]

    if not active:
        console.print("[red]No valid cases configured. Run again to set up cases.[/]")
        sys.exit(1)

    console.print(f"\n[bold green]Starting monitor for {len(active)} case(s)…[/]")
    console.print("[dim]Press Ctrl+C at any time to stop.[/]\n")
    time.sleep(1)

    # 2. Create dashboard
    dashboard = Dashboard(cases)

    # 3. Start monitor thread
    thread = threading.Thread(
        target=run_monitor, args=(config, dashboard), daemon=True
    )
    thread.start()

    # 4. Ctrl+C handler
    def _stop(sig, frame):
        console.print("\n\n[bold yellow]Stopping monitor…[/]")
        dashboard._running = False

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    # 5. Rich Live display loop
    with Live(
        dashboard.render(),
        console=console,
        refresh_per_second=2,
        screen=True,
    ) as live:
        while dashboard._running:
            live.update(dashboard.render())
            time.sleep(0.5)
        # Final render after stop
        live.update(dashboard.render())

    console.print("\n[bold green]Monitor stopped cleanly. Goodbye![/]\n")


if __name__ == "__main__":
    main()
