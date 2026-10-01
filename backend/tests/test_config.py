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


class TestThePoolerCannotBeSentStartupParameters:
    """This took production down for the length of one deploy.

    The search path was sent as the libpq startup parameter `options`, which
    is right for a direct connection and impossible through PgBouncer: in
    transaction pooling mode it refuses every startup parameter outside a
    small allowlist, and `options` is not on it. `render.yaml` tells the
    operator to use Neon's pooled endpoint, so every connection was rejected
    at once - a fast 503 rather than a timeout, which is what gave it away.
    """

    @pytest.mark.parametrize(
        "host",
        [
            "ep-cool-name-123456-pooler.eu-central-1.aws.neon.tech",
            "aws-0-eu-west-2.pooler.supabase.com",
            "pgbouncer.internal:6432",
        ],
    )
    def test_a_pooled_url_sends_no_startup_options(self, host: str) -> None:
        from app.core.database import is_pooled

        assert is_pooled(f"postgresql+psycopg://u:p@{host}/db") is True

    @pytest.mark.parametrize(
        "host",
        [
            "ep-cool-name-123456.eu-central-1.aws.neon.tech",
            "localhost:5432",
            "db.example.com",
        ],
    )
    def test_a_direct_url_still_sends_them(self, host: str) -> None:
        from app.core.database import is_pooled

        assert is_pooled(f"postgresql+psycopg://u:p@{host}/db") is False

    def test_no_startup_option_is_built_for_a_pooled_url(self) -> None:
        """Asserted on what `create_engine` is handed: the whole outage was
        one argument reaching a server that will not take it."""
        from app.core.database import search_path_args

        settings = build_settings(
            database_url="postgresql+psycopg://u:p@ep-x-pooler.eu.aws.neon.tech/db"
        )
        assert search_path_args(settings) == {}

    def test_and_one_is_built_for_a_direct_url(self) -> None:
        from app.core.database import search_path_args

        settings = build_settings(database_url="postgresql+psycopg://u:p@ep-x.eu.aws.neon.tech/db")
        assert "search_path" in search_path_args(settings)["options"]

    def test_the_direct_endpoint_is_derived_from_the_pooled_one(self) -> None:
        """Neon names the two endpoints for one database `ep-x-pooler.<region>`
        and `ep-x.<region>`. Migrations need the second, and the second is the
        first with four characters removed."""
        from app.core.database import direct_url, is_pooled

        pooled = "postgresql+psycopg://u:p@ep-x-pooler.c-6.eu-central-1.aws.neon.tech/db"
        direct = direct_url(pooled)

        assert direct == "postgresql+psycopg://u:p@ep-x.c-6.eu-central-1.aws.neon.tech/db"
        assert is_pooled(direct) is False

    def test_a_password_is_not_mistaken_for_a_host(self) -> None:
        """The text being removed is four characters a password may contain,
        and a mangled password fails in a way that reads like a wrong one."""
        from app.core.database import direct_url

        url = "postgresql+psycopg://u:a-pooler.b@ep-x-pooler.eu.aws.neon.tech/db"
        assert direct_url(url) == "postgresql+psycopg://u:a-pooler.b@ep-x.eu.aws.neon.tech/db"

    def test_a_url_that_needs_no_change_is_returned_as_it_is(self) -> None:
        from app.core.database import direct_url

        for url in (
            "postgresql+psycopg://u:p@localhost:5432/db",
            "postgresql+psycopg://u:p@ep-x.eu.aws.neon.tech/db",
        ):
            assert direct_url(url) == url

    def test_migrations_choose_the_direct_endpoint(self) -> None:
        """Alembic pins `search_path=public` with a startup parameter, which is
        exactly what a pooler refuses. It connects directly instead, and
        `MIGRATION_DATABASE_URL` overrides the derivation for a provider whose
        direct host cannot be guessed."""
        from pathlib import Path

        # Read rather than imported: importing `env.py` runs the migrations.
        source = (Path(__file__).resolve().parents[1] / "alembic" / "env.py").read_text(
            encoding="utf-8"
        )

        assert "def migration_url()" in source
        assert "migration_database_url" in source
        assert "direct_url(" in source
        # And it refuses rather than migrating through a pooler with no pin,
        # which would create operational tables in the schema promotions swap.
        assert "is_pooled(url)" in source
        assert "RuntimeError" in source
