"""Reloading the analytical view, and who may ask.

The gap this closes: a successful load put new rows in PostgreSQL and the
running API went on serving the view it built at start-up. `view_is_stale()`
could tell you the two disagreed and `refresh_analytics_view()` could fix it,
but nothing connected them - so new data reached the database and stopped
there until somebody restarted the service.
"""

from __future__ import annotations

import weakref
from collections.abc import Iterator
from typing import Any, ClassVar

import pytest
from fastapi.testclient import TestClient

from app.services import analytics_service
from app.services.analytics_service import get_analytics_view, refresh_analytics_view
from tests.conftest import build_client, build_settings

TOKEN = "an-internal-token"
WRONG = "an-internal-tokem"  # same length, so a length check cannot pass this


@pytest.fixture
def internal() -> TestClient:
    with build_client(build_settings(internal_token=TOKEN)) as client:
        yield client


class TestWhoMayAsk:
    def test_the_pipeline_may(self, internal: TestClient) -> None:
        response = internal.post(
            "/api/v1/internal/reload-analytics",
            headers={"x-internal-token": TOKEN},
        )
        assert response.status_code == 200

    def test_a_wrong_token_may_not(self, internal: TestClient) -> None:
        response = internal.post(
            "/api/v1/internal/reload-analytics",
            headers={"x-internal-token": WRONG},
        )
        assert response.status_code == 401

    def test_no_token_may_not(self, internal: TestClient) -> None:
        assert internal.post("/api/v1/internal/reload-analytics").status_code == 401

    def test_an_empty_header_is_not_a_token(self, internal: TestClient) -> None:
        response = internal.post(
            "/api/v1/internal/reload-analytics", headers={"x-internal-token": ""}
        )
        assert response.status_code == 401

    def test_an_unconfigured_deployment_has_no_such_endpoint(self) -> None:
        """404 rather than 401, deliberately.

        Answering "wrong credentials" would confirm the route exists and is
        worth guessing at. A deployment nothing is meant to reach into should
        not advertise the door.
        """
        with build_client(build_settings(internal_token=None)) as client:
            for headers in ({}, {"x-internal-token": ""}, {"x-internal-token": "guess"}):
                response = client.post("/api/v1/internal/reload-analytics", headers=headers)
                assert response.status_code == 404

    def test_the_build_token_does_not_open_this_door(self) -> None:
        """The two secrets are deliberately not interchangeable.

        `build_token` lifts a rate limit, grants no access a public caller
        lacks, and lives in a build's environment on somebody else's
        infrastructure. This endpoint makes the service rebuild its view. A
        secret that leaks from a build log must not also be able to drive it.
        """
        settings = build_settings(build_token="a-build-token", internal_token=TOKEN)
        with build_client(settings) as client:
            response = client.post(
                "/api/v1/internal/reload-analytics",
                headers={"x-build-token": "a-build-token"},
            )
            assert response.status_code == 401

    def test_it_is_not_a_get(self, internal: TestClient) -> None:
        """A state change must not be reachable by anything that prefetches."""
        response = internal.get(
            "/api/v1/internal/reload-analytics", headers={"x-internal-token": TOKEN}
        )
        assert response.status_code == 405


@pytest.mark.integration
class TestWhatItDoes:
    def test_it_reports_what_it_rebuilt(self, internal: TestClient) -> None:
        body = internal.post(
            "/api/v1/internal/reload-analytics",
            headers={"x-internal-token": TOKEN},
        ).json()

        assert body["players"] >= 0
        assert body["competitions"] >= 0
        assert body["build_seconds"] >= 0
        assert body["is_stale"] is False

    def test_reloading_unchanged_data_says_nothing_changed(self, internal: TestClient) -> None:
        """The distinction a pipeline needs.

        "The load reached the API" and "the load changed nothing" look
        identical from outside and mean very different things about the run
        that just finished.
        """
        headers = {"x-internal-token": TOKEN}
        internal.post("/api/v1/internal/reload-analytics", headers=headers)
        second = internal.post("/api/v1/internal/reload-analytics", headers=headers).json()
        assert second["changed"] is False

    def test_the_served_view_is_the_reloaded_one(self, internal: TestClient) -> None:
        """Not merely that a rebuild happened - that the API now serves it."""
        before = get_analytics_view()
        internal.post("/api/v1/internal/reload-analytics", headers={"x-internal-token": TOKEN})
        after = get_analytics_view()
        assert after is not before, "the cached view was not replaced"
        assert len(after.players) == len(before.players)


