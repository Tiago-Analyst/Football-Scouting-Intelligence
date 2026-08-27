"""Settings behaviour, with emphasis on the rules that protect credentials."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tests.conftest import build_settings


class TestCorsOrigins:
    def test_parses_comma_separated_string(self) -> None:
        settings = build_settings(cors_allow_origins="http://a.test, http://b.test")
        assert settings.cors_allow_origins == ["http://a.test", "http://b.test"]

    def test_ignores_empty_segments(self) -> None:
        settings = build_settings(cors_allow_origins="http://a.test,,  ,http://b.test")
        assert settings.cors_allow_origins == ["http://a.test", "http://b.test"]

    def test_rejects_wildcard(self) -> None:
        """A wildcard origin plus credentials would expose the API to any site."""
        with pytest.raises(ValidationError):
            build_settings(cors_allow_origins="*")

    def test_rejects_wildcard_among_valid_origins(self) -> None:
        with pytest.raises(ValidationError):
            build_settings(cors_allow_origins="http://a.test,*")


class TestDatabaseUrl:
    def test_builds_url_from_parts(self) -> None:
        settings = build_settings(
            postgres_user="u",
            postgres_password="p",
            postgres_host="h",
            postgres_port=6000,
            postgres_db="d",
        )
        assert settings.sqlalchemy_url == "postgresql+psycopg://u:p@h:6000/d"

    def test_explicit_database_url_wins(self) -> None:
        settings = build_settings(database_url="postgresql+psycopg://x:y@z:5432/w")
        assert settings.sqlalchemy_url == "postgresql+psycopg://x:y@z:5432/w"

    @pytest.mark.parametrize(
        "given",
        ["postgres://u:p@h:5432/d", "postgresql://u:p@h:5432/d"],
    )
    def test_managed_provider_urls_are_normalised_to_psycopg(self, given: str) -> None:
        """Neon/Supabase/Railway hand out these forms; psycopg is the driver we install."""
        settings = build_settings(database_url=given)
        assert settings.sqlalchemy_url == "postgresql+psycopg://u:p@h:5432/d"

    def test_psycopg2_url_is_left_alone(self) -> None:
        settings = build_settings(database_url="postgresql+psycopg2://u:p@h:5432/d")
        assert settings.sqlalchemy_url == "postgresql+psycopg2://u:p@h:5432/d"


class TestFootyStatsGate:
    def test_absent_key_reports_not_configured(self) -> None:
        assert build_settings(footystats_api_key="").footystats_configured is False

    def test_whitespace_only_key_reports_not_configured(self) -> None:
        """A stray space in .env must not read as a usable key."""
        assert build_settings(footystats_api_key="   ").footystats_configured is False

    def test_present_key_reports_configured(self) -> None:
        assert build_settings(footystats_api_key="abc123").footystats_configured is True


class TestSecretHandling:
    def test_secrets_are_not_in_safe_summary(self) -> None:
        settings = build_settings(
            footystats_api_key="SUPER_SECRET_KEY", postgres_password="SUPER_SECRET_PW"
        )
        rendered = repr(settings.safe_summary())
        assert "SUPER_SECRET_KEY" not in rendered
        assert "SUPER_SECRET_PW" not in rendered

    def test_secrets_are_masked_in_repr(self) -> None:
        """SecretStr guards against a stray print/log of the settings object."""
        settings = build_settings(
            footystats_api_key="SUPER_SECRET_KEY", postgres_password="SUPER_SECRET_PW"
        )
        assert "SUPER_SECRET_KEY" not in repr(settings)
        assert "SUPER_SECRET_PW" not in repr(settings)
