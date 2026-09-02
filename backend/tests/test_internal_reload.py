"""Reloading the analytical view, and who may ask.

The gap this closes: a successful load put new rows in PostgreSQL and the
running API went on serving the view it built at start-up. `view_is_stale()`
could tell you the two disagreed and `refresh_analytics_view()` could fix it,
but nothing connected them - so new data reached the database and stopped
there until somebody restarted the service.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.services.analytics_service import get_analytics_view
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