@pytest.fixture
def _restore_the_cached_view() -> Iterator[None]:
    """Leave the process-wide view as it was found.

    These tests put a stub in the cache. Nothing clears it between tests, so
    without this the next test to ask for the view would be handed a fake.
    """
    get_analytics_view.cache_clear()
    yield
    get_analytics_view.cache_clear()


class TestOnlyOneViewExistsAtATime:
    """The rebuild must not need room for two views.

    WHAT HAPPENED

    9 November, production. The pipeline promoted a dataset and called this
    endpoint. The process died 6.6 seconds in, Render's proxy answered 502,
    and the service restarted - ten minutes of no API. Reproduced twice, the
    second time with the instance verifiably warm, which is what ruled out a
    cold start.

    The handler read `before = get_analytics_view()` and kept it for the whole
    rebuild in order to compare one fingerprint afterwards. That local held
    every percentile table, similarity matrix and best-role ranking of the
    outgoing view alive while the incoming one was built, so peak memory was
    two complete views on a 512 MB instance.

    It was invisible in every other configuration: a restart rebuilds the view
    anyway, so the data still reached readers and the only symptom was downtime
    nobody attributed to this. There is no worker timeout to blame - the
    service runs `uvicorn` with no master process and no `--timeout`.

    WHAT IS ASSERTED

    Not an amount of memory, which would be a different number on every
    machine and would not fail on the mistake. The mistake is a reference
    surviving into the rebuild, so that is what is measured: a weak reference
    to the outgoing view, read from inside the construction of its
    replacement.
    """

    def test_the_handler_holds_nothing_while_the_replacement_is_built(
        self, monkeypatch: pytest.MonkeyPatch, _restore_the_cached_view: None
    ) -> None:
        """The defect itself, with no database in the way.

        A stub stands in for the view because what is being measured is who
        holds a reference, not what the thing referenced contains.
        """

        class StubView:
            """Weak-referenceable, and enough of a view for the response."""

            fingerprint = "unchanged"
            # Shared across instances on purpose: the handler only asks these
            # for their length, and giving each stub its own would be
            # furnishing a fake nobody looks inside.
            players: ClassVar[dict[str, Any]] = {}
            competitions: ClassVar[dict[str, str]] = {}

        witness: list[weakref.ReferenceType[StubView]] = []
        alive_during_the_build: list[bool] = []

        def stub_build(_settings: Any) -> StubView:
            if witness:
                alive_during_the_build.append(witness[0]() is not None)
            return StubView()

        monkeypatch.setattr(analytics_service, "build_view", stub_build)

        with build_client(build_settings(internal_token=TOKEN)) as client:
            get_analytics_view.cache_clear()
            outgoing = get_analytics_view()
            witness.append(weakref.ref(outgoing))
            del outgoing

            response = client.post(
                "/api/v1/internal/reload-analytics",
                headers={"x-internal-token": TOKEN},
            )

        assert response.status_code == 200
        assert alive_during_the_build == [False], (
            "the view being replaced was still referenced while its replacement "
            "was built - peak memory is two views, which is what killed the "
            "process in production"
        )

    @pytest.mark.integration
    def test_a_real_view_is_freed_before_the_next_one_is_allocated(
        self, _restore_the_cached_view: None
    ) -> None:
        """The same question asked of the real thing.

        A stub proves the handler lets go. It cannot prove a real view is
        collectable: a view is a graph of engines holding one another, and
        anything caught in a reference cycle outlives the last reference to it
        until a collection runs. That is why `refresh_analytics_view` collects
        between dropping the old view and building the new one, and this is the
        test that would notice if a cycle were introduced that defeats it.
        """
        witness = weakref.ref(get_analytics_view())
        assert witness() is not None, "nothing was built to observe"

        refresh_analytics_view()

        assert witness() is None, (
            "the previous view survived its own replacement - something now "
            "holds it, or holds a cycle containing it"
        )
