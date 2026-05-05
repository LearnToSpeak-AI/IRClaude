from pathlib import Path

from myorch.config import Settings


def test_default_settings_resolve_paths():
    s = Settings()
    assert s.apps_root == Path("/home/user/Documents/APPS")
    assert s.data_dir.name == ".myorch"
    assert s.db_path.suffix == ".db"
    assert s.tmp_dir == Path("/tmp/myorch")
    assert s.host == "127.0.0.1"
    assert s.port == 7000


def test_settings_can_be_overridden_via_env(monkeypatch):
    monkeypatch.setenv("MYORCH_PORT", "9999")
    monkeypatch.setenv("MYORCH_APPS_ROOT", "/tmp/fake_apps")
    s = Settings()
    assert s.port == 9999
    assert s.apps_root == Path("/tmp/fake_apps")
