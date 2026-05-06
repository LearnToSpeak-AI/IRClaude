import os
from pathlib import Path

import pytest

from myorch.config import Settings, load_settings


def test_default_settings_use_xdg_paths(monkeypatch, tmp_path):
    monkeypatch.delenv("MYORCH_APPS_ROOT", raising=False)
    monkeypatch.delenv("MYORCH_DATA_DIR", raising=False)
    monkeypatch.delenv("MYORCH_CONFIG_FILE", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    s = Settings()
    assert s.apps_root == tmp_path / "projects"
    assert s.data_dir == tmp_path / ".local" / "share" / "myorch"
    assert s.config_file == tmp_path / ".config" / "myorch" / "config.toml"
    assert s.host == "127.0.0.1"
    assert s.port == 6667


def test_xdg_overrides_apply(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-conf"))
    monkeypatch.delenv("MYORCH_DATA_DIR", raising=False)
    monkeypatch.delenv("MYORCH_CONFIG_FILE", raising=False)

    s = Settings()
    assert s.data_dir == tmp_path / "xdg-data" / "myorch"
    assert s.config_file == tmp_path / "xdg-conf" / "myorch" / "config.toml"


def test_env_overrides_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("MYORCH_APPS_ROOT", str(tmp_path / "apps"))
    monkeypatch.setenv("MYORCH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MYORCH_PORT", "9999")
    s = Settings()
    assert s.apps_root == tmp_path / "apps"
    assert s.data_dir == tmp_path / "data"
    assert s.port == 9999


def test_db_path_and_mcp_paths_are_under_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("MYORCH_DATA_DIR", str(tmp_path / "d"))
    s = Settings()
    assert s.db_path == tmp_path / "d" / "data.db"
    assert s.mcp_config_path == tmp_path / "d" / "mcp.json"
    assert s.run_dir == tmp_path / "d" / "run"
    assert s.bin_dir == tmp_path / "d" / "bin"
    assert s.etc_dir == tmp_path / "d" / "etc"


def test_load_settings_merges_toml_file(monkeypatch, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        "apps_root = \"/srv/projects\"\n"
        "port = 7100\n"
        "host = \"127.0.0.1\"\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MYORCH_CONFIG_FILE", str(cfg))
    s = load_settings()
    assert s.apps_root == Path("/srv/projects")
    assert s.port == 7100


def test_env_wins_over_toml(monkeypatch, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("port = 7100\n", encoding="utf-8")
    monkeypatch.setenv("MYORCH_CONFIG_FILE", str(cfg))
    monkeypatch.setenv("MYORCH_PORT", "8200")
    s = load_settings()
    assert s.port == 8200
