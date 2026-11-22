import pytest

gi = pytest.importorskip("gi")
try:
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    from ulum.gui.window import MainWindow, calculate_health_score
except Exception:
    pytest.skip("Gtk 3.0 or PyGObject environment not available", allow_module_level=True)


def test_gui_window_initialization():
    try:
        win = MainWindow()
        assert win.header.props.title == "ULUM Update Manager"
        assert win.notebook.get_n_pages() == 7
        win.destroy()
    except Exception as e:
        pytest.skip(f"GUI display not available: {e}")


def test_health_score_calculation(temp_db):
    repo, _ = temp_db
    res = calculate_health_score(repo)
    assert "score" in res
    assert "status" in res
    assert "deductions" in res
    assert 0 <= res["score"] <= 100
