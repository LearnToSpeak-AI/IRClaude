import yaml

from irclaude.bridge.ergo_config import generate_ergo_config


def test_generated_config_binds_loopback_and_port():
    text = generate_ergo_config(host="127.0.0.1", port=6667)
    data = yaml.safe_load(text)
    listeners = data["server"]["listeners"]
    assert "127.0.0.1:6667" in listeners
    assert listeners["127.0.0.1:6667"] == {}


def test_generated_config_enables_required_caps():
    text = generate_ergo_config(host="127.0.0.1", port=6667)
    data = yaml.safe_load(text)
    assert data["server"]["compatibility"]["allow-truncation"] is False
    assert data["server"]["name"] == "irclaude.local"
    assert data["server"]["enable-rfc3339-time"] is True
    assert data["server"]["casemapping"] == "ascii"


def test_generated_config_uses_custom_server_name():
    text = generate_ergo_config(host="127.0.0.1", port=7777, server_name="custom.local")
    data = yaml.safe_load(text)
    assert data["server"]["name"] == "custom.local"
    assert "127.0.0.1:7777" in data["server"]["listeners"]


def test_generated_config_includes_operator_block():
    text = generate_ergo_config(host="127.0.0.1", port=6667)
    data = yaml.safe_load(text)
    opers = data["opers"]
    assert "claude-bot" in opers
    assert "password" in opers["claude-bot"]


def test_generated_config_disables_sasl_required():
    text = generate_ergo_config(host="127.0.0.1", port=6667)
    data = yaml.safe_load(text)
    accounts = data["accounts"]
    assert accounts["registration"]["enabled"] is True
    assert accounts["authentication-enabled"] is False
