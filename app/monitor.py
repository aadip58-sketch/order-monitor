"""
monitor.py — Background monitoring daemon for SCI Case Monitor.

Runs in a dedicated daemon thread so it never blocks the GUI.

Communication with the GUI:
  - Inbound:  threading.Event (stop signal)
  - Outbound: queue.Queue with typed message dicts

Message dict schema
-------------------
{
    "type": "log" | "status" | "new_order" | "cycle_start" | "cycle_end",
    "text": str,               # human-readable log line
    "case_index": int | None,  # 0-based index into cases list
    "case_key": str | None,
    "order": Order | None,     # only for "new_order"
    "next_check": float | None # epoch of next check (for countdown)
}
"""

from __future__ import annotations

import queue
import threading
import time
from datetime import datetime
from typing import Any

from app import state
from app.scraper import check_case, Order, CASE_TYPES
from app.notifier import send_mac_notification


CHECK_INTERVAL = 120  # seconds


# ---------------------------------------------------------------------------
# Message helpers
# ---------------------------------------------------------------------------

def _msg(type_: str, text: str, **kw) -> dict:
    return {"type": type_, "text": text, **kw}


# ---------------------------------------------------------------------------
# Monitor class
# ---------------------------------------------------------------------------

class Monitor:
    """
    Manages the background monitoring loop.

    Usage:
        m = Monitor(out_queue)
        m.start()
        ...
        m.stop()
    """

    def __init__(self, out_queue: queue.Queue, config: dict[str, Any]):
        self._q = out_queue
        self._config = config
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._seen_orders: dict[str, list[str]] = state.load_seen_orders()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="sci-monitor"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def update_config(self, config: dict[str, Any]) -> None:
        """Update config (thread-safe; takes effect next cycle)."""
        self._config = config

    # -----------------------------------------------------------------------
    # Internal loop
    # -----------------------------------------------------------------------

    def _post(self, type_: str, text: str, **kw) -> None:
        self._q.put(_msg(type_, text, **kw))

    def _log(self, text: str, case_index: int | None = None) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {text}"
        self._post("log", line, case_index=case_index)

    def _run(self) -> None:
        self._log("🟢 Monitoring started.")
        first_run = True

        while not self._stop_event.is_set():
            cycle_start = time.time()
            self._post("cycle_start", "")
            self._log("─" * 48)
            self._log("🔄 Starting check cycle…")

            cases = self._config.get("cases", [])
            active_cases = [
                (i, c) for i, c in enumerate(cases)
                if c.get("case_type") and c.get("case_no") and c.get("year")
            ]

            if not active_cases:
                self._log("⚠ No cases configured. Waiting…")
            else:
                for idx, case in active_cases:
                    if self._stop_event.is_set():
                        break
                    self._check_one_case(idx, case, first_run)

            first_run = False

            # Save seen orders after every cycle
            state.save_seen_orders(self._seen_orders)

            # Calculate sleep accounting for elapsed time
            elapsed = time.time() - cycle_start
            interval = self._config.get("check_interval", CHECK_INTERVAL)
            sleep_secs = max(0, interval - elapsed)
            next_check = time.time() + sleep_secs
            self._post("cycle_end", "", next_check=next_check)
            self._log(f"✅ Cycle complete. Next check in {int(sleep_secs)}s.")

            # Sleep in small increments so stop_event is checked frequently
            deadline = time.time() + sleep_secs
            while time.time() < deadline and not self._stop_event.is_set():
                time.sleep(min(1.0, deadline - time.time()))

        self._log("🔴 Monitoring stopped.")

    def _check_one_case(
        self,
        idx: int,
        case: dict[str, str],
        first_run: bool,
    ) -> None:
        ct = case["case_type"]
        cn = case["case_no"]
        yr = case["year"]
        short = f"{CASE_TYPES.get(ct, ct)} {cn}/{yr}"
        key = state.make_case_key(ct, cn, yr)

        self._log(f"📋 Checking {short}…", case_index=idx)
        self._post("status", f"Checking…", case_index=idx)

        def sub_log(msg: str) -> None:
            self._log(msg, case_index=idx)

        orders = check_case(ct, cn, yr, log_fn=sub_log)

        known_uids = set(self._seen_orders.get(key, []))

        if first_run:
            # Baseline: store all current orders without alerting
            new_uids = [o.uid() for o in orders]
            self._seen_orders[key] = new_uids
            self._log(
                f"    📌 Baseline set: {len(orders)} existing order(s) stored.",
                case_index=idx,
            )
            self._post(
                "status",
                f"Baseline loaded ({len(orders)} orders)",
                case_index=idx,
                order_count=len(orders),
            )
        else:
            new_orders = [o for o in orders if o.uid() not in known_uids]
            all_uids = [o.uid() for o in orders]

            if new_orders:
                for order in new_orders:
                    self._log(
                        f"    🔔 NEW ORDER: {order.label}",
                        case_index=idx,
                    )
                    self._post(
                        "new_order",
                        f"🔔 NEW ORDER for {short}: {order.label}",
                        case_index=idx,
                        case_key=key,
                        order=order,
                    )
                    send_mac_notification(
                        title=f"SCI Monitor — New Order",
                        message=f"{short}\n{order.label}",
                        subtitle=order.date or "New order uploaded",
                        sound="Glass",
                    )
                # Merge new UIDs into stored list
                self._seen_orders[key] = list(known_uids | set(all_uids))
            else:
                self._log(f"    ✓ No new orders.", case_index=idx)

            total = len(self._seen_orders.get(key, []))
            self._post(
                "status",
                f"Active — {len(new_orders)} new, {total} total",
                case_index=idx,
                order_count=total,
                new_count=len(new_orders),
            )
