import os
from pathlib import Path

from pydantic import BaseModel, Field


class Settings(BaseModel):
    apps_root: Path = Field(default_factory=lambda: Path(os.environ.get(
        "MYORCH_APPS_ROOT", "/home/user/Documents/APPS"
    )))
    data_dir: Path = Field(default_factory=lambda: Path(os.environ.get(
        "MYORCH_DATA_DIR", str(Path.home() / ".myorch")
    )))
    tmp_dir: Path = Field(default_factory=lambda: Path(os.environ.get(
        "MYORCH_TMP_DIR", "/tmp/myorch"
    )))
    host: str = Field(default_factory=lambda: os.environ.get("MYORCH_HOST", "127.0.0.1"))
    port: int = Field(default_factory=lambda: int(os.environ.get("MYORCH_PORT", "7000")))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "data.db"

    @property
    def mcp_config_path(self) -> Path:
        return self.data_dir / "mcp.json"


def get_settings() -> Settings:
    return Settings()
