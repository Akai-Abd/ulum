import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from ulum.adapters.appimage import AppImageAdapter
from ulum.adapters.apt import AptAdapter
from ulum.core.config import UlumConfig
from ulum.core.models import ExecutionResult
from ulum.core.orchestrator import Orchestrator
from ulum.doctor.repos import AptRepoDoctor
from ulum.removal.kernels import KernelCleaner
from ulum.utils.self_update import SelfUpdater, parse_version_tuple


def test_kernel_cleaner_extract_release():
    assert KernelCleaner._extract_release("linux-image-6.8.0-149-generic") == "6.8.0-149-generic"
    assert KernelCleaner._extract_release("linux-headers-6.8.0-149") == "6.8.0-149"
    assert KernelCleaner._extract_release("linux-modules-extra-6.8.0-83-generic") == "6.8.0-83-generic"
    assert KernelCleaner._extract_release("linux-image-generic") is None


def test_kernel_cleaner_plan_preserves_running_and_fallback():
    mock_packages = [
        {"package": "linux-image-6.8.0-151-generic", "version": "6.8.0-151", "status": "install ok installed", "size_bytes": 100000000},
        {"package": "linux-modules-6.8.0-151-generic", "version": "6.8.0-151", "status": "install ok installed", "size_bytes": 50000000},
        {"package": "linux-image-6.8.0-149-generic", "version": "6.8.0-149", "status": "install ok installed", "size_bytes": 100000000},
        {"package": "linux-modules-6.8.0-149-generic", "version": "6.8.0-149", "status": "install ok installed", "size_bytes": 50000000},
        {"package": "linux-image-6.8.0-140-generic", "version": "6.8.0-140", "status": "install ok installed", "size_bytes": 100000000},
        {"package": "linux-modules-6.8.0-83-generic", "version": "6.8.0-83", "status": "deinstall ok config-files", "size_bytes": 10000},
    ]

    with patch.object(KernelCleaner, "get_running_kernel", return_value="6.8.0-151-generic"), \
         patch.object(KernelCleaner, "list_kernel_packages", return_value=mock_packages):
        plan = KernelCleaner.plan_cleanup()

        assert plan["running_kernel"] == "6.8.0-151-generic"
        # Running kernel release (151) and latest fallback (149) should be protected
        assert "6.8.0-151-generic" in plan["kept_kernels"]
        # Old kernel (140) should be removable
        assert "6.8.0-140-generic" in plan["removable_kernels"]
        assert "linux-image-6.8.0-140-generic" in plan["packages_to_remove"]
        # Residual config package should be purged
        assert "linux-modules-6.8.0-83-generic" in plan["packages_to_remove"]
        # Running kernel must NEVER be in packages_to_remove
        assert "linux-image-6.8.0-151-generic" not in plan["packages_to_remove"]
        assert plan["is_safe"] is True


def test_kernel_cleaner_execute_safety_abort():
    # If a package matching running kernel is passed, execute_cleanup must abort immediately
    plan = {
        "running_kernel": "6.8.0-151-generic",
        "packages_to_remove": ["linux-image-6.8.0-151-generic"],
    }
    res = KernelCleaner.execute_cleanup(plan, dry_run=False)
    assert not res.success
    assert "Aborted" in (res.error_summary or "")


def test_apt_repo_doctor_disable(tmp_path: Path):
    sources_file = tmp_path / "test.list"
    sources_file.write_text("deb http://ppa.launchpad.net/dead/ppa/ubuntu noble main\n", encoding="utf-8")

    entry = {
        "file": str(sources_file),
        "line_number": 1,
        "reason": "404 Not Found",
        "file_type": "list",
    }
    ok, msg = AptRepoDoctor.disable_broken_entry(entry, dry_run=False)
    assert ok
    content = sources_file.read_text(encoding="utf-8")
    assert content.startswith("# DISABLED BY ULUM (404 Not Found): deb http://ppa.launchpad.net/dead/ppa/ubuntu noble main")


