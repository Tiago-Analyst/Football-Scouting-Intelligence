"""Health, readiness and metadata endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core import database as database_module
from tests.conftest import build_client, build_settings


class TestLiveness:
    def test_liveness_is_ok(self, client: TestClient) -> None:
        response = client.get("/health/live")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_liveness_does_not_touch_the_database(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Liveness must survive a total database outage."""

        def explode() -> None:
            raise AssertionError("liveness must not query the database")

        monkeypatch.setattr(database_module, "check_database_connection", explode)
        assert client.get("/health/live").status_code == 200


class TestReadiness:
    def test_reports_degraded_when_database_is_down(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.api.v1.health.check_database_connection",
            lambda: (False, "OperationalError: connection refused"),
        )
        response = client.get("/health")
        assert response.status_code == 503

        body = response.json()
        assert body["status"] == "degraded"
        db = next(d for d in body["dependencies"] if d["name"] == "postgresql")
        assert db["status"] == "unavailable"

    def test_does_not_leak_driver_detail_when_database_is_down(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Driver errors name hosts, users and databases. They must not be returned."""
        leaky = "OperationalError: password authentication failed for user fri_app"
        monkeypatch.setattr("app.api.v1.health.check_database_connection", lambda: (False, leaky))
        body = client.get("/health").text
        assert "password" not in body.lower()
        assert "fri_app" not in body

    def test_reports_degraded_when_database_is_unmigrated(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A reachable but unmigrated database is not ready to serve."""
        monkeypatch.setattr("app.api.v1.health.check_database_connection", lambda: (True, None))
        monkeypatch.setattr("app.api.v1.health.get_schema_revision", lambda: None)

        response = client.get("/health")
        assert response.status_code == 503
        body = response.json()
        assert body["schema_revision"] is None
        db = next(d for d in body["dependencies"] if d["name"] == "postgresql")
        assert db["status"] == "degraded"

    def test_reports_ok_when_database_is_migrated(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("app.api.v1.health.check_database_connection", lambda: (True, None))
        monkeypatch.setattr("app.api.v1.health.get_schema_revision", lambda: "0001_baseline")

        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["schema_revision"] == "0001_baseline"

    def test_footystats_absent_key_is_not_configured_not_failed(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """In demo mode a missing key is expected, so it must not read as a fault."""
        monkeypatch.setattr("app.api.v1.health.check_database_connection", lambda: (True, None))
        monkeypatch.setattr("app.api.v1.health.get_schema_revision", lambda: "0001_baseline")

        body = client.get("/health").json()
        assert body["status"] == "ok"
        fs = next(d for d in body["dependencies"] if d["name"] == "footystats")
        assert fs["status"] == "not_configured"


class TestMeta:
    def test_demo_mode_flags_mock_data(self, client: TestClient) -> None:
        body = client.get("/api/v1/meta").json()
        assert body["app_mode"] == "demo"
        assert body["demo_data_notice"]
        assert all(source["is_mock"] for source in body["data_sources"])

    def test_no_data_source_claims_to_be_validated_yet(self, client: TestClient) -> None:
        """Nothing may claim validated provider data before Phase 12 profiling."""
        body = client.get("/api/v1/meta").json()
        assert all(source["validated"] is False for source in body["data_sources"])

    def test_production_mode_has_no_demo_notice(self) -> None:
        with build_client(build_settings(app_mode="production")) as client:
            body = client.get("/api/v1/meta").json()
            assert body["app_mode"] == "production"
            assert body["demo_data_notice"] is None
            assert all(source["is_mock"] is False for source in body["data_sources"])

    def test_meta_never_exposes_the_api_key(self) -> None:
        with build_client(build_settings(footystats_api_key="SUPER_SECRET_KEY")) as client:
            assert "SUPER_SECRET_KEY" not in client.get("/api/v1/meta").text


@pytest.mark.integration
class TestAgainstRealDatabase:
    """Exercises the real local PostgreSQL. Deselect with -m 'not integration'."""

    def test_health_reports_ok_against_live_migrated_database(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "ok"
        assert body["schema_revision"] is not None
