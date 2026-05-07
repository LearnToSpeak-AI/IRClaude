import secrets
import subprocess
from pathlib import Path
from textwrap import dedent

import yaml


_OPER_PASSWORD_HASH = (
    # bcrypt hash of "irclaude-local"; not used for remote auth (loopback only)
    "$2a$04$E5GvEZ.O5Os4M.YHBcJYS.4Vu8LRxQp4WQ/WfZxFHM7lI6f.gkxRq"
)


def _patch_overrides(
    config: dict,
    *,
    host: str,
    port: int,
    server_name: str,
    datastore_path: str,
    motd_path: str | None = None,
) -> dict:
    config.setdefault("server", {})
    config["server"]["name"] = server_name
    config["server"]["listeners"] = {f"{host}:{port}": {}}
    config["server"]["casemapping"] = "ascii"
    config["server"]["enable-rfc3339-time"] = True
    config["server"].setdefault("compatibility", {})["allow-truncation"] = False
    if motd_path is not None:
        config["server"]["motd"] = motd_path
    config.setdefault("accounts", {})
    config["accounts"]["authentication-enabled"] = False
    config["accounts"].setdefault("registration", {})["enabled"] = True
    config.setdefault("datastore", {})["path"] = datastore_path
    config.setdefault("languages", {})["enabled"] = False
    config.setdefault("opers", {})["claude-bot"] = {
        "class": "server-admin",
        "whois-line": "is the irclaude bridge bot",
        "password": _OPER_PASSWORD_HASH,
    }
    config.setdefault("oper-classes", {})["server-admin"] = {
        "title": "Server Admin",
        "capabilities": [
            "kill",
            "ban",
            "oper:local_kill",
            "oper:local_ban",
            "oper:local_unban",
            "rehash",
            "accreg",
        ],
    }
    return config


def generate_ergo_config(
    host: str,
    port: int,
    server_name: str = "irclaude.local",
    datastore_path: str = "ircd.db",
    binary_path: Path | str | None = None,
    motd_path: str | None = None,
) -> str:
    """Return a YAML ergo config string for a loopback IRCv3 server.

    If ``binary_path`` is provided, runs ``<binary> defaultconfig`` to obtain
    the upstream-blessed baseline (which evolves with ergo versions), then
    patches in our overrides. Otherwise falls back to a static minimal config
    suitable for tests but NOT guaranteed to satisfy ``ergo run``'s schema.
    """

    if binary_path is not None and Path(binary_path).exists():
        result = subprocess.run(
            [str(binary_path), "defaultconfig"],
            capture_output=True,
            text=True,
            check=True,
        )
        config = yaml.safe_load(result.stdout)
        return yaml.safe_dump(
            _patch_overrides(
                config,
                host=host,
                port=port,
                server_name=server_name,
                datastore_path=datastore_path,
                motd_path=motd_path,
            ),
            sort_keys=False,
        )

    config = {
        "network": {"name": "irclaude"},
        "server": {
            "name": server_name,
            "listeners": {f"{host}:{port}": {}},
            "casemapping": "ascii",
            "enforce-utf8": True,
            "lookup-hostnames": False,
            "enable-rfc3339-time": True,
            "compatibility": {"allow-truncation": False},
            "max-line-len": 8192,
            "ip-cloaking": {"enabled": False},
        },
        "accounts": {
            "registration": {
                "enabled": True,
                "enabled-callbacks": ["none"],
                "verify-timeout": "32h",
            },
            "authentication-enabled": False,
            "multiclient": {
                "enabled": True,
                "allowed-by-default": True,
            },
        },
        "channels": {
            "default-modes": "+nt",
            "max-channels-per-client": 200,
            "registration": {"enabled": True},
        },
        "opers": {
            "claude-bot": {
                "class": "server-admin",
                "whois-line": "is the irclaude bridge bot",
                "password": _OPER_PASSWORD_HASH,
            }
        },
        "oper-classes": {
            "server-admin": {
                "title": "Server Admin",
                "capabilities": [
                    "kill",
                    "ban",
                    "oper:local_kill",
                    "oper:local_ban",
                    "oper:local_unban",
                    "rehash",
                    "accreg",
                ],
            }
        },
        "history": {
            "enabled": True,
            "channel-length": 2048,
            "client-length": 1024,
        },
        "limits": {
            "nicklen": 32,
            "identlen": 20,
            "realnamelen": 150,
            "channellen": 64,
            "awaylen": 390,
            "kicklen": 390,
            "topiclen": 390,
            "monitor-entries": 100,
            "whowas-entries": 100,
            "chan-list-modes": 100,
            "registration-messages": 1024,
            "multiline": {"max-bytes": 4096, "max-lines": 100},
        },
        "datastore": {"path": datastore_path},
        "logging": [
            {
                "method": "stderr",
                "level": "info",
                "type": "* -userinput -useroutput",
            }
        ],
    }
    return yaml.safe_dump(config, sort_keys=False)


def fresh_oper_password() -> str:
    return secrets.token_urlsafe(24)


def _doc_header() -> str:
    return dedent(
        """\
        # Auto-generated by irclaude — do not edit manually.
        # Loopback-only IRCv3 server. Regenerate with `irclaude setup`.
        """
    )
