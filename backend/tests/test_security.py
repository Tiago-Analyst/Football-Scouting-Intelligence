"""Security posture: headers, CORS, rate limiting, error disclosure, docs exposure."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.errors import DataNotValidatedError, NotFoundError, ProviderNotConfiguredError
from app.main import create_app
from tests.conftest import build_client, build_settings


class TestSecurityHeaders:
    def test_hardening_headers_are_present(self, client: TestClient) -> None:
        headers = client.get("/health/live").headers
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["X-Frame-Options"] == "DENY"
        assert headers["Referrer-Policy"] == "no-referrer"

    def test_request_id_is_returned(self, client: TestClient) -> None:
        assert client.get("/health/live").headers.get("x-request-id")

    def test_supplied_request_id_is_echoed(self, client: TestClient) -> None:
        """Lets a frontend correlate a failed call with a server-side log line."""
        response = client.get("/health/live", headers={"x-request-id": "abc-123"})
        assert response.headers["x-request-id"] == "abc-123"


class TestCors:
    def test_allowed_origin_is_permitted(self, client: TestClient) -> None:
        response = client.get("/health/live", headers={"Origin": "http://localhost:3000"})
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_unknown_origin_is_not_granted_access(self, client: TestClient) -> None:
        response = client.get("/health/live", headers={"Origin": "http://evil.test"})
        assert response.headers.get("access-control-allow-origin") is None


class TestRateLimiting:
    def test_requests_beyond_the_limit_are_rejected(self) -> None:
        with build_client(build_settings(rate_limit_per_minute=3)) as client:
            statuses = [client.get("/api/v1/meta").status_code for _ in range(5)]
        assert statuses[:3] == [200, 200, 200]
        assert statuses[3:] == [429, 429]

    def test_rejection_includes_retry_after(self) -> None:
        with build_client(build_settings(rate_limit_per_minute=1)) as client:
            client.get("/api/v1/meta")
            response = client.get("/api/v1/meta")
        assert response.status_code == 429
        assert int(response.headers["Retry-After"]) >= 1

    def test_health_is_exempt_so_probes_keep_working(self) -> None:
        """A rate-limited health check would make an orchestrator kill a healthy pod."""
        with build_client(build_settings(rate_limit_per_minute=1)) as client:
            statuses = [client.get("/health/live").status_code for _ in range(5)]
        assert statuses == [200] * 5


class TestErrorDisclosure:
    @staticmethod
    def _app_with_failing_route(**settings_overrides: object):
        settings = build_settings(**settings_overrides)
        app = create_app(settings)

        @app.get("/boom")
        def boom() -> None:
            raise RuntimeError("secret internal detail: table dim_player column salary")

        @app.get("/missing")
        def missing() -> None:
            raise NotFoundError("Player not found")

        @app.get("/no-provider")
        def no_provider() -> None:
            raise ProviderNotConfiguredError("FootyStats API key is not configured")

        @app.get("/unvalidated")
        def unvalidated() -> None:
            raise DataNotValidatedError("Metric mapping pending FootyStats validation")

        return TestClient(app, raise_server_exceptions=False)

    def test_production_hides_internal_error_detail(self) -> None:
        client = self._app_with_failing_route(app_env="production", debug=False)
        response = client.get("/boom")
        assert response.status_code == 500
        assert "dim_player" not in response.text
        assert "salary" not in response.text
        assert response.json()["error"]["message"] == "An internal error occurred."

    def test_production_hides_detail_even_if_debug_is_left_on(self) -> None:
        """Belt and braces: DEBUG=true in a production deploy must not leak internals."""
        client = self._app_with_failing_route(app_env="production", debug=True)
        assert "dim_player" not in client.get("/boom").text

    def test_development_surfaces_detail_for_debugging(self) -> None:
        client = self._app_with_failing_route(app_env="development", debug=True)
        assert "dim_player" in client.get("/boom").text

    def test_domain_errors_map_to_their_status_codes(self) -> None:
        client = self._app_with_failing_route()
        assert client.get("/missing").status_code == 404
        assert client.get("/no-provider").status_code == 503
        assert client.get("/unvalidated").status_code == 501

    def test_errors_share_one_envelope_shape(self) -> None:
        client = self._app_with_failing_route()
        body = client.get("/missing").json()
        assert body["error"]["code"] == "not_found"
        assert body["error"]["message"] == "Player not found"


class TestDocsExposure:
    def test_docs_are_available_outside_production(self, client: TestClient) -> None:
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200

    def test_docs_are_disabled_in_production(self) -> None:
        """The schema describes the whole API surface; do not publish it."""
        with build_client(build_settings(app_env="production")) as client:
            assert client.get("/docs").status_code == 404
            assert client.get("/openapi.json").status_code == 404
