import pytest
from desktop_sprite.ai.provider import (
    AIProvider, DisabledProvider, ProviderError,
    ProviderDisabled, AuthError, RateLimitError, TimeoutError, NetworkError, BadRequestError,
)


def test_abstract_provider_cannot_be_instantiated():
    with pytest.raises(TypeError):
        AIProvider()  # type: ignore[abstract]


def test_disabled_provider_generate_raises_provider_disabled():
    p = DisabledProvider()
    with pytest.raises(ProviderDisabled):
        p.generate("sys", "user", timeout=1.0)


def test_provider_error_hierarchy():
    assert issubclass(ProviderDisabled, ProviderError)
    assert issubclass(AuthError, ProviderError)
    assert issubclass(RateLimitError, ProviderError)
    assert issubclass(TimeoutError, ProviderError)
    assert issubclass(NetworkError, ProviderError)
    assert issubclass(BadRequestError, ProviderError)


def test_provider_error_default_message():
    err = AuthError("bad key")
    assert "bad key" in str(err)
