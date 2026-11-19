import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from ulum.gui.window import MainWindow

def test_gui_window_initialization():
    win = MainWindow()
    assert win.header.props.title == "ULUM Update Manager"
    assert win.notebook.get_n_pages() == 4
    win.destroy()
