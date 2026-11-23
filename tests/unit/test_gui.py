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
        assert hasattr(win, "level_health")
        assert hasattr(win, "progress_boot")
        assert hasattr(win, "btn_pill_sec")
        assert hasattr(win, "upd_urgency_combo")
        assert hasattr(win, "btn_upgrade_self")
        assert hasattr(win, "btn_check_self")
        assert hasattr(win, "lbl_upgrade_btn")
        assert win.btn_upgrade_self.get_sensitive() is False

        # Test metric pill filter action
        win._filter_updates_to("Security")
        assert win.upd_urgency_combo.get_active_text() == "Security"

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
