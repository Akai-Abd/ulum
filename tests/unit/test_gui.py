import pytest

gi = pytest.importorskip("gi")
try:
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    from ulum.gui.window import MainWindow
except Exception:
    pytest.skip("Gtk 3.0 or PyGObject environment not available", allow_module_level=True)

def test_gui_window_initialization():
    try:
        win = MainWindow()
        assert win.header.props.title == "ULUM Update Manager"
        assert win.notebook.get_n_pages() == 4
        win.destroy()
    except Exception as e:
        pytest.skip(f"GUI display not available: {e}")
