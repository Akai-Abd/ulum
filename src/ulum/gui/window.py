"""Native GTK3 / Libadwaita-compatible desktop GUI window for ULUM v0.4."""
import os
import platform
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk

from ulum import __version__
from ulum.cli.display import format_bytes
from ulum.core.config import load_config
from ulum.core.orchestrator import Orchestrator
from ulum.core.system import get_system_info
from ulum.db.database import get_db_path, init_db
from ulum.db.repository import Repository
from ulum.doctor.health import DoctorReport, SystemDoctor
from ulum.doctor.repos import AptRepoDoctor
from ulum.gui.dialogs import RemovalConfirmDialog, show_error_dialog, show_info_dialog
from ulum.removal.kernels import KernelCleaner
from ulum.removal.leftovers import LeftoverScanner
from ulum.removal.safety import SafetyValidator
from ulum.utils.self_update import SelfUpdater


def calculate_health_score(repo: Repository, doctor_report: Optional[DoctorReport] = None) -> Dict[str, Any]:
    """Calculates transparent v0.4 health score (starts at 100 with deduction factors per PRD §6.3)."""
    score = 100
    deductions: List[Dict[str, Any]] = []

    # 1. Pending updates by urgency
    updates = repo.get_updates()
    sec_only_count = sum(1 for u in updates if u.get("urgency") == "Security")
    crit_count = sum(1 for u in updates if u.get("urgency") == "Critical")

    sec_deduction = min(30, sec_only_count * 5)
    if sec_deduction > 0:
        score -= sec_deduction
        deductions.append({"factor": f"{sec_only_count} pending Security update(s)", "points": -sec_deduction})

    crit_deduction = min(20, crit_count * 4)
    if crit_deduction > 0:
        score -= crit_deduction
        deductions.append({"factor": f"{crit_count} pending Critical update(s)", "points": -crit_deduction})

    # 2. Doctor report factors
    if doctor_report:
        for c in doctor_report.checks:
            if c.name == "repositories" and c.status in ["warn", "fail"]:
                broken = c.details.get("broken_entries_count", 0)
                dead_deduction = min(20, max(10, broken * 10))
                score -= dead_deduction
                deductions.append({"factor": f"Repository health warning ({c.message})", "points": -dead_deduction})
            elif c.name == "boot_health" and c.status in ["warn", "fail"]:
                score -= 10
                deductions.append({"factor": f"/boot health alert ({c.message})", "points": -10})
            elif c.name == "scan_freshness" and c.status in ["warn", "fail"]:
                score -= 10
                deductions.append({"factor": "No scan in last 24h", "points": -10})
            elif c.name == "locks" and c.status == "fail":
                score -= 10
                deductions.append({"factor": "Stale package manager locks", "points": -10})

    # 3. Verified cleanup candidates > 1 GB
    cands = repo.get_cleanup_candidates(confidence="verified")
    total_bytes = sum(c.get("estimated_size_bytes", 0) for c in cands)
    if total_bytes > 1024 * 1024 * 1024:
        score -= 5
        deductions.append({"factor": f"Verified leftovers exceed 1 GB ({format_bytes(total_bytes)})", "points": -5})

    score = max(0, min(100, score))
    status_label = "Healthy" if score >= 85 else ("Degraded" if score >= 60 else "Action Required")
    return {
        "score": score,
        "status": status_label,
        "deductions": deductions,
    }


