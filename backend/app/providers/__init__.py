"""Performance data providers.

The application depends on `PerformanceDataProvider` and the canonical model,
never on a concrete provider or its field names.
"""

from app.providers.base import (
    PerformanceDataProvider,
    ProviderError,
    UnknownEntityError,
)
from app.providers.mock import MockPerformanceProvider
from app.providers.registry import build_performance_provider, get_performance_provider

__all__ = [
    "MockPerformanceProvider",
    "PerformanceDataProvider",
    "ProviderError",
    "UnknownEntityError",
    "build_performance_provider",
    "get_performance_provider",
]
