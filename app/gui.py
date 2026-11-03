"""
gui.py — Native macOS Desktop GUI for Supreme Court of India Case Monitor.
Built with CustomTkinter for high-contrast, modern UI in both Light & Dark modes.
"""

from __future__ import annotations

import os
import queue
import time
import tkinter as tk
from datetime import datetime
from typing import Any

# Ensure Tk deprecation warning is silenced
os.environ["TK_SILENCE_DEPRECATION"] = "1"

import customtkinter as ctk

from app import state
from app.monitor import Monitor
from app.scraper import CASE_TYPE_NAMES, CASE_TYPES

# Set default appearance
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class SCIMonitorApp(ctk.CTk):
    """Supreme Court of India Case Monitor Main Desktop Window."""

    CHECK_INTERVAL = 120  # seconds

    def __init__(self):
        super().__init__()

        self.title("Supreme Court of India — Case Monitor")
        self.geometry("1020x760")
        self.minsize(920, 680)

        # State management
        self._config = state.load_config()
        self._monitor: Monitor | None = None
        self._msg_queue: queue.Queue = queue.Queue()
        self._running = False
        self._next_check: float | None = None
        self._case_order_counts = [0, 0, 0]

        # Case type mappings
        sorted_types = sorted(CASE_TYPE_NAMES.items(), key=lambda x: int(x[0]))
        self._type_display_values = ["-- Select Case Type --"] + [
            f"{k}. {v}" for k, v in sorted_types
        ]
        self._display_to_key = {"-- Select Case Type --": ""}
        self._key_to_display = {"": "-- Select Case Type --"}
        for k, v in sorted_types:
            disp = f"{k}. {v}"
            self._display_to_key[disp] = k
            self._key_to_display[k] = disp

        # Build UI
        self._build_ui()
        self._load_config_into_ui()

        # Queue polling and timer updates
        self._poll_id = self.after(100, self._poll_queue)
        self._tick_id = self.after(1000, self._tick)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # -----------------------------------------------------------------------
    # UI Layout Construction
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Main scrollable container or root layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._build_header(row=0)
        self._build_config_card(row=1)
        self._build_dashboard_card(row=2)
        self._build_log_and_control_area(row=3)

    def _build_header(self, row: int) -> None:
        header_frame = ctk.CTkFrame(self, corner_radius=12, fg_color=("gray90", "gray17"))
        header_frame.grid(row=row, column=0, padx=20, pady=(16, 10), sticky="ew")
        header_frame.grid_columnconfigure(1, weight=1)

        # App Title & Subtitle
        title_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_box.grid(row=0, column=0, padx=16, pady=12, sticky="w")

        title_lbl = ctk.CTkLabel(
            title_box,
            text="🏛  Supreme Court of India — Case Monitor",
            font=ctk.CTkFont(family="SF Pro Display", size=20, weight="bold"),
        )
        title_lbl.pack(anchor="w")

        sub_lbl = ctk.CTkLabel(
            title_box,
            text="Monitors up to 3 cases on sci.gov.in every 120s • Auto-solves CAPTCHA • macOS native alerts",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray65"),
        )
        sub_lbl.pack(anchor="w")

        # Global Status Badge & Appearance Switch
        controls_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        controls_box.grid(row=0, column=2, padx=16, pady=12, sticky="e")

        self._global_status_badge = ctk.CTkLabel(
            controls_box,
            text="● IDLE",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=("gray45", "gray60"),
            fg_color=("gray82", "gray25"),
            corner_radius=8,
            padx=12,
            pady=4,
        )
        self._global_status_badge.pack(side="right", padx=(10, 0))

        appearance_menu = ctk.CTkOptionMenu(
            controls_box,
            values=["System", "Dark", "Light"],
            width=90,
            command=lambda v: ctk.set_appearance_mode(v),
            font=ctk.CTkFont(size=11),
        )
        appearance_menu.set("System")
        appearance_menu.pack(side="right")

    def _build_config_card(self, row: int) -> None:
        """Section for configuring up to 3 cases."""
        self.config_frame = ctk.CTkFrame(self, corner_radius=12)
        self.config_frame.grid(row=row, column=0, padx=20, pady=8, sticky="ew")
        self.config_frame.grid_columnconfigure(1, weight=3)
        self.config_frame.grid_columnconfigure(2, weight=1)
        self.config_frame.grid_columnconfigure(3, weight=1)

        # Title
        sec_title = ctk.CTkLabel(
            self.config_frame,
            text="📋  Case Configuration (Enter up to 3 cases to track)",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        sec_title.grid(row=0, column=0, columnspan=4, padx=16, pady=(14, 8), sticky="w")

        # Table Column Headers
        col_headers = [
            ("#", 0, ""),
            ("Case Type", 1, "w"),
            ("Case Number", 2, "w"),
            ("Filing / Case Year", 3, "w"),
        ]
        for col_name, col_idx, anchor in col_headers:
            h_lbl = ctk.CTkLabel(
                self.config_frame,
                text=col_name,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=("gray30", "gray70"),
            )
            h_lbl.grid(row=1, column=col_idx, padx=12, pady=(0, 6), sticky=anchor if anchor else None)

        # 3 Rows of inputs
        self._case_type_vars: list[ctk.StringVar] = []
        self._case_no_vars: list[ctk.StringVar] = []
        self._case_year_vars: list[ctk.StringVar] = []
        self._case_type_menus: list[ctk.CTkOptionMenu] = []
        self._case_no_entries: list[ctk.CTkEntry] = []
        self._case_year_entries: list[ctk.CTkEntry] = []

        current_year = str(datetime.now().year)

        for i in range(3):
            grid_row = i + 2

            # Index label
            idx_lbl = ctk.CTkLabel(
                self.config_frame,
                text=f"{i+1}.",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=("gray40", "gray60"),
                width=30,
            )
            idx_lbl.grid(row=grid_row, column=0, padx=(12, 6), pady=6)

            # Case Type OptionMenu
            ct_var = ctk.StringVar(value=self._type_display_values[0])
            self._case_type_vars.append(ct_var)
            ct_menu = ctk.CTkOptionMenu(
                self.config_frame,
                values=self._type_display_values,
                variable=ct_var,
                command=lambda *_: self._on_config_change(),
                font=ctk.CTkFont(size=12),
                dynamic_resizing=False,
            )
            ct_menu.grid(row=grid_row, column=1, padx=6, pady=6, sticky="ew")
            self._case_type_menus.append(ct_menu)

            # Case Number Entry
            cn_var = ctk.StringVar()
            self._case_no_vars.append(cn_var)
            cn_entry = ctk.CTkEntry(
                self.config_frame,
                textvariable=cn_var,
                placeholder_text="e.g. 1234",
                font=ctk.CTkFont(size=13),
            )
            cn_entry.grid(row=grid_row, column=2, padx=6, pady=6, sticky="ew")
            cn_entry.bind("<KeyRelease>", lambda *_: self._on_config_change())
            self._case_no_entries.append(cn_entry)

            # Year Entry
            yr_var = ctk.StringVar(value=current_year)
            self._case_year_vars.append(yr_var)
            yr_entry = ctk.CTkEntry(
                self.config_frame,
                textvariable=yr_var,
                placeholder_text="YYYY",
                font=ctk.CTkFont(size=13),
            )
            yr_entry.grid(row=grid_row, column=3, padx=(6, 16), pady=6, sticky="ew")
            yr_entry.bind("<KeyRelease>", lambda *_: self._on_config_change())
            self._case_year_entries.append(yr_entry)

        # Padding at bottom of card
        ctk.CTkLabel(self.config_frame, text="", height=4).grid(
            row=5, column=0, columnspan=4
        )

    def _build_dashboard_card(self, row: int) -> None:
        """Section showing active status and order count badges for all 3 cases."""
        self.dash_frame = ctk.CTkFrame(self, corner_radius=12)
        self.dash_frame.grid(row=row, column=0, padx=20, pady=8, sticky="ew")
        self.dash_frame.grid_columnconfigure((0, 1, 2), weight=1)

        sec_title = ctk.CTkLabel(
            self.dash_frame,
            text="📡  Active Monitoring Dashboard",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        sec_title.grid(row=0, column=0, columnspan=3, padx=16, pady=(12, 8), sticky="w")

        self._dash_cards = []
        self._dash_title_lbls = []
        self._dash_status_lbls = []
        self._dash_orders_lbls = []

        for i in range(3):
            sub_card = ctk.CTkFrame(
                self.dash_frame,
                corner_radius=10,
                fg_color=("gray88", "gray20"),
                border_width=1,
                border_color=("gray75", "gray30"),
            )
            sub_card.grid(row=1, column=i, padx=10, pady=(0, 14), sticky="nsew")

            t_lbl = ctk.CTkLabel(
                sub_card,
                text=f"Case {i+1}: Not Configured",
                font=ctk.CTkFont(size=13, weight="bold"),
            )
            t_lbl.pack(anchor="w", padx=12, pady=(10, 2))

            s_lbl = ctk.CTkLabel(
                sub_card,
                text="○ Idle — Waiting for details",
                font=ctk.CTkFont(size=11),
                text_color=("gray45", "gray60"),
            )
            s_lbl.pack(anchor="w", padx=12, pady=2)

            o_lbl = ctk.CTkLabel(
                sub_card,
                text="0 orders logged",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=("gray50", "gray60"),
            )
            o_lbl.pack(anchor="w", padx=12, pady=(2, 10))

            self._dash_cards.append(sub_card)
            self._dash_title_lbls.append(t_lbl)
            self._dash_status_lbls.append(s_lbl)
            self._dash_orders_lbls.append(o_lbl)

    def _build_log_and_control_area(self, row: int) -> None:
        """Control bar and activity logging view."""
        bottom_frame = ctk.CTkFrame(self, corner_radius=12)
        bottom_frame.grid(row=row, column=0, padx=20, pady=(8, 16), sticky="nsew")
        bottom_frame.grid_columnconfigure(0, weight=1)
        bottom_frame.grid_rowconfigure(1, weight=1)

        # Controls row
        ctrl_bar = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        ctrl_bar.grid(row=0, column=0, padx=16, pady=(12, 8), sticky="ew")

        self._toggle_btn = ctk.CTkButton(
            ctrl_bar,
            text="▶  Start Monitoring",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#2ecc71",
            hover_color="#27ae60",
            height=40,
            width=200,
            corner_radius=10,
            command=self._toggle_monitoring,
        )
        self._toggle_btn.pack(side="left")

        self._countdown_lbl = ctk.CTkLabel(
            ctrl_bar,
            text="Check Interval: 120s  •  Monitoring: Inactive",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray65"),
        )
        self._countdown_lbl.pack(side="left", padx=16)

        clear_btn = ctk.CTkButton(
            ctrl_bar,
            text="Clear Logs",
            width=90,
            height=30,
            fg_color=("gray75", "gray28"),
            hover_color=("gray65", "gray35"),
            text_color=("black", "white"),
            font=ctk.CTkFont(size=11),
            command=self._clear_log,
        )
        clear_btn.pack(side="right")

        # Live Activity Log text box
        self._log_box = ctk.CTkTextbox(
            bottom_frame,
            font=ctk.CTkFont(family="Courier", size=12),
            corner_radius=8,
            border_width=1,
            border_color=("gray80", "gray25"),
            wrap="word",
        )
        self._log_box.grid(row=1, column=0, padx=16, pady=(0, 14), sticky="nsew")
        self._log_box.configure(state="disabled")

    # -----------------------------------------------------------------------
    # Config & Dashboard Sync
    # -----------------------------------------------------------------------

    def _load_config_into_ui(self) -> None:
        cases = self._config.get("cases", [{}, {}, {}])
        for i in range(3):
            case = cases[i] if i < len(cases) else {}
            ct_key = case.get("case_type", "")
            disp = self._key_to_display.get(ct_key, self._type_display_values[0])
            self._case_type_vars[i].set(disp)
            self._case_no_vars[i].set(case.get("case_no", ""))
            self._case_year_vars[i].set(case.get("year", str(datetime.now().year)))
        self._refresh_dashboard()

    def _collect_config(self) -> dict[str, Any]:
        cases = []
        for i in range(3):
            disp = self._case_type_vars[i].get()
            ct_key = self._display_to_key.get(disp, "")
            cases.append({
                "case_type": ct_key,
                "case_no": self._case_no_vars[i].get().strip(),
                "year": self._case_year_vars[i].get().strip(),
            })
        self._config["cases"] = cases
        return self._config

    def _on_config_change(self, *_) -> None:
        self._collect_config()
        state.save_config(self._config)
        self._refresh_dashboard()
        if self._monitor:
            self._monitor.update_config(self._config)

    def _refresh_dashboard(self) -> None:
        cases = self._config.get("cases", [{}, {}, {}])
        for i in range(3):
            case = cases[i] if i < len(cases) else {}
            ct = case.get("case_type", "")
            cn = case.get("case_no", "").strip()
            yr = case.get("year", "").strip()

            if ct and cn and yr:
                short_name = f"{CASE_TYPES.get(ct, ct)} {cn}/{yr}"
                self._dash_title_lbls[i].configure(text=f"Case {i+1}: {short_name}")
                if self._running:
                    self._dash_status_lbls[i].configure(
                        text="● Active — Monitoring every 120s",
                        text_color="#2ecc71",
                    )
                else:
                    self._dash_status_lbls[i].configure(
                        text="○ Configured — Ready to monitor",
                        text_color=("gray45", "gray65"),
                    )
                count = self._case_order_counts[i]
                self._dash_orders_lbls[i].configure(
                    text=f"{count} order(s) logged" if count else "No orders logged yet",
                    text_color="#3498db" if count else ("gray50", "gray60"),
                )
            else:
                self._dash_title_lbls[i].configure(text=f"Case {i+1}: Not Configured")
                self._dash_status_lbls[i].configure(
                    text="○ Fill Case Type, Number & Year above",
                    text_color=("gray50", "gray55"),
                )
                self._dash_orders_lbls[i].configure(
                    text="—",
                    text_color=("gray50", "gray55"),
                )

    # -----------------------------------------------------------------------
    # Logging
    # -----------------------------------------------------------------------

    def _append_log(self, text: str) -> None:
        self._log_box.configure(state="normal")
        self._log_box.insert("end", text + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _clear_log(self) -> None:
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    # -----------------------------------------------------------------------
    # Monitoring Controls
    # -----------------------------------------------------------------------

    def _toggle_monitoring(self) -> None:
        if self._running:
            self._stop_monitoring()
        else:
            self._start_monitoring()

    def _start_monitoring(self) -> None:
        cfg = self._collect_config()
        active = [
            c for c in cfg["cases"]
            if c.get("case_type") and c.get("case_no") and c.get("year")
        ]

        if not active:
            self._append_log("=" * 60)
            self._append_log("⚠ CANNOT START: No complete case details configured!")
            self._append_log(
                "  Please select a Case Type, enter a Case Number (e.g. 1234), "
                "and Year (e.g. 2024) in Row 1 above."
            )
            self._append_log("=" * 60)
            return

        self._running = True
        self._toggle_btn.configure(
            text="⏹  Stop Monitoring",
            fg_color="#e74c3c",
            hover_color="#c0392b",
        )
        self._global_status_badge.configure(
            text="● MONITORING",
            text_color="#2ecc71",
            fg_color=("#e8f8f0", "#163826"),
        )

        self._refresh_dashboard()
        self._monitor = Monitor(self._msg_queue, cfg)
        self._monitor.start()

    def _stop_monitoring(self) -> None:
        self._running = False
        self._next_check = None
        self._countdown_lbl.configure(
            text="Check Interval: 120s  •  Monitoring: Inactive"
        )
        if self._monitor:
            self._monitor.stop()

        self._toggle_btn.configure(
            text="▶  Start Monitoring",
            fg_color="#2ecc71",
            hover_color="#27ae60",
        )
        self._global_status_badge.configure(
            text="● IDLE",
            text_color=("gray45", "gray60"),
            fg_color=("gray82", "gray25"),
        )
        self._refresh_dashboard()

    # -----------------------------------------------------------------------
    # Queue Consumer & Ticker
    # -----------------------------------------------------------------------

    def _poll_queue(self) -> None:
        try:
            while True:
                msg = self._msg_queue.get_nowait()
                self._handle_msg(msg)
        except queue.Empty:
            pass
        self._poll_id = self.after(100, self._poll_queue)

    def _handle_msg(self, msg: dict[str, Any]) -> None:
        mtype = msg.get("type", "")
        text = msg.get("text", "")
        idx = msg.get("case_index")

        if mtype == "log":
            self._append_log(text)

        elif mtype == "status":
            if idx is not None and 0 <= idx < 3:
                self._dash_status_lbls[idx].configure(text=f"● {text}")
                count = msg.get("order_count")
                if count is not None:
                    self._case_order_counts[idx] = count
                    self._dash_orders_lbls[idx].configure(
                        text=f"{count} order(s) logged"
                    )

        elif mtype == "cycle_end":
            self._next_check = msg.get("next_check")

    def _tick(self) -> None:
        if self._running and self._next_check is not None:
            remaining = max(0, int(self._next_check - time.time()))
            mins, secs = divmod(remaining, 60)
            self._countdown_lbl.configure(
                text=f"Next check in {mins:02d}:{secs:02d}  •  Interval: 120s"
            )
        self._tick_id = self.after(1000, self._tick)

    # -----------------------------------------------------------------------
    # Window Close Handler
    # -----------------------------------------------------------------------

    def _on_close(self) -> None:
        if hasattr(self, "_poll_id"):
            try:
                self.after_cancel(self._poll_id)
            except Exception:
                pass
        if hasattr(self, "_tick_id"):
            try:
                self.after_cancel(self._tick_id)
            except Exception:
                pass

        self._collect_config()
        state.save_config(self._config)

        if self._monitor:
            self._monitor.stop()

        try:
            self.quit()
            self.destroy()
        except Exception:
            pass