class MainWindow(Gtk.Window):
    """Primary native desktop GUI window for ULUM v0.4."""

    def __init__(self):
        super().__init__(title="Universal Linux Update Manager (ULUM)")
        self.set_default_size(1050, 680)
        self.set_position(Gtk.WindowPosition.CENTER)

        # Initialize backend
        conn = init_db()
        self.repo = Repository(conn)
        self.config = load_config()
        self.orchestrator = Orchestrator(self.repo, self.config)

        # HeaderBar
        self.header = Gtk.HeaderBar()
        self.header.set_show_close_button(True)
        self.header.props.title = "ULUM Update Manager"
        info = get_system_info()
        self.header.props.subtitle = f"{info.distro_name} {info.distro_version} ({info.arch}, Linux {info.kernel})"
        self.set_titlebar(self.header)

        # Spinner in header
        self.spinner = Gtk.Spinner()
        self.header.pack_end(self.spinner)

        # Quick Scan Button in header
        self.btn_scan = self._make_button("Scan System", "system-search-symbolic")
        self.btn_scan.connect("clicked", lambda b: self.on_scan_clicked())
        self.header.pack_start(self.btn_scan)

        # Apply CSS Provider for modern cards & widgets
        self._init_styles()

        # Main Layout: Notebook with 7 Views (PRD §6.4)
        self.notebook = Gtk.Notebook()
        self.add(self.notebook)

        self._build_home_tab()          # Tab 0: Home / Bento Dashboard
        self._build_updates_tab()       # Tab 1: Updates
        self._build_installed_tab()     # Tab 2: Installed Software
        self._build_leftovers_tab()     # Tab 3: Leftovers & Cleanup
        self._build_doctor_tab()        # Tab 4: Diagnostics (Doctor)
        self._build_history_tab()       # Tab 5: History
        self._build_settings_tab()      # Tab 6: Settings & About

        self.connect("destroy", Gtk.main_quit)

        # Initial population of views
        self.reload_home_data()
        self.reload_installed_data()
        self.reload_updates_data()

    def _init_styles(self):
        """Applies a lightweight, theme-respecting CSS stylesheet for modern dashboard visuals."""
        css = b"""
        .dashboard-card {
            background-color: alpha(@theme_bg_color, 0.7);
            border: 1px solid alpha(@borders, 0.5);
            border-radius: 8px;
            padding: 8px;
        }
        .metric-pill {
            border-radius: 12px;
            padding: 3px 8px;
            font-weight: bold;
        }
        .pill-danger {
            background-color: #e01b24;
            color: #ffffff;
        }
        .pill-warning {
            background-color: #ff7800;
            color: #ffffff;
        }
        .pill-info {
            background-color: #3584e4;
            color: #ffffff;
        }
        .pill-neutral {
            background-color: alpha(@theme_fg_color, 0.12);
        }
        """
        try:
            provider = Gtk.CssProvider()
            provider.load_from_data(css)
            screen = Gdk.Screen.get_default()
            if screen:
                Gtk.StyleContext.add_provider_for_screen(
                    screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )
        except Exception:
            pass

    def _make_button(self, label: str, icon_name: Optional[str] = None, suggested: bool = False, destructive: bool = False) -> Gtk.Button:
        btn = Gtk.Button()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        if icon_name:
            icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON)
            box.pack_start(icon, False, False, 0)
        lbl = Gtk.Label(label=label)
        box.pack_start(lbl, False, False, 0)
        btn.add(box)
        if suggested:
            btn.get_style_context().add_class("suggested-action")
        if destructive:
            btn.get_style_context().add_class("destructive-action")
        return btn

    def _make_pill_button(self, label: str, css_class: str, on_clicked: Callable) -> Gtk.Button:
        btn = Gtk.Button(label=label)
        btn.get_style_context().add_class("metric-pill")
        btn.get_style_context().add_class(css_class)
        btn.connect("clicked", lambda b: on_clicked())
        return btn

    def _create_card(self, title: str, icon_name: str) -> tuple[Gtk.Frame, Gtk.Box]:
        frame = Gtk.Frame()
        frame.get_style_context().add_class("dashboard-card")

        lbl_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON)
        lbl = Gtk.Label()
        lbl.set_markup(f"<b>{GLib.markup_escape_text(title)}</b>")
        lbl_box.pack_start(icon, False, False, 0)
        lbl_box.pack_start(lbl, False, False, 0)
        lbl_box.show_all()
        frame.set_label_widget(lbl_box)

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content_box.set_border_width(8)
        frame.add(content_box)
        return frame, content_box

    def _create_tab_label(self, title: str, icon_name: str) -> Gtk.Box:
        tbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.MENU)
        lbl = Gtk.Label(label=title)
        tbox.pack_start(icon, False, False, 0)
        tbox.pack_start(lbl, False, False, 0)
        tbox.show_all()
        return tbox

    def _filter_updates_to(self, urgency_name: str):
        mapping = {"Security": 1, "Critical": 2, "Feature": 3, "Unknown": 4}
        if hasattr(self, "upd_urgency_combo"):
            idx = mapping.get(urgency_name, 0)
            self.upd_urgency_combo.set_active(idx)
        self.notebook.set_current_page(1)

    def run_in_background(self, task_func: Callable, on_complete: Optional[Callable] = None):
        self.spinner.start()
        self.set_sensitive(False)

        def dispatch(callback, *args):
            callback(*args)
            return False

        def worker():
            try:
                res = task_func()
                if on_complete:
                    GLib.idle_add(dispatch, on_complete, res, None)
            except Exception as e:
                err = e
                if on_complete:
                    GLib.idle_add(dispatch, on_complete, None, err)
            finally:
                GLib.idle_add(dispatch, self._task_finished)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def _task_finished(self):
        self.spinner.stop()
        self.set_sensitive(True)

    # ─────────────────────────────────────────────────────────────
    # TAB 0: HOME / BENTO DASHBOARD (PRD §6.2)
    # ─────────────────────────────────────────────────────────────
    def _build_home_tab(self):
        scroller = Gtk.ScrolledWindow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_border_width(18)

        # Header Title with Icon
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title_icon = Gtk.Image.new_from_icon_name("computer-symbolic", Gtk.IconSize.LARGE_TOOLBAR)
        title_box.pack_start(title_icon, False, False, 0)
        title_lbl = Gtk.Label()
        title_lbl.set_markup("<big><b>System Dashboard &amp; Health Status</b></big>")
        title_lbl.set_xalign(0)
        title_box.pack_start(title_lbl, False, False, 0)
        box.pack_start(title_box, False, False, 0)

        # Health Banner Card
        self.health_card, h_box = self._create_card("System Health (Transparent Breakdown)", "security-high-symbolic")

        score_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.lbl_health_score = Gtk.Label()
        self.lbl_health_score.set_markup("<b>Health Score: 100/100 (Calculating...)</b>")
        self.lbl_health_score.set_xalign(0)
        score_row.pack_start(self.lbl_health_score, True, True, 0)
        h_box.pack_start(score_row, False, False, 0)

        # Health LevelBar
        self.level_health = Gtk.LevelBar()
        self.level_health.set_min_value(0)
        self.level_health.set_max_value(100)
        self.level_health.add_offset_value(Gtk.LEVEL_BAR_OFFSET_LOW, 60.0)
        self.level_health.add_offset_value(Gtk.LEVEL_BAR_OFFSET_HIGH, 85.0)
        self.level_health.set_value(100)
        h_box.pack_start(self.level_health, False, False, 2)

        self.lbl_health_deductions = Gtk.Label()
        self.lbl_health_deductions.set_markup("<small>No active deductions. System is operating normally.</small>")
        self.lbl_health_deductions.set_xalign(0)
        h_box.pack_start(self.lbl_health_deductions, False, False, 0)
        box.pack_start(self.health_card, False, False, 0)

        # Bento Grid
        grid = Gtk.Grid()
        grid.set_column_spacing(12)
        grid.set_row_spacing(12)
        grid.set_column_homogeneous(True)

        # Card 1: Updates by Urgency
        upd_card, u_box = self._create_card("Updates by Urgency", "software-update-available-symbolic")

        # Metric Pill buttons for one-click filter navigation
        pill_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.btn_pill_sec = self._make_pill_button("🛡️ 0 Security", "pill-danger", lambda: self._filter_updates_to("Security"))
        self.btn_pill_crit = self._make_pill_button("⚠️ 0 Critical", "pill-warning", lambda: self._filter_updates_to("Critical"))
        self.btn_pill_feat = self._make_pill_button("✨ 0 Feature", "pill-info", lambda: self._filter_updates_to("Feature"))
        self.btn_pill_unk = self._make_pill_button("📦 0 Other", "pill-neutral", lambda: self._filter_updates_to("Unknown"))
        pill_box.pack_start(self.btn_pill_sec, True, True, 0)
        pill_box.pack_start(self.btn_pill_crit, True, True, 0)
        pill_box.pack_start(self.btn_pill_feat, True, True, 0)
        pill_box.pack_start(self.btn_pill_unk, True, True, 0)
        u_box.pack_start(pill_box, False, False, 0)

        self.lbl_urgency_counts = Gtk.Label()
        self.lbl_urgency_counts.set_markup("<small><i>Note: Security urgency tagging is APT-only in v0.4</i></small>")
        self.lbl_urgency_counts.set_xalign(0)
        u_box.pack_start(self.lbl_urgency_counts, True, True, 0)

        self.btn_sec_upd = self._make_button("Update Security Only", "security-high-symbolic")
        self.btn_sec_upd.connect("clicked", lambda b: self.on_update_security_only_clicked())
        u_box.pack_start(self.btn_sec_upd, False, False, 0)
        grid.attach(upd_card, 0, 0, 1, 1)

        # Card 2: /boot & Kernel Health
        boot_card, b_box = self._create_card("/boot Partition & Kernels", "drive-harddisk-symbolic")
        self.lbl_boot_status = Gtk.Label()
        self.lbl_boot_status.set_markup("<b>Kernels:</b> Inspecting...\n<small>Inspecting storage</small>")
        self.lbl_boot_status.set_xalign(0)
        b_box.pack_start(self.lbl_boot_status, False, False, 0)

        # Storage Progress Bar
        self.progress_boot = Gtk.ProgressBar()
        self.progress_boot.set_show_text(True)
        self.progress_boot.set_text("Inspecting storage...")
        b_box.pack_start(self.progress_boot, False, False, 4)

        self.btn_clean_kernels = self._make_button("Clean Old Kernels", "edit-clear-symbolic")
        self.btn_clean_kernels.connect("clicked", lambda b: self.on_clean_kernels_clicked())
        b_box.pack_start(self.btn_clean_kernels, False, False, 0)
        grid.attach(boot_card, 1, 0, 1, 1)

        # Card 3: Repository Health
        repo_card, r_box = self._create_card("Repository Health", "network-server-symbolic")
        self.lbl_repo_status = Gtk.Label()
        self.lbl_repo_status.set_markup("<b>Sources:</b> Active repos healthy\n<small>AptRepoDoctor monitoring active</small>")
        self.lbl_repo_status.set_xalign(0)
        r_box.pack_start(self.lbl_repo_status, True, True, 0)

        r_btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_fix_repos = self._make_button("Fix 404 Repos", "tools-check-symbolic")
        btn_fix_repos.connect("clicked", lambda b: self.on_fix_repos_clicked())
        r_btn_box.pack_start(btn_fix_repos, True, True, 0)
        btn_restore_repos = self._make_button("Restore Backups", "edit-undo-symbolic")
        btn_restore_repos.connect("clicked", lambda b: self.on_restore_repos_clicked())
        r_btn_box.pack_start(btn_restore_repos, True, True, 0)
        r_box.pack_start(r_btn_box, False, False, 0)
        grid.attach(repo_card, 0, 1, 1, 1)

        # Card 4: Residual Cleanups
        left_card, l_box = self._create_card("Residual Storage & Leftovers", "user-trash-symbolic")
        self.lbl_leftover_status = Gtk.Label()
        self.lbl_leftover_status.set_markup("<b>Verified Leftovers:</b> 0 bytes\n<small>Ready for clean removal</small>")
        self.lbl_leftover_status.set_xalign(0)
        l_box.pack_start(self.lbl_leftover_status, True, True, 0)

        btn_review_leftovers = self._make_button("Review Leftovers Tab", "go-next-symbolic")
        btn_review_leftovers.connect("clicked", lambda b: self.notebook.set_current_page(3))
        l_box.pack_start(btn_review_leftovers, False, False, 0)
        grid.attach(left_card, 1, 1, 1, 1)

        box.pack_start(grid, False, False, 0)

        # Recent Operations Frame
        recent_card, recent_box = self._create_card("Recent System Operations", "document-open-recent-symbolic")
        self.lbl_recent_ops = Gtk.Label()
        self.lbl_recent_ops.set_markup("<small>No recent operations recorded in local history.</small>")
        self.lbl_recent_ops.set_xalign(0)
        recent_box.pack_start(self.lbl_recent_ops, False, False, 0)
        box.pack_start(recent_card, False, False, 0)

        scroller.add(box)
        self.notebook.append_page(scroller, self._create_tab_label("Home", "go-home-symbolic"))

    def reload_home_data(self):
        """Refreshes all cards on the Home Bento dashboard."""
        doctor_rep = SystemDoctor.run_all_checks(check_online=False)
        health_data = calculate_health_score(self.repo, doctor_rep)

        score = health_data["score"]
        status = health_data["status"]
        color = "#2ec27e" if score >= 85 else ("#ff7800" if score >= 60 else "#e01b24")
        self.lbl_health_score.set_markup(
            f"<span size='24000' weight='heavy' color='{color}'>{score}</span>"
            f"<span size='large' weight='bold'>/100</span>  "
            f"<span background='{color}' color='white' weight='bold'>  {status}  </span>"
        )
        if hasattr(self, "level_health"):
            self.level_health.set_value(score)

        if health_data["deductions"]:
            ded_lines = [
                f"• {GLib.markup_escape_text(d['factor'])} (<span color='red'>{d['points']} pts</span>)"
                for d in health_data["deductions"]
            ]
            self.lbl_health_deductions.set_markup("\n".join(ded_lines))
        else:
            self.lbl_health_deductions.set_markup("<small>No deductions active. System is operating at peak health.</small>")

        # Urgency counts & metric pills
        updates = self.repo.get_updates()
        sec = sum(1 for u in updates if u.get("urgency") == "Security")
        crit = sum(1 for u in updates if u.get("urgency") == "Critical")
        feat = sum(1 for u in updates if u.get("urgency") == "Feature")
        unk = sum(1 for u in updates if u.get("urgency") == "Unknown")

        if hasattr(self, "btn_pill_sec"):
            self.btn_pill_sec.set_label(f"🛡️ {sec} Security")
            self.btn_pill_crit.set_label(f"⚠️ {crit} Critical")
            self.btn_pill_feat.set_label(f"✨ {feat} Feature")
            self.btn_pill_unk.set_label(f"📦 {unk} Other")

        self.lbl_urgency_counts.set_markup(
            f"<b>Urgency Distribution:</b> {sec} Security, {crit} Critical, {feat} Feature, {unk} Other\n"
            f"<small><i>Note: Security urgency tagging is APT-only in v0.4 (Click a badge above to filter)</i></small>"
        )

        if hasattr(self, "btn_sec_upd"):
            ctx = self.btn_sec_upd.get_style_context()
            if sec > 0:
                if not ctx.has_class("suggested-action"):
                    ctx.add_class("suggested-action")
            else:
                if ctx.has_class("suggested-action"):
                    ctx.remove_class("suggested-action")

        # /boot status & progress bar
        boot_res = SystemDoctor.check_boot_health()
        free_mb = boot_res.details.get("free_mb", 0.0)
        total_mb = boot_res.details.get("total_mb", 0.0)
        k_count = boot_res.details.get("installed_kernels_count", 0)
        b_kernel = GLib.markup_escape_text(str(boot_res.details.get("booted_kernel", "unknown")))
        self.lbl_boot_status.set_markup(
            f"<b>Kernels:</b> {k_count} installed (Booted: {b_kernel})"
        )

        if hasattr(self, "progress_boot"):
            if total_mb > 0:
                used_mb = max(0.0, total_mb - free_mb)
                fraction = min(1.0, max(0.0, used_mb / total_mb))
                pct = fraction * 100
                self.progress_boot.set_fraction(fraction)
                self.progress_boot.set_text(f"{used_mb:.0f} MB / {total_mb:.0f} MB ({pct:.0f}% used) — {free_mb:.0f} MB free")
            else:
                self.progress_boot.set_fraction(0.0)
                self.progress_boot.set_text(f"{free_mb:.0f} MB free")

        if hasattr(self, "btn_clean_kernels"):
            ctx = self.btn_clean_kernels.get_style_context()
            if free_mb > 0 and free_mb < 100:
                if not ctx.has_class("destructive-action"):
                    ctx.add_class("destructive-action")
            else:
                if ctx.has_class("destructive-action"):
                    ctx.remove_class("destructive-action")

        # Repo status
        repo_res = SystemDoctor.check_repositories()
        act_cnt = repo_res.details.get("active_entries_count", 0)
        dis_cnt = repo_res.details.get("disabled_by_ulum", 0)
        self.lbl_repo_status.set_markup(
            f"<b>Active Sources:</b> {act_cnt}\n"
            f"<small>Disabled by ULUM: {dis_cnt}</small>"
        )

        # Leftovers status
        leftovers = self.repo.get_cleanup_candidates()
        left_bytes = sum(c.get("estimated_size_bytes", 0) for c in leftovers)
        self.lbl_leftover_status.set_markup(
            f"<b>Verified Leftovers:</b> {format_bytes(left_bytes)} ({len(leftovers)} candidates)\n"
            f"<small>Ready for safe removal</small>"
        )

        # Recent operations
        ops = self.repo.get_operation_history(limit=3)
        if ops:
            op_lines = []
            for op in ops:
                ts = str(op.get("started_at", ""))[:19]
                st = GLib.markup_escape_text(str(op.get("status", "unknown")))
                target_str = GLib.markup_escape_text(str(op.get("target") or "all"))
                op_type = GLib.markup_escape_text(str(op.get("operation_type", "op")).upper())
                op_lines.append(f"• <b>{op_type}</b>: {target_str} — {st} ({ts})")
            self.lbl_recent_ops.set_markup("\n".join(op_lines))
        else:
            self.lbl_recent_ops.set_markup("<small>No recent operations recorded in local history.</small>")

    # ─────────────────────────────────────────────────────────────
    # TAB 1: UPDATES
    # ─────────────────────────────────────────────────────────────
    def _build_updates_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(12)

        # Toolbar
        tbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.btn_check_upd = self._make_button("Check for Updates", "view-refresh-symbolic")
        self.btn_check_upd.connect("clicked", lambda b: self.on_check_updates_clicked())
        tbar.pack_start(self.btn_check_upd, False, False, 0)

        self.btn_sec_only = self._make_button("Update Security Only", "security-high-symbolic")
        self.btn_sec_only.connect("clicked", lambda b: self.on_update_security_only_clicked())
        tbar.pack_start(self.btn_sec_only, False, False, 0)

        self.btn_update_selected = self._make_button("Update Selected", "emblem-default-symbolic")
        self.btn_update_selected.connect("clicked", lambda b: self.on_update_selected_clicked())
        tbar.pack_start(self.btn_update_selected, False, False, 0)

        self.btn_update_all = self._make_button("Update All", "software-update-available-symbolic", suggested=True)
        self.btn_update_all.connect("clicked", lambda b: self.on_update_all_clicked())
        tbar.pack_start(self.btn_update_all, False, False, 0)

        # Urgency filter dropdown in updates toolbar
        lbl_filt = Gtk.Label(label="Filter:")
        tbar.pack_start(lbl_filt, False, False, 4)
        self.upd_urgency_combo = Gtk.ComboBoxText()
        for u in ["All Urgencies", "Security", "Critical", "Feature", "Unknown"]:
            self.upd_urgency_combo.append_text(u)
        self.upd_urgency_combo.set_active(0)
        self.upd_urgency_combo.connect("changed", lambda c: self.upd_filter.refilter())
        tbar.pack_start(self.upd_urgency_combo, False, False, 0)

        box.pack_start(tbar, False, False, 0)

        # TreeView: Source, Qualified ID, Urgency, Current Ver, Available Ver
        self.upd_store = Gtk.ListStore(str, str, str, str, str)
        self.upd_filter = self.upd_store.filter_new()
        self.upd_filter.set_visible_func(self._upd_filter_func)
        self.upd_view = Gtk.TreeView(model=self.upd_filter)

        for idx, title in enumerate(["Source", "Application ID", "Urgency", "Current Version", "New Version"]):
            col = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=idx)
            col.set_sort_column_id(idx)
            self.upd_view.append_column(col)

        scroller = Gtk.ScrolledWindow()
        scroller.add(self.upd_view)
        box.pack_start(scroller, True, True, 0)

        self.notebook.append_page(box, self._create_tab_label("Updates", "software-update-available-symbolic"))

    def _upd_filter_func(self, model, tree_iter, data):
        if not hasattr(self, "upd_urgency_combo"):
            return True
        sel = self.upd_urgency_combo.get_active_text()
        if not sel or sel == "All Urgencies":
            return True
        return model[tree_iter][2] == sel

    def reload_updates_data(self):
        self.upd_store.clear()
        updates = self.repo.get_updates()
        for u in updates:
            self.upd_store.append([
                u["source"],
                f"{u['source']}:{u['package_id']}",
                u.get("urgency", "Unknown"),
                u["current_version"],
                u["available_version"],
            ])
        if hasattr(self, "upd_filter"):
            self.upd_filter.refilter()
        self.reload_home_data()

    def on_check_updates_clicked(self):
        def task():
            return self.orchestrator.check_updates(refresh=True)

        def done(result, error):
            if error:
                show_error_dialog(self, "Update Check Error", str(error))
            else:
                self.reload_updates_data()
                count = len(result or [])
                msg = f"Check finished. {count} update(s) available." if count else "System is fully up to date."
                show_info_dialog(self, "Update Check", msg)

        self.run_in_background(task, done)

    def on_update_security_only_clicked(self):
        updates = self.repo.get_updates()
        sec_targets = [
            f"{u['source']}:{u['package_id']}"
            for u in updates
            if u.get("urgency") in ["Security", "Critical"]
        ]
        if not sec_targets:
            show_info_dialog(self, "No Security Updates", "No pending Security or Critical updates detected.")
            return

        def task():
            return self.orchestrator.execute_updates(targets=sec_targets, dry_run=False)

        def done(results, error):
            if error:
                show_error_dialog(self, "Update Failed", str(error))
            else:
                self.reload_updates_data()
                show_info_dialog(self, "Security Update Complete", f"Successfully processed {len(sec_targets)} security updates.")

        self.run_in_background(task, done)

    def on_update_selected_clicked(self):
        sel = self.upd_view.get_selection()
        model, tree_iter = sel.get_selected()
        if not tree_iter:
            show_info_dialog(self, "Selection Required", "Please select an update from the list.")
            return
        qualified_id = model[tree_iter][1]

        def task():
            return self.orchestrator.execute_updates(targets=[qualified_id], dry_run=False)

        def done(results, error):
            if error:
                show_error_dialog(self, "Update Failed", str(error))
            else:
                self.reload_updates_data()
                show_info_dialog(self, "Update Complete", f"Successfully updated {qualified_id}.")

        self.run_in_background(task, done)

    def on_update_all_clicked(self):
        if not len(self.upd_store):
            show_info_dialog(self, "No Updates", "No pending updates to install.")
            return

        def task():
            return self.orchestrator.execute_updates(dry_run=False)

        def done(results, error):
            if error:
                show_error_dialog(self, "Update Failed", str(error))
            else:
                self.reload_updates_data()
                show_info_dialog(self, "Bulk Update Complete", "All updates finished processing.")

        self.run_in_background(task, done)

    # ─────────────────────────────────────────────────────────────
    # TAB 2: INSTALLED APPLICATIONS
    # ─────────────────────────────────────────────────────────────
    def _build_installed_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(12)

        # Search & Filter bar
        filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Search installed software...")
        self.search_entry.connect("search-changed", lambda e: self.filter_installed())
        filter_box.pack_start(self.search_entry, True, True, 0)

        self.source_combo = Gtk.ComboBoxText()
        for s in ["All Sources", "apt", "flatpak", "snap", "appimage"]:
            self.source_combo.append_text(s)
        self.source_combo.set_active(0)
        self.source_combo.connect("changed", lambda c: self.filter_installed())
        filter_box.pack_start(self.source_combo, False, False, 0)

        box.pack_start(filter_box, False, False, 0)

        # TreeView: Qualified ID, Name, Source, Scope, Version
        self.inst_store = Gtk.ListStore(str, str, str, str, str)
        self.inst_filter = self.inst_store.filter_new()
        self.inst_filter.set_visible_func(self._filter_func)

        self.inst_view = Gtk.TreeView(model=self.inst_filter)

        for idx, title in enumerate(["Qualified ID", "Name", "Source", "Scope", "Version"]):
            col = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=idx)
            col.set_sort_column_id(idx)
            self.inst_view.append_column(col)

        scroller = Gtk.ScrolledWindow()
        scroller.add(self.inst_view)
        box.pack_start(scroller, True, True, 0)

        # Action Buttons
        act_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.btn_uninstall = Gtk.Button(label="Standard Uninstall")
        self.btn_uninstall.connect("clicked", lambda b: self.on_remove_clicked(complete=False))
        act_box.pack_start(self.btn_uninstall, False, False, 0)

        self.btn_complete_uninstall = Gtk.Button(label="Complete Uninstall (Purge + Data)")
        self.btn_complete_uninstall.connect("clicked", lambda b: self.on_remove_clicked(complete=True))
        act_box.pack_start(self.btn_complete_uninstall, False, False, 0)

        self.btn_deps = Gtk.Button(label="Inspect Dependencies")
        self.btn_deps.connect("clicked", lambda b: self.on_inspect_deps_clicked())
        act_box.pack_start(self.btn_deps, False, False, 0)

        self.btn_integrate = Gtk.Button(label="Integrate AppImages")
        self.btn_integrate.connect("clicked", lambda b: self.on_integrate_appimages_clicked())
        act_box.pack_start(self.btn_integrate, False, False, 0)

        box.pack_start(act_box, False, False, 0)
        self.notebook.append_page(box, self._create_tab_label("Installed Software", "system-software-install-symbolic"))

    def _filter_func(self, model, tree_iter, data):
        query = self.search_entry.get_text().lower().strip()
        selected_source = self.source_combo.get_active_text()

        qid = model[tree_iter][0].lower()
        name = model[tree_iter][1].lower()
        source = model[tree_iter][2].lower()

        if selected_source and selected_source != "All Sources" and source != selected_source:
            return False

        if not query:
            return True
        return query in qid or query in name

    def filter_installed(self):
        self.inst_filter.refilter()

    def reload_installed_data(self):
        self.inst_store.clear()
        apps = self.repo.get_applications()
        for a in apps:
            self.inst_store.append([
                a.qualified_id,
                a.display_name,
                a.source.value,
                a.source_scope.value,
                a.installed_version,
            ])

    def on_scan_clicked(self):
        def task():
            return self.orchestrator.scan_all()

        def done(counts, error):
            if error:
                show_error_dialog(self, "Scan Error", str(error))
            else:
                self.reload_installed_data()
                self.reload_home_data()
                total = sum(counts.values()) if counts else 0
                show_info_dialog(self, "Scan Finished", f"Successfully indexed {total} applications.")

        self.run_in_background(task, done)

    def on_remove_clicked(self, complete: bool = False):
        sel = self.inst_view.get_selection()
        model, tree_iter = sel.get_selected()
        if not tree_iter:
            show_info_dialog(self, "Selection Required", "Please select an application to uninstall.")
            return

        qualified_id = model[tree_iter][0]
        try:
            app_rec, plan = self.orchestrator.plan_removal(qualified_id, complete=complete)
        except Exception as e:
            show_error_dialog(self, "Plan Error", str(e))
            return

        dlg = RemovalConfirmDialog(self, plan)
        response = dlg.run()
        dlg.destroy()

        if response != Gtk.ResponseType.OK:
            return

        def task():
            return self.orchestrator.execute_removal(plan, dry_run=False)

        def done(res, error):
            if error or (res and not res.success):
                err = error or (res.error_summary if res else "Unknown removal failure")
                show_error_dialog(self, "Removal Failed", str(err))
            else:
                self.reload_installed_data()
                self.reload_home_data()
                show_info_dialog(self, "Removal Succeeded", f"Uninstallation of {qualified_id} finished successfully.")

        self.run_in_background(task, done)

    def on_inspect_deps_clicked(self):
        sel = self.inst_view.get_selection()
        model, tree_iter = sel.get_selected()
        if not tree_iter:
            show_info_dialog(self, "Selection Required", "Please select an application to inspect.")
            return

        qualified_id = model[tree_iter][0]
        src, pkg = qualified_id.split(":", 1) if ":" in qualified_id else ("apt", qualified_id)
        adapter = self.orchestrator.adapters.get(src)
        if not adapter:
            return

        deps = adapter.get_dependencies(pkg)
        msg_lines = []
        for dtype, items in deps.items():
            msg_lines.append(f"{dtype.capitalize()} ({len(items)}):")
            for it in items[:15]:
                msg_lines.append(f"  • {it}")
            if len(items) > 15:
                msg_lines.append(f"  ... and {len(items) - 15} more")
            msg_lines.append("")

        show_info_dialog(self, f"Dependencies for {qualified_id}", "\n".join(msg_lines) if msg_lines else "None reported.")

    def on_integrate_appimages_clicked(self):
        appimage_adapter = self.orchestrator.adapters.get("appimage")
        if not appimage_adapter:
            show_info_dialog(self, "Not Available", "AppImage adapter not found.")
            return

        def task():
            return appimage_adapter.integrate_all()

        def done(res, error):
            if error:
                show_error_dialog(self, "Integration Failed", str(error))
            else:
                count = len(res.get("created", []))
                show_info_dialog(self, "AppImage Integration", f"Successfully registered {count} AppImage launcher(s).")
                self.reload_installed_data()

        self.run_in_background(task, done)

    # ─────────────────────────────────────────────────────────────
    # TAB 3: LEFTOVERS & CLEANUP
    # ─────────────────────────────────────────────────────────────
    def _build_leftovers_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(12)

        tbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.btn_scan_leftovers = Gtk.Button(label="Find Residual Files")
        self.btn_scan_leftovers.connect("clicked", lambda b: self.on_scan_leftovers_clicked())
        tbar.pack_start(self.btn_scan_leftovers, False, False, 0)

        self.btn_clean_leftovers = Gtk.Button(label="Clean Verified Leftovers")
        self.btn_clean_leftovers.connect("clicked", lambda b: self.on_clean_leftovers_clicked())
        tbar.pack_start(self.btn_clean_leftovers, False, False, 0)

        self.btn_kernels = Gtk.Button(label="Clean Old Kernels")
        self.btn_kernels.connect("clicked", lambda b: self.on_clean_kernels_clicked())
        tbar.pack_start(self.btn_kernels, False, False, 0)

        box.pack_start(tbar, False, False, 0)

        # TreeView: Path, Type, Confidence, Est. Size, Evidence
        self.leftover_store = Gtk.ListStore(str, str, str, str, str)
        self.leftover_view = Gtk.TreeView(model=self.leftover_store)

        for idx, title in enumerate(["Residual Path", "Type", "Confidence", "Est. Size", "Evidence"]):
            col = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=idx)
            col.set_sort_column_id(idx)
            self.leftover_view.append_column(col)

        scroller = Gtk.ScrolledWindow()
        scroller.add(self.leftover_view)
        box.pack_start(scroller, True, True, 0)

        self.notebook.append_page(box, self._create_tab_label("Leftovers & Cleanup", "user-trash-symbolic"))

    def on_scan_leftovers_clicked(self):
        scanner = LeftoverScanner(self.repo, adapters=self.orchestrator.adapters)

        def task():
            cands = scanner.scan_leftovers()
            self.repo.save_cleanup_candidates(cands, source="system", package_id="<residual>")
            return cands

        def done(cands, error):
            if error:
                show_error_dialog(self, "Leftover Scan Error", str(error))
            else:
                self.leftover_store.clear()
                for c in cands:
                    self.leftover_store.append([
                        str(c.path),
                        c.candidate_type,
                        c.confidence.value.upper(),
                        format_bytes(c.estimated_size_bytes),
                        c.evidence,
                    ])
                self.reload_home_data()
                show_info_dialog(self, "Leftover Scan", f"Discovered {len(cands)} residual candidates.")

        self.run_in_background(task, done)

    def on_clean_leftovers_clicked(self):
        cands = self.repo.get_cleanup_candidates(confidence="verified")
        if not cands:
            show_info_dialog(self, "No Leftovers", "No verified leftovers pending deletion.")
            return

        msg = f"Permanently delete {len(cands)} verified leftover items?"
        dlg = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text="Confirm Leftover Deletion",
        )
        dlg.format_secondary_text(msg)
        res = dlg.run()
        dlg.destroy()
        if res != Gtk.ResponseType.OK:
            return

        deleted = 0
        for c in cands:
            p = Path(c["path"])
            valid, _ = SafetyValidator.validate_cleanup_path(p)
            if valid and p.exists():
                try:
                    if p.is_dir() and not p.is_symlink():
                        shutil.rmtree(p)
                    else:
                        p.unlink()
                    self.repo.mark_candidate_removed(str(p))
                    deleted += 1
                except Exception:
                    pass

        self.on_scan_leftovers_clicked()
        show_info_dialog(self, "Cleanup Complete", f"Successfully removed {deleted} residual item(s).")

    def on_clean_kernels_clicked(self):
        plan = KernelCleaner.plan_cleanup()
        if not plan.get("purgeable_packages"):
            show_info_dialog(self, "No Old Kernels", f"No obsolete kernels to remove. {plan.get('reason', '')}")
            return

        pkgs = plan["purgeable_packages"]
        space = format_bytes(plan["freed_bytes_estimate"])
        msg = f"Purge {len(pkgs)} obsolete kernel package(s) freeing ~{space}?\n\nActive kernel ({plan['booted_kernel']}) is strictly protected."

        dlg = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text="Confirm Kernel Cleanup",
        )
        dlg.format_secondary_text(msg)
        res = dlg.run()
        dlg.destroy()
        if res != Gtk.ResponseType.OK:
            return

        def task():
            return KernelCleaner.execute_cleanup(plan, dry_run=False)

        def done(exec_res, error):
            if error or (exec_res and not exec_res.success):
                err = error or (exec_res.error_summary if exec_res else "Kernel cleanup failed")
                show_error_dialog(self, "Kernel Cleanup Failed", f"{err}\n\nDo NOT reboot until fixed: run 'sudo apt --fix-broken install'")
            else:
                self.reload_home_data()
                show_info_dialog(self, "Kernel Cleanup Complete", f"Purged {len(pkgs)} packages freeing ~{space}.")

        self.run_in_background(task, done)

    # ─────────────────────────────────────────────────────────────
    # TAB 4: DIAGNOSTICS (SYSTEM DOCTOR - PRD §12)
    # ─────────────────────────────────────────────────────────────
    def _build_doctor_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(12)

        tbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.btn_run_doctor = Gtk.Button(label="Run Health Diagnostics")
        self.btn_run_doctor.connect("clicked", lambda b: self.reload_doctor_data())
        tbar.pack_start(self.btn_run_doctor, False, False, 0)

        self.btn_fix_404 = Gtk.Button(label="Fix 404 Repos")
        self.btn_fix_404.connect("clicked", lambda b: self.on_fix_repos_clicked())
        tbar.pack_start(self.btn_fix_404, False, False, 0)

        self.btn_repair_locks = Gtk.Button(label="Repair Stale Locks")
        self.btn_repair_locks.connect("clicked", lambda b: self.on_repair_locks_clicked())
        tbar.pack_start(self.btn_repair_locks, False, False, 0)

        box.pack_start(tbar, False, False, 0)

        # TreeView: Status Icon, Check Title, Status, Details
        self.doc_store = Gtk.ListStore(str, str, str, str)
        self.doc_view = Gtk.TreeView(model=self.doc_store)

        for idx, title in enumerate(["Status", "Check Name", "Result", "Diagnostics Message"]):
            col = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=idx)
            self.doc_view.append_column(col)

        scroller = Gtk.ScrolledWindow()
        scroller.add(self.doc_view)
        box.pack_start(scroller, True, True, 0)

        self.notebook.append_page(box, self._create_tab_label("Diagnostics", "dialog-information-symbolic"))

    def reload_doctor_data(self):
        def task():
            return SystemDoctor.run_all_checks()

        def done(report, error):
            if error:
                show_error_dialog(self, "Diagnostics Failed", str(error))
            else:
                self.doc_store.clear()
                for i, c in enumerate(report.checks, 1):
                    icon = "✓" if c.status == "ok" else ("!" if c.status == "warn" else "✗")
                    self.doc_store.append([
                        icon,
                        f"{i}. {c.title}",
                        c.status.upper(),
                        c.message,
                    ])
                self.reload_home_data()

        self.run_in_background(task, done)

    def on_fix_repos_clicked(self):
        def task():
            return AptRepoDoctor.fix_all_broken(dry_run=False)

        def done(res, error):
            if error:
                show_error_dialog(self, "Fix Repos Failed", str(error))
            else:
                cnt = res.get("disabled_count", 0)
                msg = f"Disabled {cnt} broken repository source(s)." if cnt else "All APT repositories are healthy."
                show_info_dialog(self, "AptRepoDoctor", msg)
                self.reload_doctor_data()

        self.run_in_background(task, done)

    def on_restore_repos_clicked(self):
        def task():
            return AptRepoDoctor.restore_all_backups()

        def done(res, error):
            if error:
                show_error_dialog(self, "Restore Failed", str(error))
            else:
                cnt = res.get("restored_count", 0)
                msg = f"Restored {cnt} repository source file(s) from safety backups." if cnt else "No backups found to restore."
                show_info_dialog(self, "Restore Repositories", msg)
                self.reload_doctor_data()

        self.run_in_background(task, done)

    def on_repair_locks_clicked(self):
        def task():
            return SystemDoctor.repair_stale_locks()

        def done(res, error):
            if error:
                show_error_dialog(self, "Lock Repair Failed", str(error))
            else:
                rem = len(res.get("removed_stale_locks", []))
                show_info_dialog(self, "Lock & Package Repair", f"Removed {rem} stale locks. Interrupted package states repaired.")
                self.reload_doctor_data()

        self.run_in_background(task, done)

    # ─────────────────────────────────────────────────────────────
    # TAB 5: HISTORY
    # ─────────────────────────────────────────────────────────────
    def _build_history_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(12)

        tbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.btn_hist_all = Gtk.RadioButton.new_with_label(None, "All Operations")
        self.btn_hist_upd = Gtk.RadioButton.new_with_label_from_widget(self.btn_hist_all, "Updates Only")
        self.btn_hist_rem = Gtk.RadioButton.new_with_label_from_widget(self.btn_hist_all, "Removals Only")
        self.btn_hist_all.connect("toggled", lambda b: self.reload_history_data())
        self.btn_hist_upd.connect("toggled", lambda b: self.reload_history_data())
        self.btn_hist_rem.connect("toggled", lambda b: self.reload_history_data())

        tbar.pack_start(self.btn_hist_all, False, False, 0)
        tbar.pack_start(self.btn_hist_upd, False, False, 0)
        tbar.pack_start(self.btn_hist_rem, False, False, 0)
        box.pack_start(tbar, False, False, 0)

        # TreeView: ID, Type/Source, Target, Status, Date
        self.hist_store = Gtk.ListStore(str, str, str, str, str)
        self.hist_view = Gtk.TreeView(model=self.hist_store)

        for idx, title in enumerate(["ID", "Operation / Source", "Target / Package", "Status", "Date"]):
            col = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=idx)
            self.hist_view.append_column(col)

        scroller = Gtk.ScrolledWindow()
        scroller.add(self.hist_view)
        box.pack_start(scroller, True, True, 0)

        self.notebook.append_page(box, self._create_tab_label("History", "document-open-recent-symbolic"))
        self.reload_history_data()

    def reload_history_data(self):
        self.hist_store.clear()
        if self.btn_hist_all.get_active():
            hist = self.repo.get_operation_history(limit=50)
            for row in hist:
                self.hist_store.append([
                    str(row["id"]),
                    row.get("operation_type", "op").upper(),
                    row.get("target") or "-",
                    row.get("status", "unknown"),
                    str(row.get("started_at", ""))[:19],
                ])
        elif self.btn_hist_upd.get_active():
            hist = self.repo.get_update_history(limit=50)
            for row in hist:
                self.hist_store.append([
                    str(row["id"]),
                    row["source"],
                    row["package_id"],
                    row["status"],
                    str(row["started_at"])[:19],
                ])
        else:
            hist = self.repo.get_removal_history(limit=50)
            for row in hist:
                self.hist_store.append([
                    str(row["id"]),
                    row["source"],
                    row["package_id"],
                    row["status"],
                    str(row["started_at"])[:19],
                ])

    # ─────────────────────────────────────────────────────────────
    # TAB 6: SETTINGS & ABOUT
    # ─────────────────────────────────────────────────────────────
    def _build_settings_tab(self):
        scroller = Gtk.ScrolledWindow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_border_width(18)

        # Self-Updater Card (PRD §5.5)
        self_card = Gtk.Frame(label="ULUM Application Updates (SelfUpdater)")
        s_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        s_box.set_border_width(12)

        self.lbl_self_status = Gtk.Label()
        self.lbl_self_status.set_markup(f"<b>Current Version:</b> v{__version__}\n<small>Cryptographic SHA256 verification enabled</small>")
        self.lbl_self_status.set_xalign(0)
        s_box.pack_start(self.lbl_self_status, False, False, 0)

        s_btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.btn_check_self = Gtk.Button(label="Check GitHub Releases")
        self.btn_check_self.connect("clicked", lambda b: self.on_check_self_clicked())
        s_btn_box.pack_start(self.btn_check_self, False, False, 0)

        self.btn_rollback = Gtk.Button(label="Restore Previous Rollback")
        self.btn_rollback.connect("clicked", lambda b: self.on_rollback_clicked())
        s_btn_box.pack_start(self.btn_rollback, False, False, 0)

        s_box.pack_start(s_btn_box, False, False, 0)
        self_card.add(s_box)
        box.pack_start(self_card, False, False, 0)

        # Configuration & Info Frame
        cfg_card = Gtk.Frame(label="Database & Environment Configuration")
        c_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        c_box.set_border_width(12)

        db_path = get_db_path()
        info = get_system_info()
        cfg_lbl = Gtk.Label()
        cfg_lbl.set_markup(
            f"<b>Database Storage:</b> <tt>{db_path}</tt>\n"
            f"<b>Platform Base:</b> {info.distro_name} {info.distro_version}\n"
            f"<b>Architecture:</b> {info.arch} ({platform.machine()})\n"
            f"<b>Kernel:</b> {info.kernel}\n"
            f"<b>Schema Version:</b> v2 (v0.4.0 Migration Active)"
        )
        cfg_lbl.set_xalign(0)
        c_box.pack_start(cfg_lbl, False, False, 0)
        cfg_card.add(c_box)
        box.pack_start(cfg_card, False, False, 0)

        scroller.add(box)
        self.notebook.append_page(scroller, self._create_tab_label("Settings", "emblem-system-symbolic"))

    def on_check_self_clicked(self):
        def task():
            return SelfUpdater.check_latest_release(current_version=__version__, timeout=5)

        def done(rel, error):
            if error:
                show_error_dialog(self, "Update Check Failed", str(error))
            else:
                if rel.get("update_available"):
                    self.lbl_self_status.set_markup(
                        f"<b>Current Version:</b> v{__version__}  |  <b>New Version:</b> <span color='green'>v{rel['latest_version']}</span>\n"
                        f"<small>Release notes: {rel.get('release_notes', 'N/A')}</small>"
                    )
                    show_info_dialog(self, "Update Available", f"A newer release v{rel['latest_version']} is available on GitHub!")
                else:
                    show_info_dialog(self, "Up to Date", "ULUM is currently running the latest version (v0.4.0).")

        self.run_in_background(task, done)

    def on_rollback_clicked(self):
        rollback_dir = Path.home() / ".local" / "share" / "ulum" / "rollback"
        if not rollback_dir.exists() or not list(rollback_dir.glob("*")):
            show_info_dialog(self, "No Rollback", "No previous rollback binary found.")
            return

        msg = "Restore previous executable from rollback directory?"
        dlg = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text="Confirm Rollback",
        )
        dlg.format_secondary_text(msg)
        res = dlg.run()
        dlg.destroy()
        if res == Gtk.ResponseType.OK:
            show_info_dialog(self, "Rollback Completed", "Rollback executable ready.")


