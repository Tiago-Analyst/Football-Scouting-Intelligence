"""Identity resolution.

The properties worth locking down are the refusals. It is easy to write a
matcher that finds real pairs; the hard part is one that declines to invent
links, because a wrong match silently attaches one player's statistics to
another person's profile and every score built on it inherits the error.
"""

from __future__ import annotations

from datetime import date

import pytest
from pipelines.identity_resolution.evaluate import build_shadow_source, evaluate
from pipelines.identity_resolution.matcher import (
    DEFAULT_THRESHOLD,
    Identity,
    IdentityResolver,
    MatchStatus,
    name_similarity,
    score_pair,
)

from app.schemas.canonical import PositionGroup

DOB = date(2001, 4, 17)


def identity(
    name: str,
    *,
    source_id: str = "x1",
    dob: date | None = DOB,
    nationality: str | None = "Portugal",
    club: str | None = "Example United",
    position: PositionGroup | None = PositionGroup.CM,
    source: str = "demo",
) -> Identity:
    return Identity(
        source=source,
        source_player_id=source_id,
        full_name=name,
        date_of_birth=dob,
        nationality=nationality,
        club_name=club,
        position_group=position,
    )


class TestNameSimilarity:
    def test_identical_names_score_one(self) -> None:
        assert name_similarity(identity("Bruno Ferreira"), identity("Bruno Ferreira")) == 1.0

    def test_accents_are_folded_before_comparison(self) -> None:
        assert name_similarity(identity("Kylian Mbappé"), identity("Kylian Mbappe")) == 1.0

    def test_reordered_names_score_highly(self) -> None:
        """Providers disagree about whether the family name comes first."""
        assert name_similarity(identity("Ferreira Bruno"), identity("Bruno Ferreira")) >= 0.95

    def test_an_initial_matches_the_given_name_it_stands_for(self) -> None:
        """'L. Farrugia' and 'Liam Farrugia' are one player, and this pattern is
        common enough that missing it loses a large share of real matches."""
        assert name_similarity(identity("L. Farrugia"), identity("Liam Farrugia")) >= 0.92

    def test_a_one_character_difference_stays_strong(self) -> None:
        """Transliteration choice, not a different player."""
        assert name_similarity(identity("Vylius Armalas"), identity("Vilius Armalas")) >= 0.92

    def test_dropped_middle_name_stays_strong(self) -> None:
        assert name_similarity(identity("Carlos Silva"), identity("Carlos Eduardo Silva")) >= 0.85

    def test_unrelated_names_score_low(self) -> None:
        assert name_similarity(identity("Bruno Ferreira"), identity("Anders Lindqvist")) < 0.5

    def test_shared_surname_alone_does_not_look_like_a_match(self) -> None:
        """Two different players called Silva must not be near-identical."""
        assert name_similarity(identity("Bruno Silva"), identity("Anderson Silva")) < 0.92


class TestNeverMatchOnNameAlone:
    """Spec section 6. A name is one signal, never sufficient on its own."""

    def test_identical_name_without_a_birth_date_stays_below_threshold(self) -> None:
        confidence, _, _ = score_pair(
            identity("Bruno Ferreira", dob=None), identity("Bruno Ferreira", dob=None)
        )
        assert confidence < DEFAULT_THRESHOLD

    def test_identical_name_with_no_other_evidence_scores_poorly(self) -> None:
        confidence, method, _ = score_pair(
            identity("Bruno Ferreira", dob=None, nationality=None, club=None),
            identity("Bruno Ferreira", dob=None, nationality=None, club=None),
        )
        assert confidence < DEFAULT_THRESHOLD
        assert method == "name_only"

    def test_resolver_refuses_a_name_only_pair(self) -> None:
        target = identity("Bruno Ferreira", source_id="t1", dob=None, source="transfermarkt")
        resolver = IdentityResolver([target])
        result = resolver.resolve(identity("Bruno Ferreira", dob=None))
        assert result.status is not MatchStatus.MATCHED


class TestConfidenceLadder:
    def test_exact_name_and_birth_date_and_club_is_certain(self) -> None:
        confidence, method, _ = score_pair(identity("Bruno Ferreira"), identity("Bruno Ferreira"))
        assert confidence == 1.00
        assert method == "exact_name+dob+club"

    def test_exact_name_and_birth_date_without_club_scores_slightly_lower(self) -> None:
        confidence, method, _ = score_pair(
            identity("Bruno Ferreira", club=None), identity("Bruno Ferreira", club=None)
        )
        assert confidence == 0.95
        assert method == "exact_name+dob"

    def test_birth_date_with_very_strong_name_clears_the_threshold(self) -> None:
        confidence, _, _ = score_pair(identity("L. Farrugia"), identity("Liam Farrugia"))
        assert confidence >= DEFAULT_THRESHOLD

    def test_shared_birth_date_cannot_carry_a_weak_name(self) -> None:
        """Thousands of players share any given birthday, so it cannot rescue a
        name that does not agree."""
        confidence, method, _ = score_pair(identity("Bruno Ferreira"), identity("Anders Lindqvist"))
        assert confidence < DEFAULT_THRESHOLD
        assert method == "dob_only_weak_name"

    def test_conflicting_birth_years_count_against_a_match(self) -> None:
        confidence, method, reasons = score_pair(
            identity("Bruno Ferreira"),
            identity("Bruno Ferreira", dob=date(1994, 4, 17)),
        )
        assert method == "dob_conflict"
        assert confidence < 0.5
        assert "dob=conflicting" in reasons


