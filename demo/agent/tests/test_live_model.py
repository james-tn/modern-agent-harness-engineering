"""Public deployments require caller-owned endpoints and token authentication."""

from unittest.mock import Mock

import pytest

from equity_event import live_model
from equity_event.live_trace import LiveTrace


@pytest.fixture
def provider_arguments(monkeypatch):
    captured = {}
    credential = Mock()

    def initialize(_self, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(live_model.OpenAIChatClient, "__init__", initialize)
    monkeypatch.setattr(live_model, "AzureCliCredential", lambda: credential)
    return captured, credential


def test_live_requires_configured_endpoint(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    with pytest.raises(ValueError, match="Set AZURE_OPENAI_ENDPOINT"):
        live_model.LiveEquityClient(Mock(spec=LiveTrace))


def test_environment_endpoint_uses_token_authentication(monkeypatch, provider_arguments):
    arguments, credential = provider_arguments
    endpoint = "https://example.openai.azure.com/"
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", endpoint)
    client = live_model.LiveEquityClient(Mock(spec=LiveTrace))
    assert arguments["azure_endpoint"] == endpoint
    assert arguments["credential"] is credential
    assert client.credential is credential
    assert "api_key" not in arguments
    assert arguments["model"] == live_model.DEFAULT_DEPLOYMENT


def test_explicit_endpoint_takes_precedence(monkeypatch, provider_arguments):
    arguments, _ = provider_arguments
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://other.openai.azure.com/")
    endpoint = "https://example.cognitiveservices.azure.com/"
    live_model.LiveEquityClient(Mock(spec=LiveTrace), endpoint=endpoint)
    assert arguments["azure_endpoint"] == endpoint


@pytest.mark.parametrize("endpoint", [
    "",
    "http://example.openai.azure.com/",
    "https://example.invalid/",
    "https://user:password@example.openai.azure.com/",
    "https://example.openai.azure.com/?unexpected=query",
    "https://example.openai.azure.com/#fragment",
])
def test_invalid_environment_endpoint_fails_before_provider_creation(monkeypatch, endpoint):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", endpoint)
    credential = Mock(side_effect=AssertionError("Invalid configuration must not initialize credentials."))
    monkeypatch.setattr(live_model, "AzureCliCredential", credential)
    with pytest.raises(ValueError, match="AZURE_OPENAI_ENDPOINT|HTTPS Azure"):
        live_model.LiveEquityClient(Mock(spec=LiveTrace))
    credential.assert_not_called()
