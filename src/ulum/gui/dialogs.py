import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from ulum.cli.display import format_bytes
from ulum.core.models import RemovalPlan

class RemovalConfirmDialog(Gtk.Dialog):
    def __init__(self, parent: Gtk.Window, plan: RemovalPlan):
        super().__init__(
            title="Confirm Application Removal",
            transient_for=parent,
            flags=0,
        )
        self.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            "Proceed with Removal", Gtk.ResponseType.OK,
        )
        self.set_default_size(500, 350)
        self.set_border_width(12)

        box = self.get_content_area()
        box.set_spacing(10)

        # Header
        mode_str = "Complete (Purge Config & Data)" if plan.complete else "Standard Uninstall"
        header = Gtk.Label()
        header.set_markup(
            f"<big><b>Remove {plan.application.qualified_id}?</b></big>\n"
            f"<b>Mode:</b> {mode_str}\n"
            f"<b>Native Command:</b> <tt>{' '.join(plan.native_command)}</tt>"
        )
        header.set_xalign(0)
        box.pack_start(header, False, False, 0)

        # Warnings if any
        if plan.safety_warnings:
            warn_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            warn_lbl = Gtk.Label()
            warn_lbl.set_markup("<span color='red'><b>⚠ Safety Warnings:</b></span>")
            warn_lbl.set_xalign(0)
            warn_box.pack_start(warn_lbl, False, False, 0)
            for w in plan.safety_warnings:
                item_lbl = Gtk.Label(label=f"• {w}")
                item_lbl.set_line_wrap(True)
                item_lbl.set_xalign(0)
                warn_box.pack_start(item_lbl, False, False, 0)
            box.pack_start(warn_box, False, False, 0)

        # Cleanup items
        if plan.cleanup_items:
            paths_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            paths_lbl = Gtk.Label()
            paths_lbl.set_markup(f"<b>Residual paths to be deleted ({format_bytes(plan.estimated_freed_bytes)}):</b>")
            paths_lbl.set_xalign(0)
            paths_box.pack_start(paths_lbl, False, False, 0)

            scroller = Gtk.ScrolledWindow()
            scroller.set_min_content_height(100)
            listbox = Gtk.ListBox()
            for item in plan.cleanup_items:
                row = Gtk.Label(label=f"• {item.path} ({format_bytes(item.estimated_size_bytes)})")
                row.set_xalign(0)
                listbox.add(row)
            scroller.add(listbox)
            paths_box.pack_start(scroller, True, True, 0)
            box.pack_start(paths_box, True, True, 0)

        self.show_all()

def show_info_dialog(parent: Gtk.Window, title: str, message: str) -> None:
    dlg = Gtk.MessageDialog(
        transient_for=parent,
        flags=0,
        message_type=Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.OK,
        text=title,
    )
    dlg.format_secondary_text(message)
    dlg.run()
    dlg.destroy()

def show_error_dialog(parent: Gtk.Window, title: str, error: str) -> None:
    dlg = Gtk.MessageDialog(
        transient_for=parent,
        flags=0,
        message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.OK,
        text=title,
    )
    dlg.format_secondary_text(error)
    dlg.run()
    dlg.destroy()
