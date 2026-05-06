import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


def _xdg_data_home() -> Path:
    raw = os.environ.get("XDG_DATA_HOME")
    if raw:
        return Path(raw)
    return Path.home() / ".local" / "share"


def _xdg_config_home() -> Path:
    raw = os.environ.get("XDG_CONFIG_HOME")
    if raw:
        return Path(raw)
    return Path.home() / ".config"


def _default_apps_root() -> Path:
    return Path(os.environ.get("MYORCH_APPS_ROOT", str(Path.home() / "projects")))


def _default_data_dir() -> Path:
    raw = os.environ.get("MYORCH_DATA_DIR")
    if raw:
        return Path(raw)
    return _xdg_data_home() / "myorch"


def _default_config_file() -> Path:
    raw = os.environ.get("MYORCH_CONFIG_FILE")
    if raw:
        return Path(raw)
    return _xdg_config_home() / "myorch" / "config.toml"


class Settings(BaseModel):
    apps_root: Path = Field(default_factory=_default_apps_root)
    data_dir: Path = Field(default_factory=_default_data_dir)
    config_file: Path = Field(default_factory=_default_config_file)
    host: str = Field(default_factory=lambda: os.environ.get("MYORCH_HOST", "127.0.0.1"))
    port: int = Field(default_factory=lambda: int(os.environ.get("MYORCH_PORT", "6667")))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "data.db"

    @property
    def mcp_config_path(self) -> Path:
        return self.data_dir / "mcp.json"

    @property
    def run_dir(self) -> Path:
        return self.data_dir / "run"

    @property
    def bin_dir(self) -> Path:
        return self.data_dir / "bin"

    @property
    def etc_dir(self) -> Path:
        return self.data_dir / "etc"

    @property
    def ergo_binary(self) -> Path:
        return self.bin_dir / "ergo"

    @property
    def ergo_config(self) -> Path:
        return self.etc_dir / "ergo.yaml"

    @property
    def pid_file(self) -> Path:
        return self.run_dir / "myorch.pid"


_ENV_KEYS = {
    "apps_root": "MYORCH_APPS_ROOT",
    "data_dir": "MYORCH_DATA_DIR",
    "host": "MYORCH_HOST",
    "port": "MYORCH_PORT",
}


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def load_settings() -> Settings:
    """Build Settings by merging a TOML config file under env overrides.

    Precedence: env > TOML file > built-in defaults.
    """
    config_path = _default_config_file()
    file_data = _load_toml(config_path)

    overrides: dict[str, Any] = {}
    if "apps_root" in file_data:
        overrides["apps_root"] = Path(str(file_data["apps_root"]))
    if "data_dir" in file_data:
        overrides["data_dir"] = Path(str(file_data["data_dir"]))
    if "host" in file_data:
        overrides["host"] = str(file_data["host"])
    if "port" in file_data:
        overrides["port"] = int(file_data["port"])

    for field, env_key in _ENV_KEYS.items():
        if env_key in os.environ:
            raw = os.environ[env_key]
            overrides[field] = (
                Path(raw) if field in {"apps_root", "data_dir"} else
                int(raw) if field == "port" else
                raw
            )

    overrides.setdefault("config_file", config_path)
    return Settings(**overrides)


def get_settings() -> Settings:
    return load_settings()
