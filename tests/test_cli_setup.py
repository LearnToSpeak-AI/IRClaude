from pathlib import Path

from typer.testing import CliRunner

from myorch.cli import app


runner = CliRunner()


def test_setup_writes_toml_and_calls_ergo_fetch(monkeypatch, tmp_path: Path):
    home = tmp_path / "home"; home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    fetched_to: list[Path] = []

    def fake_download(target_dir, version, expected_sha256):
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "ergo").write_bytes(b"#!/bin/sh\n")
        (target_dir / "ergo").chmod(0o755)
        fetched_to.append(target_dir)
        return target_dir / "ergo"

    monkeypatch.setattr("myorch.cli.download_ergo", fake_download, raising=False)

    apps = tmp_path / "apps" / "Foo"
    apps.mkdir(parents=True)

    monkeypatch.setenv("MYORCH_APPS_ROOT", str(tmp_path / "apps"))
    monkeypatch.setattr(
        "myorch.cli.detect_weechat_plugin_dir",
        lambda: tmp_path / "weechat" / "python" / "autoload",
        raising=False,
    )

    result = runner.invoke(app, ["setup"], input="y\n")
    assert result.exit_code == 0
    cfg = home / ".config" / "myorch" / "config.toml"
    assert cfg.exists()
    assert "apps_root" in cfg.read_text(encoding="utf-8")
    assert fetched_to


def test_setup_weechat_symlink_creates_plugin_link(tmp_path, monkeypatch):
    plugin_dir = tmp_path / "weechat" / "python" / "autoload"
    plugin_dir.mkdir(parents=True)
    monkeypatch.setattr(
        "myorch.cli.detect_weechat_plugin_dir", lambda: plugin_dir, raising=False
    )
    repo_plugin = tmp_path / "repo" / "weechat_plugin" / "myorch.py"
    repo_plugin.parent.mkdir(parents=True)
    repo_plugin.write_text("# plugin", encoding="utf-8")
    monkeypatch.setattr("myorch.cli.repo_plugin_path", lambda: repo_plugin, raising=False)

    result = runner.invoke(app, ["setup-weechat"])
    assert result.exit_code == 0
    linked = plugin_dir / "myorch.py"
    assert linked.exists() or linked.is_symlink()


def test_setup_weechat_prints_manual_fallback_when_dir_missing(monkeypatch):
    monkeypatch.setattr("myorch.cli.detect_weechat_plugin_dir", lambda: None, raising=False)
    result = runner.invoke(app, ["setup-weechat"])
    assert result.exit_code == 0
    assert "manual" in result.stdout.lower() or "could not" in result.stdout.lower()
