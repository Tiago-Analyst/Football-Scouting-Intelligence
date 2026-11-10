"""A deploy that ships a migration must apply it before it serves.

WHAT HAPPENED

10 November 2026, 15:25 to 15:59 UTC: every sign-in in production answered
`503 database_unavailable`. The deploy had shipped code whose first act on
`/api/v1/auth/login` is to read `login_attempt` - the sign-in throttle's
counter - and that table did not exist, because nothing in a deploy applied
the migration.

The only `alembic upgrade head` that reached production lived inside the data
pipeline. So the code arrived on merge and the schema arrived whenever the
pipeline next ran, which is a schedule GitHub delivers a fraction of. Thirty
minutes of readings confirmed it: the revision never moved from `0015` while
the process served `0016`'s code.

It had never shown before because no previous deploy had carried a migration.
The window was open at every one of them, and the first migration to go
through it took sign-in down.

WHY A TEST AND NOT ONLY A COMMENT

Because the fix is one line in a file nobody reads on the way past, and the
failure it prevents is invisible until a migration exists AND somebody tries
to sign in. `render.yaml` is the only place that can carry it, so this asserts
that it still does - and says why, so that removing it is a decision rather
than a tidy-up.

WHAT THIS CANNOT CHECK

That Render honours the key, that the plan supports a pre-deploy command, or
that the command succeeded on the last deploy. Those are facts about the
platform and about one deploy; this is a fact about the configuration. The
observable proof is the schema revision in `/health` moving in step with a
deploy rather than hours later.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

RENDER_YAML = Path(__file__).resolve().parents[2] / "render.yaml"


@pytest.fixture(scope="module")
def service() -> dict:
    parsed = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
    services = parsed["services"]
    assert len(services) == 1, "this file assumes one service; teach it the others"
    return services[0]


class TestTheDeployMigratesFirst:
    def test_a_pre_deploy_command_exists(self, service: dict) -> None:
        command = service.get("preDeployCommand")
        assert command, (
            "render.yaml declares no preDeployCommand, so a deploy carrying a "
            "migration will serve code against the old schema - which took "
            "sign-in down on 10 November"
        )

    def test_it_runs_the_migrations(self, service: dict) -> None:
        command = service["preDeployCommand"]
        assert "alembic" in command and "upgrade" in command, (
            f"the pre-deploy command does not migrate: {command!r}"
        )

    def test_it_upgrades_to_head_rather_than_a_fixed_revision(self, service: dict) -> None:
        """A pinned revision would silently stop applying new migrations.

        The whole defect was a schema that lagged the code. Naming a revision
        here would reproduce it the first time somebody added one and forgot
        this line.
        """
        assert "head" in service["preDeployCommand"]

    def test_the_build_filter_still_covers_migrations(self, service: dict) -> None:
        """A migration must trigger a deploy at all.

        `buildFilter` stops a frontend commit restarting the API. A migration
        lives under `backend/`, so it is covered - but if that path were ever
        narrowed, a migration-only commit would deploy nothing and the
        pre-deploy command above would never run.
        """
        paths = service["buildFilter"]["paths"]
        assert any(p.startswith("backend/") for p in paths), (
            f"no backend path in buildFilter, so a migration may not deploy: {paths}"
        )

    def test_the_health_check_does_not_depend_on_the_schema(self, service: dict) -> None:
        """Why the outage was invisible to everything watching.

        `/health/live` performs no I/O, which is right for a restart decision -
        a database outage must not make Render kill a healthy process. The
        consequence, stated here because it cost thirty-four minutes: this
        probe answers 200 while sign-in is failing, and `/health` answered
        `ok` with `postgresql: ok` throughout, because neither exercises a
        query against the missing table.

        Nothing in this repository would have noticed. A check that asks
        `/api/v1/auth/login` for a 401 would.
        """
        assert service["healthCheckPath"] == "/health/live"