def test_appimage_integrate(tmp_path: Path, monkeypatch):
    app_bin = tmp_path / "testapp-1.0.0.AppImage"
    app_bin.write_text("#!/bin/sh\necho hello\n")
    desktop_dir = tmp_path / "applications"
    monkeypatch.setattr(AppImageAdapter, "get_desktop_dir", classmethod(lambda cls: desktop_dir))

    ok, msg, dfile = AppImageAdapter.integrate_appimage(app_bin)
    assert ok
    assert dfile is not None
    assert dfile.exists()
    content = dfile.read_text(encoding="utf-8")
    assert "Type=Application" in content
    assert "Name=Testapp" in content
    assert f'Exec="{app_bin.resolve()}" %U' in content


def test_apt_get_download_size():
    apt = AptAdapter()
    sample_stdout = """
Reading package lists... Done
Building dependency tree... Done
The following packages will be upgraded:
  curl
1 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.
Need to get 145 MB of archives.
After this operation, 10 kB of additional disk space will be used.
"""
    with patch("ulum.adapters.apt.run_cmd") as mock_cmd:
        mock_cmd.return_value = ExecutionResult(success=True, exit_code=0, stdout=sample_stdout)
        with patch.object(apt, "is_available", return_value=True):
            size = apt.get_download_size()
            assert size == 145 * 1024 * 1024


def test_orchestrator_download_size_summary():
    repo = MagicMock()
    cfg = UlumConfig(enabled_adapters=["apt"])
    orc = Orchestrator(repo=repo, config=cfg)

    mock_apt = MagicMock()
    mock_apt.is_available.return_value = True
    # 1.5 GB
    mock_apt.get_download_size.return_value = int(1.5 * 1024 * 1024 * 1024)
    orc.adapters["apt"] = mock_apt

    summary = orc.get_update_download_summary()
    assert summary["is_large_download"] is True
    assert "Metered connection caution" in (summary["warning"] or "")
    assert "GB" in summary["formatted_size"]


def test_version_tuple_comparison():
    assert parse_version_tuple("0.2.2") == (0, 2, 2)
    assert parse_version_tuple("v0.3.0") == (0, 3, 0)
    assert parse_version_tuple("0.3.0") > parse_version_tuple("0.2.2")
    assert parse_version_tuple("0.2.3") > parse_version_tuple("0.2.2")
    assert parse_version_tuple("1.0.0") > parse_version_tuple("0.9.9")


