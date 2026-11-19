import shutil
import threading
from typing import Callable, Optional
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk
from ulum.cli.display import format_bytes
from ulum.core.config import load_config
from ulum.core.orchestrator import Orchestrator
from ulum.core.system import detect_package_managers, get_system_info
from ulum.db.database import init_db
from ulum.db.repository import Repository
from ulum.gui.dialogs import RemovalConfirmDialog, show_error_dialog, show_info_dialog
from ulum.removal.leftovers import LeftoverScanner
from ulum.removal.safety import SafetyValidator

class MainWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Universal Linux Update Manager (ULUM)")
        self.set_default_size(900, 600)
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
        self.header.props.subtitle = f"{info.distro_name} {info.distro_version} ({info.arch})"
        self.set_titlebar(self.header)

        # Spinner in header
        self.spinner = Gtk.Spinner()
        self.header.pack_end(self.spinner)

        # Quick Scan Button in header
        self.btn_scan = Gtk.Button(label="Scan System")
        self.btn_scan.connect("clicked", lambda b: self.on_scan_clicked())
        self.header.pack_start(self.btn_scan)

        # Main Layout: Notebook
        self.notebook = Gtk.Notebook()
        self.add(self.notebook)

        self._build_updates_tab()
        self._build_installed_tab()
        self._build_leftovers_tab()
        self._build_history_tab()

        self.connect("destroy", Gtk.main_quit)
        
        # Initial population of installed apps
        self.reload_installed_data()
        self.reload_updates_data()

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
    # TAB 1: UPDATES
    # ─────────────────────────────────────────────────────────────
    def _build_updates_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(12)

        # Toolbar
        tbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.btn_check_upd = Gtk.Button(label="Check for Updates")
        self.btn_check_upd.connect("clicked", lambda b: self.on_check_updates_clicked())
        tbar.pack_start(self.btn_check_upd, False, False, 0)

        self.btn_update_selected = Gtk.Button(label="Update Selected")
        self.btn_update_selected.connect("clicked", lambda b: self.on_update_selected_clicked())
        tbar.pack_start(self.btn_update_selected, False, False, 0)

        self.btn_update_all = Gtk.Button(label="Update All")
        self.btn_update_all.connect("clicked", lambda b: self.on_update_all_clicked())
        tbar.pack_start(self.btn_update_all, False, False, 0)

        box.pack_start(tbar, False, False, 0)

        # TreeView: Source, Qualified ID, Current Ver, Available Ver
        self.upd_store = Gtk.ListStore(str, str, str, str)
        self.upd_view = Gtk.TreeView(model=self.upd_store)

        for idx, title in enumerate(["Source", "Application ID", "Current Version", "New Version"]):
            col = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=idx)
            col.set_sort_column_id(idx)
            self.upd_view.append_column(col)

        scroller = Gtk.ScrolledWindow()
        scroller.add(self.upd_view)
        box.pack_start(scroller, True, True, 0)

        self.notebook.append_page(box, Gtk.Label(label="Updates"))

    def reload_updates_data(self):
        self.upd_store.clear()
        updates = self.repo.get_updates()
        for u in updates:
            self.upd_store.append([
                u["source"],
                f"{u['source']}:{u['package_id']}",
                u["current_version"],
                u["available_version"],
            ])

    def on_check_updates_clicked(self):
        def task():
            return self.orchestrator.check_updates(refresh=False)

        def done(result, error):
            if error:
                show_error_dialog(self, "Update Check Error", str(error))
            else:
                self.reload_updates_data()
                count = len(result or [])
                msg = f"Check finished. {count} update(s) available." if count else "System is fully up to date."
                show_info_dialog(self, "Update Check", msg)

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
        for s in ["All Sources", "apt", "flatpak", "snap"]:
            self.source_combo.append_text(s)
        self.source_combo.set_active(0)
        self.source_combo.connect("changed", lambda c: self.filter_installed())
        filter_box.pack_start(self.source_combo, False, False, 0)

        box.pack_start(filter_box, False, False, 0)

        # TreeView: Qualified ID, Name, Source, Scope, Version
        # Store cols: [Qualified ID, Name, Source, Scope, Version]
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

        box.pack_start(act_box, False, False, 0)
        self.notebook.append_page(box, Gtk.Label(label="Installed Software"))

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

        # Show confirmation dialog
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

        self.notebook.append_page(box, Gtk.Label(label="Leftovers & Cleanup"))

    def on_scan_leftovers_clicked(self):
        scanner = LeftoverScanner(self.repo)

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
                show_info_dialog(self, "Leftover Scan", f"Discovered {len(cands)} residual candidates.")

        self.run_in_background(task, done)

    def on_clean_leftovers_clicked(self):
        cands = self.repo.get_cleanup_candidates(confidence="verified")
        if not cands:
            show_info_dialog(self, "No Leftovers", "No verified leftovers pending deletion.")
            return

        # Confirm
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
            p = c["path"]
            valid, _ = SafetyValidator.validate_cleanup_path(p)
            if valid:
                try:
                    shutil.rmtree(p)
                    self.repo.mark_candidate_removed(p)
                    deleted += 1
                except Exception:
                    pass

        self.on_scan_leftovers_clicked()
        show_info_dialog(self, "Cleanup Complete", f"Successfully removed {deleted} residual item(s).")

    # ─────────────────────────────────────────────────────────────
    # TAB 4: HISTORY & LOGS
    # ─────────────────────────────────────────────────────────────
    def _build_history_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(12)

        tbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.btn_hist_upd = Gtk.RadioButton.new_with_label(None, "Update History")
        self.btn_hist_rem = Gtk.RadioButton.new_with_label_from_widget(self.btn_hist_upd, "Removal History")
        self.btn_hist_upd.connect("toggled", lambda b: self.reload_history_data())
        tbar.pack_start(self.btn_hist_upd, False, False, 0)
        tbar.pack_start(self.btn_hist_rem, False, False, 0)

        box.pack_start(tbar, False, False, 0)

        # TreeView: ID, Source, Package ID, Status, Date
        self.hist_store = Gtk.ListStore(str, str, str, str, str)
        self.hist_view = Gtk.TreeView(model=self.hist_store)

        for idx, title in enumerate(["ID", "Source", "Package ID", "Status", "Date"]):
            col = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=idx)
            self.hist_view.append_column(col)

        scroller = Gtk.ScrolledWindow()
        scroller.add(self.hist_view)
        box.pack_start(scroller, True, True, 0)

        self.notebook.append_page(box, Gtk.Label(label="History"))
        self.reload_history_data()

    def reload_history_data(self):
        self.hist_store.clear()
        if self.btn_hist_upd.get_active():
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

