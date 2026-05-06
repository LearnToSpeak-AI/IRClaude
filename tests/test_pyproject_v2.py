import importlib

import pytest


@pytest.mark.parametrize(
    "module",
    [
        "typer",
        "rich",
        "pygments",
        "anyio",
    ],
)
def test_v2_runtime_dependency_imports(module: str):
    importlib.import_module(module)


@pytest.mark.parametrize(
    "module",
    [
        "fastapi",
        "jinja2",
        "pexpect",
        "websockets",
        "aiofiles",
    ],
)
def test_v1_dependencies_are_gone(module: str):
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module)
