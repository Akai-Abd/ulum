import json
import threading
import urllib.request
from pathlib import Path
from ulum.core.config import UlumConfig
from ulum.core.models import CleanupCandidate, ConfidenceLevel
from ulum.core.orchestrator import Orchestrator
from ulum.gui.server import create_server

def test_api_server_endpoints(temp_db, tmp_path, monkeypatch):
    repo, _ = temp_db
    config = UlumConfig()
    orc = Orchestrator(repo, config)

    server = create_server(repo, config, orc, host="127.0.0.1", port=0)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    base_url = f"http://127.0.0.1:{port}"

    # 1. Test GET /
    with urllib.request.urlopen(base_url) as res:
      assert res.status == 200
      html = res.read().decode("utf-8")
      assert "Universal Linux Update Manager (ULUM)" in html

    # 2. Test GET /api/stats
    with urllib.request.urlopen(f"{base_url}/api/stats") as res:
      assert res.status == 200
      stats = json.loads(res.read().decode("utf-8"))
      assert "distro_name" in stats
      assert "installed_count" in stats
      assert "updates_count" in stats

    # 3. Test GET /api/inventory
    with urllib.request.urlopen(f"{base_url}/api/inventory") as res:
      assert res.status == 200
      inv = json.loads(res.read().decode("utf-8"))
      assert isinstance(inv, list)

    # 4. Test GET & POST /api/settings
    with urllib.request.urlopen(f"{base_url}/api/settings") as res:
      assert res.status == 200
      cfg = json.loads(res.read().decode("utf-8"))
      assert "enabled_adapters" in cfg

    req = urllib.request.Request(
        f"{base_url}/api/settings",
        data=json.dumps({"enabled_adapters": ["apt"], "require_confirmation": True}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as res:
      assert res.status == 200
      assert json.loads(res.read().decode("utf-8"))["success"] is True

    # 5. Test POST /api/cleanup with single target path
    cand_file = tmp_path / "test_cleanup.txt"
    cand_file.write_text("residual", encoding="utf-8")
    monkeypatch.setattr("ulum.gui.server.SafetyValidator.validate_cleanup_path", lambda p: (True, ""))
    repo.save_cleanup_candidates([CleanupCandidate(cand_file, "cache", "test", ConfidenceLevel.VERIFIED)], "test", "test")

    clean_req = urllib.request.Request(
        f"{base_url}/api/cleanup",
        data=json.dumps({"path": str(cand_file)}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(clean_req) as res:
      assert res.status == 200
      assert json.loads(res.read().decode("utf-8"))["deleted"] == 1
    assert not cand_file.exists()

    server.shutdown()
