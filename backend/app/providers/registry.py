"""Provider selection.

One place decides which performance provider the application uses, so the rule
that matters is enforceable in one place:

    **Production never falls back to mock data.**

A missing FootyStats key in production raises. It does not quietly return
fabricated figures, because a fabricated figure that reaches a recruitment
decision is the worst outcome this system can produce - worse than an outage,
because an outage is visible.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import AppMode, Settings, get_settings
from app.core.errors import DataNotValidatedError, ProviderNotConfiguredError
from app.core.logging import get_logger
from app.providers.base import PerformanceDataProvider
from app.providers.footystats_mapping import get_mapping
from app.providers.market_base import MarketDataProvider, MarketDataUnavailableError
from app.providers.market_mock import MockMarketProvider
from app.providers.mock import MockPerformanceProvider
from app.providers.transfermarkt import TransfermarktDatasetProvider

log = get_logger(__name__)


def build_performance_provider(settings: Settings) -> PerformanceDataProvider:
    """Construct the provider for the configured application mode."""
    if settings.app_mode is AppMode.DEMO:
        log.info("provider_selected", provider="MockPerformanceProvider", mode="demo")
        return MockPerformanceProvider()

    # -- Production ---------------------------------------------------------
    if not settings.footystats_configured:
        raise ProviderNotConfiguredError(
            "Production mode requires a FootyStats API key. No performance data "
            "provider is available.",
            details={"app_mode": settings.app_mode.value},
        )

    # A key alone is not enough. Which metrics FootyStats can supply is read
    # from the verified mapping rather than asserted here, so "not validated
    # yet" is a fact in a file that the profiling pipeline updates — not a
    # `raise` somebody has to remember to delete.
    mapping = get_mapping()
    mapping.require()  # empty mapping -> DataNotValidatedError

    raise DataNotValidatedError(
        "FootyStatsProvider is not implemented. The field mapping is verified "
        f"for {len(mapping.available_metrics)} metrics, but no provider has been "
        "written against it yet.",
        details={"verified_metrics": len(mapping.available_metrics)},
    )


def build_market_provider(settings: Settings) -> MarketDataProvider:
    """Construct the market data provider for the configured mode.

    Unlike the performance side, the real market source exists: the
    Transfermarkt dataset schema has been profiled and its mapping written
    against observed files. Production therefore uses it directly - but still
    raises if the snapshot is absent rather than falling back to demo data.
    """
    if settings.app_mode is AppMode.DEMO:
        log.info("market_provider_selected", provider="MockMarketProvider", mode="demo")
        return MockMarketProvider()

    try:
        provider = TransfermarktDatasetProvider()
    except MarketDataUnavailableError as exc:
        raise ProviderNotConfiguredError(
            f"Transfermarkt snapshot unavailable: {exc}",
            details={"app_mode": settings.app_mode.value},
        ) from exc

    log.info(
        "market_provider_selected",
        provider="TransfermarktDatasetProvider",
        mode=settings.app_mode.value,
    )
    return provider


@lru_cache(maxsize=1)
def get_market_provider() -> MarketDataProvider:
    """Cached market provider. Loading the snapshot is expensive; do it once."""
    return build_market_provider(get_settings())


@lru_cache(maxsize=1)
def get_performance_provider() -> PerformanceDataProvider:
    """Cached provider for the current settings.

    Building the mock provider generates a few thousand records, so it is done
    once per process rather than per call. Tests that change settings clear the
    cache with `get_performance_provider.cache_clear()`.
    """
    return build_performance_provider(get_settings())
