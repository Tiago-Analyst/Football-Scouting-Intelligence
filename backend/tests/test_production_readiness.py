"""The production posture, asserted from outside.

Production behaviour is a set of `if settings.is_production` branches spread
across the codebase — docs disabled here, secure cookies there, error detail
hidden somewhere else. Each is correct in isolation and none is checkable as a
whole, which is how a deployment accidentally configured as `development` serves
interactive API docs and stack traces while looking entirely normal.

Two things are covered here. The checks in `scripts/check_production` must
discriminate — a checker that fails everything is as useless as one that passes
everything. And the application itself must actually change behaviour when the
environment says production.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from scripts.check_production import (
    check_cors,
    check_database,
    check_environment,
    check_providers,
)
from tests.conftest import build_client, build_settings


def sound(**overrides: object):  # type: ignore[no-untyped-def]
    """A production configuration with nothing wrong with it."""
    defaults: dict[str, object] = {
        "app_env": "production",
        "app_mode": "production",
        "debug": False,
        "cors_allow_origins": ["https://scouting.example.com"],
        "postgres_host": "db.internal.example.com",
        "postgres_user": "fri_app",
        "postgres_password": "a-long-random-production-secret",
        "footystats_api_key": "a-key",
    }
    defaults.update(overrides)
    return build_settings(**defaults)


class TestTheCheckerDiscriminates:
    """A checker that always fails teaches people to bypass it."""

    def test_a_sound_configuration_passes_every_check(self) -> None:
        settings = sound()
        findings = [
            *check_environment(settings),
            *check_cors(settings),
            *check_database(settings),
            *check_providers(settings),
        ]
        assert findings == []

    def test_development_env_is_caught(self) -> None:
        findings = check_environment(sound(app_env="development"))
        assert [f.check for f in findings] == ["app_env"]
        assert all(f.failed for f in findings)

    def test_debug_is_caught(self) -> None:
        findings = check_environment(sound(debug=True))
        assert any(f.check == "debug" and f.failed for f in findings)

    @pytest.mark.parametrize(
        "origin",
        ["http://localhost:3000", "http://127.0.0.1:3000", "https://localhost"],
    )
    def test_a_local_cors_origin_is_caught(self, origin: str) -> None:
        findings = check_cors(sound(cors_allow_origins=[origin]))
        assert any(f.failed for f in findings), origin

    def test_a_plain_http_origin_is_caught(self) -> None:
        """The session cookie is Secure in production and would never be sent
        to an http origin, so the site would silently fail to sign anyone in."""
        findings = check_cors(sound(cors_allow_origins=["http://app.example.com"]))
        assert any(f.failed for f in findings)

    def test_an_https_origin_passes(self) -> None:
        assert check_cors(sound(cors_allow_origins=["https://app.example.com"])) == []

    @pytest.mark.parametrize("password", ["postgres", "password", "changeme", "admin"])
    def test_a_default_password_is_caught(self, password: str) -> None:
        findings = check_database(sound(postgres_password=password))
        assert any(f.check == "database" and f.failed for f in findings), password

    def test_a_short_password_warns_rather_than_fails(self) -> None:
        """Short is worth saying; short is not the same as guessable."""
        findings = check_database(sound(postgres_password="sh0rt-but-odd"))
        assert findings and not any(f.failed for f in findings)

    def test_connecting_as_a_superuser_is_caught(self) -> None:
        """A superuser connection turns any SQL injection into a full database
        compromise, and the application needs only its own schema."""
        findings = check_database(sound(postgres_user="postgres"))
        assert any(f.failed for f in findings)

    def test_a_password_is_never_printed(self) -> None:
        secret = "postgres"
        findings = check_database(sound(postgres_password=secret))
        assert findings
        assert all(secret not in f.detail for f in findings)

    def test_production_without_a_provider_key_is_caught(self) -> None:
        """The registry would refuse to build and the API would serve nothing."""
        findings = check_providers(sound(footystats_api_key=""))
        assert any(f.failed for f in findings)

    def test_demo_mode_warns_rather_than_fails(self) -> None:
        """A public preview on fabricated data is a legitimate deployment. It
        must be a deliberate one."""
        findings = check_providers(sound(app_mode="demo"))
        assert findings and not any(f.failed for f in findings)


class TestTheApplicationHonoursIt:
    """The checks above are worthless if production does not actually differ."""

    def test_api_docs_are_served_in_development(self) -> None:
        with build_client(build_settings(app_env="development")) as client:
            assert client.get("/docs").status_code == 200
            assert client.get("/openapi.json").status_code == 200

    def test_api_docs_are_not_served_in_production(self) -> None:
        """Section 28: the frontend receives results, not implementation. The
        schema names every endpoint and field the API has."""
        with build_client(sound(app_mode="demo")) as client:
            assert client.get("/docs").status_code == 404
            assert client.get("/openapi.json").status_code == 404

    def test_security_headers_are_always_set(self) -> None:
        with build_client(build_settings()) as client:
            headers = client.get("/health/live").headers
            assert headers["X-Content-Type-Options"] == "nosniff"
            assert headers["X-Frame-Options"] == "DENY"
            assert headers["Referrer-Policy"] == "no-referrer"

    def test_hsts_is_absent_in_development(self) -> None:
        """It would pin localhost to https in the developer's browser for a
        year, across every project they run on that port."""
        with build_client(build_settings(app_env="development")) as client:
            assert "Strict-Transport-Security" not in client.get("/health/live").headers

    def test_hsts_is_present_in_production(self) -> None:
        with build_client(sound(app_mode="demo")) as client:
            header = client.get("/health/live").headers["Strict-Transport-Security"]
            assert "max-age=" in header

    def test_a_wildcard_cors_origin_is_refused_outright(self) -> None:
        """Rejected by Settings rather than merely reported, because credentials
        are allowed and the two together let any site read a signed-in
        response."""
        with pytest.raises(Exception, match=r"(?i)cors|origin|\*"):
            build_settings(cors_allow_origins=["*"])

    def test_an_unhandled_error_leaks_nothing_in_production(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Even with DEBUG on, which is the combination a hurried deployment
        produces."""
        settings = sound(app_mode="demo", debug=True)
        client: TestClient = build_client(settings)

        from app.api.v1 import reference

        def explode() -> None:
            raise RuntimeError("secret-internal-detail")

        monkeypatch.setattr(reference, "get_analytics_view", explode)

        with client:
            body = client.get("/api/v1/competitions").json()

        assert "secret-internal-detail" not in str(body)
        assert body["error"]["message"] == "An internal error occurred."
