"""Role documentation must not describe a configuration that does not exist.

An analysis document listing each role's metrics was written by hand and got
eleven of fifteen roles wrong - metrics that are not in the role, metrics that
are and were omitted - and it was written to be reviewed and decided on. A
document that misdescribes the thing it is arguing about is worse than no
document, because it reads as evidence.

These are diagnostics, not gates on behaviour. They fail when prose and
configuration disagree, which is the only way that disagreement gets noticed.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from app.analytics.roles import get_roles

DOCS = pathlib.Path(__file__).resolve().parents[2] / "docs"
ANALYSIS = DOCS / "role_validity_analysis.md"
SUPERSEDED = DOCS / "role_core_components.md"

#: Metric names carry digits (`tackles_per90`), and a pattern of `[a-z_]+`
#: silently skips almost all of them. That exact mistake made a survey of
#: partially-supplied metrics report that only one existed.
METRIC_IN_PROSE = re.compile(r"`([a-z_][a-z_0-9]*)`")


def configured_metrics() -> set[str]:
    names: set[str] = set()
    for role in get_roles().values():
        names |= {m.value for m in role.metric_weights}
    return names


class TestTheAnalysisDescribesRealMetrics:
    def test_the_document_exists(self) -> None:
        assert ANALYSIS.exists(), "the analysis under review must be in the repository"

    def test_every_metric_it_names_is_one_a_role_uses(self) -> None:
        """Catches a metric invented or misremembered in prose.

        Allows names that exist in the product but are not in any role - the
        document discusses unavailable ones like `tackle_success_percentage`
        on purpose - by checking against the canonical vocabulary.
        """
        from app.analytics.metrics import DerivedMetric

        known = {m.value for m in DerivedMetric}
        named = set(METRIC_IN_PROSE.findall(ANALYSIS.read_text(encoding="utf-8")))
        # Prose also backticks ordinary words and file names; only judge the
        # ones that look like metrics, i.e. already in the vocabulary shape.
        suspects = {n for n in named if n.endswith(("_per90", "_percentage", "_completion"))}
        unknown = sorted(suspects - known)
        assert unknown == [], f"the analysis names metrics that do not exist: {unknown}"

    def test_it_does_not_claim_a_metric_belongs_to_a_role_it_is_absent_from(self) -> None:
        """The specific failure of the superseded draft.

        Checked per role section: a metric named inside a role's own block
        must be one that role actually weights, or be explicitly discussed as
        absent.
        """
        text = ANALYSIS.read_text(encoding="utf-8")
        for role in get_roles().values():
            heading = f"### {role.label}"
            if heading not in text:
                continue
            start = text.index(heading)
            nxt = text.find("\n### ", start + 1)
            block = text[start : nxt if nxt > -1 else len(text)]
            weighted = {m.value for m in role.metric_weights}
            named = {
                n
                for n in METRIC_IN_PROSE.findall(block)
                if n.endswith(("_per90", "_percentage", "_completion"))
            }
            stray = sorted(named - weighted)
            assert stray == [], f"{role.label} block names metrics it does not weight: {stray}"


class TestTheSupersededDraftStaysMarked:
    def test_it_warns_before_it_is_read(self) -> None:
        """It is kept so the correction has something to point at.

        Deleting it would erase the record of what was got wrong; leaving it
        unmarked would let somebody act on it.
        """
        if not SUPERSEDED.exists():
            pytest.skip("the superseded draft has been removed")
        first = SUPERSEDED.read_text(encoding="utf-8").lstrip().splitlines()[0]
        assert "SUPERSEDED" in first.upper(), "the superseded draft must say so on its first line"