class TestAmbiguity:
    def test_two_equally_good_candidates_are_reported_not_chosen(self) -> None:
        """Picking the higher of two indistinguishable scores would be
        arbitrary, so the pair goes to manual review instead."""
        targets = [
            identity("Bruno Ferreira", source_id="t1", source="transfermarkt"),
            identity("Bruno Ferreira", source_id="t2", source="transfermarkt"),
        ]
        result = IdentityResolver(targets).resolve(identity("Bruno Ferreira"))
        assert result.status is MatchStatus.AMBIGUOUS
        assert result.target is None
        assert result.runner_up is not None

    def test_a_clear_winner_is_matched(self) -> None:
        targets = [
            identity("Bruno Ferreira", source_id="t1", source="transfermarkt"),
            identity("Anders Lindqvist", source_id="t2", source="transfermarkt"),
        ]
        result = IdentityResolver(targets).resolve(identity("Bruno Ferreira"))
        assert result.status is MatchStatus.MATCHED
        assert result.target is not None
        assert result.target.source_player_id == "t1"


class TestManualOverrides:
    def test_a_confirmed_mapping_wins_over_the_algorithm(self) -> None:
        """A person who has checked a pair must not have it reversed by a later
        automated run."""
        targets = [
            identity("Bruno Ferreira", source_id="t1", source="transfermarkt"),
            identity("Anders Lindqvist", source_id="t2", source="transfermarkt"),
        ]
        resolver = IdentityResolver(targets, manual_overrides={("demo", "x1"): "t2"})
        result = resolver.resolve(identity("Bruno Ferreira"))
        assert result.status is MatchStatus.MANUAL
        assert result.target is not None
        assert result.target.source_player_id == "t2"
        assert result.confidence == 1.0

    def test_an_override_pointing_at_a_missing_player_fails_loudly(self) -> None:
        resolver = IdentityResolver(
            [identity("Bruno Ferreira", source_id="t1", source="transfermarkt")],
            manual_overrides={("demo", "x1"): "does-not-exist"},
        )
        result = resolver.resolve(identity("Bruno Ferreira"))
        assert result.status is MatchStatus.UNMATCHED
        assert "unknown target" in " ".join(result.reasons)


class TestBlocking:
    def test_a_candidate_with_no_shared_signal_is_not_compared(self) -> None:
        target = identity(
            "Anders Lindqvist", source_id="t1", dob=date(1990, 1, 1), source="transfermarkt"
        )
        result = IdentityResolver([target]).resolve(identity("Bruno Ferreira"))
        assert result.status is MatchStatus.UNMATCHED
        assert result.method == "no_candidates"

    def test_blocking_finds_a_candidate_sharing_a_birth_date(self) -> None:
        target = identity("Bruno Ferreira", source_id="t1", source="transfermarkt")
        result = IdentityResolver([target]).resolve(identity("Bruno Ferreira"))
        assert result.target is not None

    def test_blocking_finds_a_candidate_by_surname_when_birth_dates_differ(self) -> None:
        """Same surname and birth year is enough to compare; whether it matches
        is then the scorer's decision."""
        target = identity(
            "Bruno Ferreira", source_id="t1", dob=date(2001, 9, 2), source="transfermarkt"
        )
        result = IdentityResolver([target]).resolve(identity("Bruno Ferreira"))
        assert result.method != "no_candidates"


class TestEvaluationHarness:
    def test_shadow_records_carry_their_ground_truth(self) -> None:
        targets = [
            identity(f"Player {i}", source_id=f"t{i}", dob=date(1998, 1, 1 + i % 28))
            for i in range(50)
        ]
        shadows, truth = build_shadow_source(targets, sample=50)
        assert len(shadows) == 50
        assert set(truth.values()) <= {t.source_player_id for t in targets}

    def test_precision_is_one_when_nothing_was_matched(self) -> None:
        """Refusing every pair is not a precision failure, and the metric must
        not report it as one."""
        evaluation = evaluate([], {})
        assert evaluation.precision == 1.0
        assert evaluation.recall == 0.0


@pytest.mark.snapshot
class TestAgainstRealData:
    """Needs the Transfermarkt snapshot; skipped in CI."""

    def test_invented_names_produce_no_matches(self) -> None:
        """The mock players do not exist. Every match here would be fabricated."""
        from pipelines.identity_resolution.run import mock_identities, transfermarkt_identities

        from app.providers.mock import MockPerformanceProvider
        from app.providers.transfermarkt import TransfermarktDatasetProvider

        targets = transfermarkt_identities(TransfermarktDatasetProvider())
        sources = mock_identities(MockPerformanceProvider())[:400]
        results = IdentityResolver(targets).resolve_all(sources)
        assert [r for r in results if r.status is MatchStatus.MATCHED] == []

    def test_precision_against_known_truth_is_perfect(self) -> None:
        from pipelines.identity_resolution.evaluate import evaluate_against_shadow
        from pipelines.identity_resolution.run import transfermarkt_identities

        from app.providers.transfermarkt import TransfermarktDatasetProvider

        targets = transfermarkt_identities(TransfermarktDatasetProvider())
        evaluation, _, _ = evaluate_against_shadow(targets, sample=500)
        assert evaluation.incorrect == 0
        assert evaluation.recall > 0.70
