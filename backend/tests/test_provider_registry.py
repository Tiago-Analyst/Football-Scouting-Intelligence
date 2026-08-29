"""Provider selection.

The safety property under test: **production never serves fabricated data.**
A silent fallback to the mock provider would put invented figures behind a UI
that says "production", which is the worst failure this system can produce.
"""

from __future__ import annotations

import pytest

from app.core.errors import DataNotValidatedError, ProviderNotConfiguredError
from app.providers.base import PerformanceDataProvider
from app.providers.mock import MockPerformanceProvider
from app.providers.registry import build_performance_provider
from tests.conftest import build_settings


class TestDemoMode:
    def test_returns_the_mock_provider(self) -> None:
        provider = build_performance_provider(build_settings(app_mode="demo"))
        assert isinstance(provider, MockPerformanceProvider)

    def test_works_without_any_api_key(self) -> None:
        """Demo mode must never depend on provider credentials - that is what
        makes the application runnable, and CI green, without them."""
        provider = build_performance_provider(
            build_settings(app_mode="demo", footystats_api_key="")
        )
        assert provider.info.is_mock is True

    def test_ignores_a_key_if_one_is_present(self) -> None:
        """Demo mode must not start calling a real API just because a key
        appeared in the environment."""
        provider = build_performance_provider(
            build_settings(app_mode="demo", footystats_api_key="some-key")
        )
        assert isinstance(provider, MockPerformanceProvider)


class TestProductionMode:
    def test_without_a_key_raises_rather_than_falling_back(self) -> None:
        with pytest.raises(ProviderNotConfiguredError):
            build_performance_provider(build_settings(app_mode="production", footystats_api_key=""))

    def test_with_a_key_it_builds_the_real_provider(self) -> None:
        """This asserted a refusal until the provider existed.

        The gate it protected has not gone: the registry still refuses unless
        the mapping grants at least one metric, and the mapping still refuses
        any entry that cannot name the response it was verified against. What
        changed is that both are now satisfied.
        """
        provider = build_performance_provider(
            build_settings(app_mode="production", footystats_api_key="a-real-looking-key")
        )
        assert provider.info.name == "FootyStatsProvider"
        assert provider.info.is_mock is False

    def test_an_empty_mapping_still_refuses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The gate itself, tested directly rather than through the absence of
        a provider: no verified field, no provider, whatever else is in place.
        """
        from app.providers import registry
        from app.providers.footystats_mapping import FootyStatsMapping

        empty = FootyStatsMapping(metrics={}, verified_against=(), rejected={})
        monkeypatch.setattr(registry, "get_mapping", lambda: empty)
        with pytest.raises(DataNotValidatedError):
            build_performance_provider(
                build_settings(app_mode="production", footystats_api_key="a-key")
            )

    @pytest.mark.parametrize("api_key", ["", "   ", "a-real-looking-key"])
    def test_never_returns_a_mock_provider(self, api_key: str) -> None:
        """The property that matters, stated directly: whatever the
        configuration, production mode either yields real data or raises."""
        result: PerformanceDataProvider | None = None
        try:
            result = build_performance_provider(
                build_settings(app_mode="production", footystats_api_key=api_key)
            )
        except (ProviderNotConfiguredError, DataNotValidatedError):
            return
        assert result is not None
        assert result.info.is_mock is False


class TestErrorsCarryUsefulDetail:
    def test_missing_provider_error_names_the_mode(self) -> None:
        with pytest.raises(ProviderNotConfiguredError) as excinfo:
            build_performance_provider(build_settings(app_mode="production", footystats_api_key=""))
        assert excinfo.value.details.get("app_mode") == "production"

    def test_the_refusal_without_a_key_says_which_mode(self) -> None:
        """The refusal has to say what would lift it, not just that it
        refused."""
        with pytest.raises(ProviderNotConfiguredError) as excinfo:
            build_performance_provider(build_settings(app_mode="production", footystats_api_key=""))
        assert "FootyStats API key" in str(excinfo.value)

    def test_errors_never_include_the_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Whatever the registry refuses for, the key must not be in the
        message: it reaches logs, and in development it reaches responses."""
        from app.providers import registry
        from app.providers.footystats_mapping import FootyStatsMapping

        secret = "SUPER_SECRET_KEY_VALUE"
        monkeypatch.setattr(
            registry,
            "get_mapping",
            lambda: FootyStatsMapping(metrics={}, verified_against=(), rejected={}),
        )
        with pytest.raises(DataNotValidatedError) as excinfo:
            build_performance_provider(
                build_settings(app_mode="production", footystats_api_key=secret)
            )
        assert secret not in str(excinfo.value)
        assert secret not in repr(excinfo.value.details)
