
from plancosts import config


def test_normalizes_to_graphql_from_primary_env(monkeypatch):
    monkeypatch.setenv("PLANCOSTS_API_URL", "http://localhost:4000")
    monkeypatch.delenv("PLAN_COSTS_PRICE_LIST_API_ENDPOINT", raising=False)
    assert config.resolve_endpoint() == "http://localhost:4000/graphql"


def test_legacy_env_takes_precedence(monkeypatch):
    monkeypatch.setenv("PLANCOSTS_API_URL", "http://a:1")
    monkeypatch.setenv("PLAN_COSTS_PRICE_LIST_API_ENDPOINT", "http://b:2")
    assert config.resolve_endpoint() == "http://b:2/graphql"


def test_cli_override_wins(monkeypatch):
    monkeypatch.setenv("PLANCOSTS_API_URL", "http://a:1")
    monkeypatch.setenv("PLAN_COSTS_PRICE_LIST_API_ENDPOINT", "http://b:2")
    assert config.resolve_endpoint("http://c:3") == "http://c:3/graphql"


def test_load_config_exposes_no_color_and_terraform_binary(monkeypatch):
    monkeypatch.setenv("PLANCOSTS_API_URL", "http://localhost:4000")
    monkeypatch.setenv("TERRAFORM_BINARY", "/opt/tf")
    cfg = config.load_config(no_color=True)
    assert cfg.price_list_api_endpoint == "http://localhost:4000/graphql"
    assert cfg.no_color is True
    assert cfg.terraform_binary == "/opt/tf"