def test_self_updater_mock():
    mock_release_json = json.dumps({
        "tag_name": "v0.9.9",
        "name": "ULUM 0.9.9 Release",
        "body": "Major improvements and bug fixes.",
        "html_url": "https://github.com/Akai-Abd/ulum/releases/tag/v0.9.9",
        "assets": [
            {
                "name": "ulum_0.9.9_all.deb",
                "browser_download_url": "https://github.com/Akai-Abd/ulum/releases/download/v0.9.9/ulum_0.9.9_all.deb",
            }
        ]
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = mock_release_json
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = SelfUpdater.check_latest_release()
        assert res["success"] is True
        assert res["update_available"] is True
        assert res["latest_version"] == "0.9.9"
        assert res["deb_filename"] == "ulum_0.9.9_all.deb"


def test_apt_repo_doctor_backup_and_restore(tmp_path: Path, monkeypatch):
    sources_dir = tmp_path / "sources.list.d"
    sources_dir.mkdir()
    sources_file = sources_dir / "broken.list"
    original_text = "deb http://ppa.launchpad.net/dead/ppa/ubuntu noble main\n"
    sources_file.write_text(original_text, encoding="utf-8")

    monkeypatch.setattr(AptRepoDoctor, "SOURCES_DIR", sources_dir)
    monkeypatch.setattr(AptRepoDoctor, "PRIMARY_SOURCES", tmp_path / "sources.list")

    entry = {
        "file": str(sources_file),
        "line_number": 1,
        "reason": "404 Not Found",
        "file_type": "list",
    }

    # Disable entry
    ok, msg = AptRepoDoctor.disable_broken_entry(entry, dry_run=False)
    assert ok
    assert "# DISABLED BY ULUM" in sources_file.read_text(encoding="utf-8")

    # Verify backup exists
    backups = list(sources_dir.glob("broken.list.ulum-backup-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == original_text

    # Restore backups
    res = AptRepoDoctor.restore_all_backups()
    assert res["restored_count"] >= 1
    assert sources_file.read_text(encoding="utf-8") == original_text


def test_apt_repo_doctor_allow_list(tmp_path: Path, monkeypatch):
    sources_file = tmp_path / "test.list"
    sources_file.write_text("deb http://ppa.launchpad.net/myppa/ubuntu noble main\n", encoding="utf-8")
    monkeypatch.setattr(AptRepoDoctor, "SOURCES_DIR", tmp_path)
    monkeypatch.setattr(AptRepoDoctor, "PRIMARY_SOURCES", tmp_path / "dummy.list")

    broken_urls = [{"url": "http://ppa.launchpad.net/myppa/ubuntu", "reason": "404 Not Found"}]
    # Without allow-list: matched
    matched = AptRepoDoctor.find_source_files_for_urls(broken_urls, allow_list=[])
    assert len(matched) == 1

    # With allow-list: ignored
    matched_allowed = AptRepoDoctor.find_source_files_for_urls(broken_urls, allow_list=["myppa"])
    assert len(matched_allowed) == 0


def test_kernel_cleaner_unknown_kernel_abort(monkeypatch):
    monkeypatch.setattr(KernelCleaner, "get_running_kernel", lambda: "unknown")
    plan = KernelCleaner.plan_cleanup()
    assert plan["is_safe"] is False
    assert "Cannot detect running kernel" in plan["safety_error"]


def test_kernel_cleaner_snapshot_and_dkms(monkeypatch):
    monkeypatch.setattr(KernelCleaner, "detect_snapshot_tool", classmethod(lambda cls: "timeshift"))
    monkeypatch.setattr(KernelCleaner, "check_dkms_modules", classmethod(lambda cls: ["nvidia/535.183.01, 6.8.0-140-generic"]))

    mock_packages = [
        {"package": "linux-image-6.8.0-151-generic", "version": "6.8.0-151", "status": "install ok installed", "size_bytes": 100000000},
        {"package": "linux-image-6.8.0-149-generic", "version": "6.8.0-149", "status": "install ok installed", "size_bytes": 100000000},
        {"package": "linux-image-6.8.0-140-generic", "version": "6.8.0-140", "status": "install ok installed", "size_bytes": 100000000},
    ]

    with patch.object(KernelCleaner, "get_running_kernel", return_value="6.8.0-151-generic"), \
         patch.object(KernelCleaner, "list_kernel_packages", return_value=mock_packages):
        plan = KernelCleaner.plan_cleanup()
        assert plan["snapshot_tool"] == "timeshift"
        assert plan["snapshot_recommended"] is True
        assert len(plan["dkms_warnings"]) == 1
        assert "6.8.0-140-generic" in plan["dkms_warnings"][0]


def test_appimage_unintegrate(tmp_path: Path, monkeypatch):
    app_bin = tmp_path / "myapp.AppImage"
    app_bin.write_text("#!/bin/sh\n")
    desktop_dir = tmp_path / "applications"
    monkeypatch.setattr(AppImageAdapter, "get_desktop_dir", classmethod(lambda cls: desktop_dir))

    # Integrate first
    ok, msg, dfile = AppImageAdapter.integrate_appimage(app_bin)
    assert ok
    assert dfile.exists()

    # Unintegrate
    un_ok, un_msg = AppImageAdapter.unintegrate_appimage("myapp")
    assert un_ok
    assert not dfile.exists()


def test_self_updater_sha256_verification(tmp_path: Path, monkeypatch):
    import hashlib
    fake_deb = tmp_path / "fake.deb"
    fake_content = b"package-binary-data" * 100
    fake_deb.write_bytes(fake_content)
    real_sha = hashlib.sha256(fake_content).hexdigest()

    # Test 1: Refuse when require_sha256 is True but no checksum provided
    res1 = SelfUpdater.apply_update("https://example.com/deb.deb", expected_sha256=None, require_sha256=True)
    assert not res1.success
    assert "SHA256 checksum is mandatory" in res1.stderr

    # Test 2: Mismatch aborts
    mock_resp = MagicMock()
    mock_resp.read.return_value = fake_content
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res2 = SelfUpdater.apply_update("https://example.com/deb.deb", expected_sha256="wronghash00000000000000000000000000000000000000000000000000000000")
        assert not res2.success
        assert "mismatch" in res2.stderr

