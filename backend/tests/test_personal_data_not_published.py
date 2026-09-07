"""Row-level identity-resolution output must not reach the repository.

WHAT HAPPENED

`docs/identity_resolution_footystats.csv` was committed to a public repository
and stayed there. It is 8,575 rows, one per player in the provider's universe,
each carrying a real person's name, date of birth and nationality. That it is
derived from a provider's data does not make it less personal, and `docs/` is
not a place where files go unnoticed - it is the place a reader looks first.

The resolver now writes it to `data/processed/`, which is git-ignored. These
tests are the part that keeps it there: a path is easy to change back, and the
failure is silent until somebody reads a diff carefully.

WHAT IS DELIBERATELY STILL PUBLISHED

The aggregate report - matched, ambiguous, unmatched, and their shares - which
is the part that documents how well resolution works and names nobody. And a
six-row example with invented players, so the columns can be explained without
handing over the population.
"""

from __future__ import annotations

import csv
import pathlib
import shutil
import subprocess

import pytest

#: Resolved from PATH once. `subprocess` with a bare "git" is flagged because a
#: partial path can be hijacked; this answers that rather than silencing it.
GIT = shutil.which("git")

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DOCS = REPO_ROOT / "docs"
EXAMPLE = DOCS / "identity_resolution_example.csv"

#: Columns that make a row personal data rather than a statistic.
IDENTIFYING = {"footystats_name", "date_of_birth", "nationality", "matched_name"}


def tracked_files() -> list[str]:
    if GIT is None:
        pytest.skip("git is not available")
    # Every argument is a literal and GIT came from PATH, so there is no
    # untrusted input for the rule below to be protecting against.
    result = subprocess.run(  # noqa: S603
        [GIT, "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("not a git checkout")
    return result.stdout.splitlines()


class TestTheRealMappingIsNotTracked:
    def test_the_row_level_csv_is_not_in_the_repository(self) -> None:
        offenders = [
            path
            for path in tracked_files()
            if path.startswith("docs/identity_resolution")
            and path.endswith(".csv")
            and not path.endswith("_example.csv")
        ]
        assert offenders == [], offenders

    def test_git_refuses_the_old_path(self) -> None:
        """`.gitignore`, not merely `git rm`. Removing it once is not a rule."""
        if GIT is None:
            pytest.skip("git is not available")
        result = subprocess.run(  # noqa: S603 - literal arguments only
            [GIT, "check-ignore", "-q", "docs/identity_resolution_footystats.csv"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, (
            "the old path is not ignored, so regenerating the report would re-publish 8,575 people"
        )

    def test_the_example_is_still_allowed(self) -> None:
        """An ignore rule broad enough to catch everything catches too much."""
        if GIT is None:
            pytest.skip("git is not available")
        result = subprocess.run(  # noqa: S603 - literal arguments only
            [GIT, "check-ignore", "-q", "docs/identity_resolution_example.csv"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=False,
        )
        assert result.returncode != 0, "the synthetic example is being ignored too"

    def test_the_resolver_writes_outside_docs(self) -> None:
        source = (REPO_ROOT / "pipelines" / "identity_resolution" / "resolve.py").read_text(
            encoding="utf-8"
        )
        assert 'PROCESSED_DIR / "identity_resolution_footystats.csv"' in source
        assert 'DOCS_DIR / "identity_resolution_footystats.csv"' not in source


class TestWhatIsPublishedInstead:
    def test_the_example_exists_and_is_small(self) -> None:
        assert EXAMPLE.exists()
        rows = EXAMPLE.read_text(encoding="utf-8").strip().splitlines()
        assert 2 <= len(rows) <= 25, "an 'example' this size is a dataset"

    def test_the_example_carries_no_real_provider_ids(self) -> None:
        """Synthetic ids, so nobody can join it back to a real player."""
        with EXAMPLE.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        assert rows
        for row in rows:
            assert row["footystats_id"].startswith("9000"), row["footystats_id"]

    def test_the_example_shows_every_outcome(self) -> None:
        """Otherwise it documents the columns and not the report."""
        with EXAMPLE.open(encoding="utf-8") as handle:
            statuses = {row["status"] for row in csv.DictReader(handle)}
        assert {"matched", "unmatched", "ambiguous"} <= statuses

    def test_the_published_report_names_nobody(self) -> None:
        """Aggregates are the publishable part, and must stay aggregates."""
        report = DOCS / "identity_resolution_footystats.md"
        if not report.exists():
            pytest.skip("the aggregate report has not been generated here")
        text = report.read_text(encoding="utf-8")

        # Prose is allowed to say the word "nationality" - the report explains
        # that resolution uses it as a signal. What must not appear is the
        # CSV's own header, which is what a row-level dump brings with it.
        assert "footystats_id,footystats_name" not in text

        # And the report should stay short. Eight thousand rows of anything
        # cannot hide in a page of counts.
        assert len(text.splitlines()) < 200, "this is no longer an aggregate report"


class TestNoOtherTrackedFileCarriesThePopulation:
    def test_no_tracked_csv_has_identifying_columns_at_scale(self) -> None:
        """The general rule, rather than one file's name.

        A CSV naming people is fine at six rows and is a disclosure at eight
        thousand. The line is drawn at size because that is what separates an
        example from a dataset.
        """
        offenders = []
        for path in tracked_files():
            if not path.endswith(".csv"):
                continue
            full = REPO_ROOT / path
            if not full.exists():
                continue
            try:
                lines = full.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            if not lines:
                continue
            header = {c.strip() for c in lines[0].split(",")}
            if IDENTIFYING & header and len(lines) > 25:
                offenders.append(f"{path}: {len(lines) - 1} rows")
        assert offenders == [], offenders
