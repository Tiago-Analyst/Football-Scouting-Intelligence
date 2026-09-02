"""Club names as evidence, and how little a shared word proves.

Club agreement feeds a confidence score that decides whether two provider
records describe one person. It used to return true on *any* shared token,
under a comment claiming to check for a distinctive one:

    Manchester United / Manchester City   shared "manchester"  -> same club
    Sporting CP       / Sporting Braga    shared "sporting"    -> same club
    Real Madrid       / Real Sociedad     shared "real"        -> same club

So a coincidence of city, or a word half a league shares, was counted as
evidence of identity. These pin the three answers that replaced it, and in
particular the middle one: `None` for evidence that settles nothing.
"""

from __future__ import annotations

import pytest
from pipelines.identity_resolution.matcher import (
    CULTURE_GENERIC_TOKENS,
    Identity,
    _same_club,
    club_tokens,
)


def agree(left: str | None, right: str | None) -> bool | None:
    return _same_club(
        Identity(source="footystats", source_player_id="1", full_name="A Player", club_name=left),
        Identity(
            source="transfermarkt", source_player_id="2", full_name="A Player", club_name=right
        ),
    )


class TestTheNamedAmbiguities:
    """Every pair the brief called out, plus the ones they generalise to.

    None of these may return True. Whether they return False or None is a
    judgement about how much the difference proves; that a shared city or a
    shared culture-word is not agreement is not a judgement at all.
    """

    @pytest.mark.parametrize(
        ("left", "right"),
        [
            ("Manchester United", "Manchester City"),
            ("Sporting CP", "Sporting Braga"),
            ("Sporting Lisbon", "Sporting Gijon"),
            ("Real Madrid", "Real Sociedad"),
            ("Real Betis", "Real Valladolid"),
            ("Athletic Club", "Atletico Madrid"),
            ("Atletico Madrid", "Athletic Bilbao"),
            ("Racing Santander", "Racing Genk"),
            ("Dynamo Kyiv", "Dynamo Moscow"),
            ("Olympique Lyonnais", "Olympique Marseille"),
            ("Borussia Dortmund", "Borussia Monchengladbach"),
            ("Newcastle United", "Newcastle Jets"),
        ],
    )
    def test_a_shared_generic_word_is_not_agreement(self, left: str, right: str) -> None:
        assert agree(left, right) is not True, f"{left} and {right} are different clubs"

    def test_the_city_is_not_the_club(self) -> None:
        """Sharing a city is genuinely ambiguous rather than a disagreement.

        `None` lets name, date of birth and nationality decide, instead of
        putting a thumb on either side of the scale.
        """
        assert agree("Manchester United", "Manchester City") is None
        # Milan and Internazionale share a city and not a single token, so this
        # one lands on a flat disagreement rather than ambiguity. Both answers
        # are correct here; what matters is that neither is True.
        assert agree("Milan", "Internazionale Milano") is not True


class TestWhatStillAgrees:
    """Hardening that lost the true matches would be a worse trade."""

    def test_a_corporate_suffix_changes_nothing(self) -> None:
        assert agree("Nottingham Forest", "Nottingham Forest FC") is True
        assert agree("FC Barcelona", "Barcelona") is True
        assert agree("Liverpool", "Liverpool FC") is True

    def test_common_abbreviations_are_expanded(self) -> None:
        assert agree("Manchester United", "Man Utd FC") is True
        assert agree("Tottenham Hotspur", "Spurs Hotspur") is True

    def test_a_shorter_name_inside_a_longer_one_agrees(self) -> None:
        """`SL Benfica` is `Sport Lisboa e Benfica` written shorter.

        What makes it safe is that `benfica` identifies a club. `Sporting CP`
        sits inside `Sporting Braga` the same way and is a different club,
        because `sporting` identifies a country's habits instead.
        """
        assert agree("SL Benfica", "Sport Lisboa e Benfica") is True
        assert agree("Sporting CP", "Sporting Braga") is not True

    def test_identical_names_agree(self) -> None:
        assert agree("Ajax", "Ajax") is True
        assert agree("Bayern München", "Bayern Munchen") is True


class TestRealDisagreement:
    def test_unrelated_clubs_disagree(self) -> None:
        assert agree("Liverpool FC", "Everton FC") is False
        assert agree("Ajax", "PSV Eindhoven") is False

    def test_a_missing_club_is_not_a_disagreement(self) -> None:
        """Or every player without club data is penalised for the gap."""
        assert agree(None, "Ajax") is None
        assert agree("Ajax", None) is None
        assert agree("", "Ajax") is None

    def test_a_name_of_nothing_but_structure_claims_nothing(self) -> None:
        assert agree("FC", "Ajax") is None
        assert agree("CD", "SC") is None


class TestTokens:
    def test_structural_words_are_dropped(self) -> None:
        """`e`, `de`, `la`, `club` and the corporate initials go.

        `sport` and `real` stay: they are culture-generic rather than
        structural, which means they are kept as tokens and simply not trusted
        on their own.
        """
        assert club_tokens("Sport Lisboa e Benfica") == frozenset({"sport", "lisboa", "benfica"})
        assert club_tokens("Real Club Deportivo de La Coruña") == frozenset(
            {"real", "deportivo", "coruna"}
        )

    def test_discriminating_words_are_kept(self) -> None:
        """`united` and `city` are common, and they are also the entire
        difference between two Manchester clubs."""
        assert "united" in club_tokens("Manchester United")
        assert "city" in club_tokens("Manchester City")

    def test_culture_words_are_kept_but_not_trusted_alone(self) -> None:
        assert "sporting" in club_tokens("Sporting CP")
        assert "sporting" in CULTURE_GENERIC_TOKENS

    def test_short_fragments_are_ignored(self) -> None:
        """Two-letter remnants match too much to be evidence of anything."""
        assert club_tokens("AC AS SS Roma") == frozenset({"roma"})