class WebDashboardWindow(Gtk.Window):
    def __init__(self, port: int, server):
        super().__init__(title="Universal Linux Update Manager (ULUM)")
        self.server = server
        self.set_default_size(1120, 700)
        self.set_position(Gtk.WindowPosition.CENTER)

        gi.require_version("WebKit2", "4.1")
        from gi.repository import WebKit2
        self.webview = WebKit2.WebView()
        self.webview.load_uri(f"http://127.0.0.1:{port}/")
        self.add(self.webview)

        self.connect("destroy", self._on_destroy)

    def _on_destroy(self, widget):
        if self.server:
            threading.Thread(target=self.server.shutdown, daemon=True).start()
        Gtk.main_quit()

def run_gui():
    try:
        gi.require_version("WebKit2", "4.1")
        from gi.repository import WebKit2
        has_webkit = True
    except Exception:
        has_webkit = False

    if has_webkit:
        conn = init_db()
        repo = Repository(conn)
        config = load_config()
        orchestrator = Orchestrator(repo, config)

        from ulum.gui.server import create_server
        server = create_server(repo, config, orchestrator, host="127.0.0.1", port=0)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()

        win = WebDashboardWindow(port=port, server=server)
        win.show_all()
        Gtk.main()
    else:
        win = MainWindow()
        win.show_all()
        Gtk.main()
