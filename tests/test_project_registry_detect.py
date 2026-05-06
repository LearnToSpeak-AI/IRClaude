from pathlib import Path

from irclaude.services.project_registry import detect_project_type


def _make(tmp_path: Path, name: str, files: list[str]) -> Path:
    d = tmp_path / name
    d.mkdir()
    for f in files:
        (d / f).write_text("# stub\n")
    return d


def test_detect_django(tmp_path: Path):
    p = _make(tmp_path, "gate", ["manage.py"])
    info = detect_project_type(p)
    assert info["type"] == "django"
    assert "manage.py runserver" in info["dev_command"]
    assert info["dev_port"] == 8000


def test_detect_node(tmp_path: Path):
    p = _make(tmp_path, "front", ["package.json"])
    info = detect_project_type(p)
    assert info["type"] == "node"
    assert info["dev_command"] == "npm run dev"


def test_detect_python_generic(tmp_path: Path):
    p = _make(tmp_path, "lib", ["pyproject.toml"])
    info = detect_project_type(p)
    assert info["type"] == "python"


def test_detect_rust(tmp_path: Path):
    p = _make(tmp_path, "svc", ["Cargo.toml"])
    info = detect_project_type(p)
    assert info["type"] == "rust"
    assert info["dev_command"] == "cargo run"


def test_detect_unknown(tmp_path: Path):
    p = _make(tmp_path, "misc", ["README.md"])
    info = detect_project_type(p)
    assert info["type"] == "unknown"
    assert info["dev_command"] is None
