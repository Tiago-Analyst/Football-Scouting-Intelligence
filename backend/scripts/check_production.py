"""Check a production configuration before it goes live.

Run against the environment you are about to deploy with:

    APP_ENV=production APP_MODE=production python -m scripts.check_production

Exit code 1 if anything would be unsafe, so it can gate a deployment.

Why this exists: the production posture is currently a set of `if
settings.is_production` branches spread across the codebase — docs disabled
here, secure cookies there, error detail hidden somewhere else. Each is correct
and none of them is *checkable* from outside. A deployment configured with
`APP_ENV=development` by accident would look completely normal and quietly serve
interactive API docs, permissive CORS and stack traces.

So this asserts the posture from the outside, using the same `Settings` object
the application will use. It reads configuration only — it opens no connection,
sends no request, and can be run safely against production credentials.

Nothing here duplicates a decision made elsewhere. Where the application decides
something from `is_production`, this checks that the decision came out right.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from urllib.parse import urlparse

REPO_ROOT_MARKER = "pyproject.toml"

#: Passwords that must never reach production. `postgres` is the default a
#: stock install ships with, and finding it in production is the single most
#: common database compromise there is.
WEAK_PASSWORDS = frozenset(
    {"postgres", "password", "changeme", "admin", "root", "secret", "fri", "test"}
)

MIN_PASSWORD_LENGTH = 16


@dataclass(frozen=True)
class Finding:
    """One thing that is wrong, or worth knowing."""

    check: str
    severity: str  # "fail" or "warn"
    detail: str

    @property
    def failed(self) -> bool:
        return self.severity == "fail"


def check_environment(settings: object) -> list[Finding]:
    """The flags that switch the whole posture."""
    findings: list[Finding] = []

    if not getattr(settings, "is_production", False):
        findings.append(
            Finding(
                "app_env",
                "fail",
                f"APP_ENV is '{settings.app_env.value}', not 'production'. Every "  # type: ignore[attr-defined]
                "production protection is gated on this: API docs, error detail, "
                "secure cookies and HSTS all stay in their development state.",
            )
        )

    if getattr(settings, "debug", False):
        findings.append(
            Finding(
                "debug",
                "fail",
                "DEBUG is on. Production hides error detail regardless, but a "
                "deployment with DEBUG set is not the configuration that was tested.",
            )
        )

    return findings


def check_cors(settings: object) -> list[Finding]:
    """Who may call the API from a browser."""
    origins: list[str] = list(getattr(settings, "cors_allow_origins", []))
    findings: list[Finding] = []

    if not origins:
        findings.append(
            Finding(
                "cors", "fail", "No CORS origin is configured; the frontend cannot call the API."
            )
        )
        return findings

    if "*" in origins:
        # Settings already rejects this, so reaching here means something
        # bypassed it. Reported rather than assumed impossible.
        findings.append(Finding("cors", "fail", "CORS allows '*' with credentials enabled."))

    for origin in origins:
        parsed = urlparse(origin)
        host = (parsed.hostname or "").lower()
        if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:  # noqa: S104
            findings.append(
                Finding("cors", "fail", f"CORS allows a local origin in production: {origin}")
            )
        elif parsed.scheme != "https":
            findings.append(
                Finding(
                    "cors",
                    "fail",
                    f"CORS allows a non-HTTPS origin: {origin}. The session cookie is "
                    "marked Secure in production and would never be sent to it.",
                )
            )

    return findings


def check_database(settings: object) -> list[Finding]:
    """Credentials and host. Never prints the password."""
    findings: list[Finding] = []

    password = settings.postgres_password.get_secret_value()  # type: ignore[attr-defined]
    host = str(getattr(settings, "postgres_host", "")).lower()
    user = str(getattr(settings, "postgres_user", ""))

    if not password:
        findings.append(Finding("database", "fail", "No database password is set."))
    elif password.lower() in WEAK_PASSWORDS:
        findings.append(
            Finding(
                "database",
                "fail",
                "The database password is a well-known default. This is the most "
                "common way a database is compromised.",
            )
        )
    elif len(password) < MIN_PASSWORD_LENGTH:
        findings.append(
            Finding(
                "database",
                "warn",
                f"The database password is under {MIN_PASSWORD_LENGTH} characters.",
            )
        )

    if host in {"localhost", "127.0.0.1"}:
        findings.append(
            Finding(
                "database",
                "warn",
                f"The database host is {host}. Correct if the database runs beside "
                "the API; wrong if a managed database was intended.",
            )
        )

    if user in {"postgres", "root", "admin"}:
        findings.append(
            Finding(
                "database",
                "fail",
                f"Connecting as '{user}', a superuser account. The application "
                "needs only its own schema, and a superuser connection turns any "
                "SQL injection into a full database compromise.",
            )
        )

    return findings


def check_providers(settings: object) -> list[Finding]:
    """What the deployment will actually be able to serve."""
    findings: list[Finding] = []

    mode = settings.app_mode.value  # type: ignore[attr-defined]
    configured = bool(getattr(settings, "footystats_configured", False))

    if mode == "demo":
        findings.append(
            Finding(
                "app_mode",
                "warn",
                "APP_MODE is 'demo'. The deployment will serve fabricated player "
                "data, labelled as such. Intended for a public preview; wrong for "
                "anything else.",
            )
        )
    elif not configured:
        findings.append(
            Finding(
                "app_mode",
                "fail",
                "APP_MODE is 'production' but no FootyStats key is set. The "
                "provider registry will refuse to build and the API will serve "
                "nothing.",
            )
        )

    return findings


def check_secrets_are_not_committed() -> list[Finding]:
    """A tracked .env is how a key reaches a public repository."""
    import subprocess

    try:
        tracked = subprocess.run(
            ["git", "ls-files", ".env", "*/.env", "**/.env"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return [Finding("secrets", "warn", "Could not check whether .env is tracked by git.")]

    if tracked:
        return [
            Finding(
                "secrets",
                "fail",
                f"These files are tracked by git and may contain credentials: {tracked}",
            )
        ]
    return []


def run() -> list[Finding]:
    from app.core.config import get_settings

    settings = get_settings()
    return [
        *check_environment(settings),
        *check_cors(settings),
        *check_database(settings),
        *check_providers(settings),
        *check_secrets_are_not_committed(),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as failures.",
    )
    args = parser.parse_args(argv)

    findings = run()

    if not findings:
        print("Production configuration looks sound.")
        return 0

    width = max(len(f.check) for f in findings)
    for finding in findings:
        marker = "FAIL" if finding.failed else "warn"
        print(f"{marker}  {finding.check:<{width}}  {finding.detail}")

    failures = [f for f in findings if f.failed]
    warnings = [f for f in findings if not f.failed]
    print(f"\n{len(failures)} failing, {len(warnings)} warning.")

    if failures:
        print("\nDo not deploy this configuration.")
        return 1
    if warnings and args.strict:
        print("\n--strict: treating warnings as failures.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
