"""Configuration measured against what the provider actually supplies.

The caveats on affected roles were written by hand, one definition at a time,
after `successful_tackles` turned out to be declared and never populated.
Hand-written caveats go stale the moment a provider changes, and the staleness
is invisible: the label still reads the same.

So the comparison is now measured, and these hold it - in particular the rule
that a score produced from fewer components than it declares must say so where
somebody will read it.
"""

from __future__ import annotations

from pipelines.quality.config_availability import (
    OUTPUT,
    Line,
    main,
    measure,
    supplied_metrics,
)


def line(available: float, missing: list[str], min_coverage: float) -> Line:
    return Line(
        key="k",
        label="A definition",
        configured_weight=100.0,
        available_weight=available,
        missing=missing,
        min_coverage=min_coverage,
    )


class TestStatus:
    def test_everything_available_is_ok(self) -> None:
        assert line(100.0, [], 1.0).status == "OK"

    def test_a_survivable_gap_is_reduced(self) -> None:
        """The definition documents what it can do without, so it carries on -
        renormalised over the rest, never filled in with a zero."""
        assert line(80.0, ["a"], 0.75).status == "REDUCED"

    def test_too_little_left_is_disabled(self) -> None:
        assert line(60.0, ["a"], 0.75).status == "DISABLED"

    def test_the_boundary_belongs_to_reduced(self) -> None:
        assert line(75.0, ["a"], 0.75).status == "REDUCED"

    def test_nothing_configured_is_not_a_pass(self) -> None:
        empty = Line("k", "l", 0.0, 0.0, ["a"], 1.0)
        assert empty.coverage == 0.0
        assert empty.status == "DISABLED"


class TestAgainstTheRealConfiguration:
    def test_the_document_is_current(self) -> None:
        assert main(["--check"]) == 0, (
            "docs/config_availability.md is stale, or a reduced role has no caveat. "
            "Run: python -m pipelines.quality.config_availability"
        )

    def test_the_three_known_absences_are_found(self) -> None:
        """Measured from the mapping, not asserted from memory."""
        _, _, _, absent = measure()
        assert set(absent) == {"progressive_passes", "aerial_duels", "successful_tackles"}

    def test_the_mapping_grants_only_canonical_names(self) -> None:
        from app.schemas.canonical import CanonicalMetric

        assert supplied_metrics() <= {m.value for m in CanonicalMetric}

    def test_a_role_producing_a_partial_score_carries_a_caveat(self) -> None:
        """The rule that matters. A number built from 80% of its definition,
        shown under an unchanged label, is the quiet failure this prevents."""
        from app.analytics.roles import get_roles

        roles, _, _, _ = measure()
        caveats = {r.key: r.caveat for r in get_roles().values()}
        for entry in roles:
            if entry.status == "REDUCED":
                assert caveats.get(entry.key), entry.key

    def test_a_disabled_definition_produces_nothing_rather_than_a_low_score(self) -> None:
        """`min_coverage` is what enforces it; this checks the arithmetic agrees.

        A disabled definition must not be reachable as a poor score, because a
        poor score reads as a judgement about the player rather than an absence
        in the data.
        """
        roles, scores, _, _ = measure()
        for entry in roles + scores:
            if entry.status == "DISABLED":
                assert entry.coverage < entry.min_coverage

    def test_similarity_vectors_are_never_disabled(self) -> None:
        """A vector drops what is missing and reports the coverage instead.

        Disabling it would remove the player from similarity entirely, which is
        the opposite of the product decision that everyone stays comparable.
        """
        _, _, vectors, _ = measure()
        assert vectors
        for vector in vectors:
            assert vector.status != "DISABLED"

    def test_the_written_report_names_what_is_switched_off(self) -> None:
        roles, scores, _, _ = measure()
        text = OUTPUT.read_text(encoding="utf-8")
        for entry in roles + scores:
            if entry.status == "DISABLED":
                assert entry.label in text
