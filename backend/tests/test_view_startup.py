"""The analytical view is built once, and early in production.

It used to be built by the first request that needed it - about 11 seconds on
1 CPU, measured on 25 November - and two requests arriving together built two.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest

from app import main
from app.services import analytics_service
from app.services.analytics_service import get_analytics_view

WAIT = 5.0


@pytest.fixture(autouse=True)
def _empty_cache() -> Iterator[None]:
    get_analytics_view.cache_clear()
    yield
    get_analytics_view.cache_clear()


class SlowBuild:
    """A build that stays in progress until the test releases it."""

    def __init__(self) -> None:
        self.calls = 0
        self.started = threading.Event()
        self.release = threading.Event()

    def __call__(self, _settings: Any) -> object:
        self.calls += 1
        self.started.set()
        assert self.release.wait(WAIT)
        return object()


def in_thread(target: Any) -> threading.Thread:
    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread


def test_callers_arriving_during_a_build_share_it(monkeypatch: pytest.MonkeyPatch) -> None:
    build = SlowBuild()
    monkeypatch.setattr(analytics_service, "build_view", build)
    seen: list[object] = []

    threads = [in_thread(lambda: seen.append(get_analytics_view())) for _ in range(5)]
    assert build.started.wait(WAIT)
    build.release.set()
    for thread in threads:
        thread.join(WAIT)

    assert build.calls == 1
    assert len(seen) == 5
    assert len(set(map(id, seen))) == 1


def test_a_reload_during_a_build_does_not_keep_its_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The build in progress may have read the database before the load."""
    build = SlowBuild()
    monkeypatch.setattr(analytics_service, "build_view", build)
    early: list[object] = []
    reloaded: list[object] = []

    first = in_thread(lambda: early.append(get_analytics_view()))
    assert build.started.wait(WAIT)
    reload = in_thread(lambda: reloaded.append(analytics_service.refresh_analytics_view()))
    build.release.set()
    first.join(WAIT)
    reload.join(WAIT)

    assert build.calls == 2
    assert reloaded[0] is not early[0]


def test_a_failed_build_is_tried_again(monkeypatch: pytest.MonkeyPatch) -> None:
    outcomes: list[Any] = [RuntimeError("database away"), "view"]

    def build(_settings: Any) -> Any:
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(analytics_service, "build_view", build)

    main._build_view_early()  # logs, does not raise

    assert get_analytics_view() == "view"


@pytest.mark.parametrize(
    ("production", "database_up", "expected"),
    [(True, True, True), (False, True, False), (True, False, False)],
)
def test_startup_builds_only_in_production_with_a_database(
    monkeypatch: pytest.MonkeyPatch, production: bool, database_up: bool, expected: bool
) -> None:
    built = threading.Event()
    settings = SimpleNamespace(
        is_production=production,
        app_mode=SimpleNamespace(value="demo"),
        safe_summary=dict,
    )
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "check_database_connection", lambda: (database_up, None))
    monkeypatch.setattr(main, "dispose_engine", lambda: None)
    monkeypatch.setattr(main, "get_analytics_view", built.set)

    async def run() -> None:
        async with main.lifespan(main.app):
            pass

    asyncio.run(run())

    assert built.wait(WAIT if expected else 0.2) is expected