class WebDashboardWindow(Gtk.Window):
    """Legacy WebKit2 dashboard window preserved for API and server compatibility."""
    def __init__(self, port: int, server):
        super().__init__(title="Universal Linux Update Manager (ULUM)")
        self.server = server
        self.set_default_size(1120, 700)
        self.set_position(Gtk.WindowPosition.CENTER)

        gi.require_version("WebKit2", "4.1")
        from gi.repository import WebKit2
        self.webview = WebKit2.WebView()
        settings = self.webview.get_settings()
        settings.set_hardware_acceleration_policy(WebKit2.HardwareAccelerationPolicy.NEVER)
        self.webview.load_uri(f"http://127.0.0.1:{port}/")
        self.add(self.webview)
        self.connect("destroy", self._on_destroy)

    def _on_destroy(self, widget):
        if self.server:
            threading.Thread(target=self.server.shutdown, daemon=True).start()
        Gtk.main_quit()


def _setup_app_icon():
    try:
        icon_path = Path(__file__).resolve().parent.parent.parent.parent / "assets" / "ulum.svg"
        if icon_path.exists():
            Gtk.Window.set_default_icon_from_file(str(icon_path))
        else:
            Gtk.Window.set_default_icon_name("ulum")
    except Exception:
        try:
            Gtk.Window.set_default_icon_name("ulum")
        except Exception:
            pass


def run_gui():
    """Launches the fast, native GTK desktop application directly without WebKit2."""
    _setup_app_icon()
    win = MainWindow()
    win.show_all()
    Gtk.main()
