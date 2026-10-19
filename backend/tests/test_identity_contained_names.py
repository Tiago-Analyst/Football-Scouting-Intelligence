"""One name being the other with surnames dropped.

WHERE THESE PAIRS COME FROM

Every pair below was taken from a real resolution of 8,575 FootyStats players
against 50,149 from Transfermarkt. The refused ones were refused; the ones this
rule is meant to recover were among 732 identical in shape, a quarter of every
refusal that had an exact date of birth to go on.

Transfermarkt keeps a Hispanic or Lusophone player under a given name and first
surname and FootyStats keeps the full registered name, so "Ramon Sosa" and
"Ramon Sosa Acosta" are one footballer. `name_similarity` claims this ground in
its docstring and cannot reach it: its coverage term charges a fixed share per
dropped surname, and those 732 scored 0.60 to 0.77 against a band starting at
0.85.

WHY NOT SIMPLY LOWER THE BAND

Because a different population sits at the same scores. Sharing a surname and a
birthday with a DIFFERENT given name also scores about 0.75, and some of those
are two people. Merging one would attach one footballer's statistics to
another's profile - the failure this module exists to avoid and the one nothing
downstream can detect. `TestNamesThatMustStayRefused` is the half of this file
that matters most.
"""

from __future__ import annotations

import datetime as dt

import pytest
from pipelines.identity_resolution.matcher import (
    DEFAULT_MARGIN,
    DEFAULT_THRESHOLD,
    STRONG_NAME,
    Identity,
    IdentityResolver,
    MatchStatus,
    _name_contained,
    name_similarity,
    score_pair,
)

BIRTHDAY = dt.date(1999, 8, 31)

#: Observed pairs that share a birthday and are two different footballers.
#: Each scores around 0.75 - the same band as the containments above.
DIFFERENT_PEOPLE = [
    ("Timothy Dieng", "Seny Dieng"),
    ("Jacob Stensson", "Daniel Stensson"),
    ("Andrea Hristov", "Petko Hristov"),
    ("Juan Jose Mina Gonzalez", "Inaki Gonzalez"),
    ("Jose Manuel Velazquez", "Sema Velazquez"),
]


def identity(
    name: str,
    *,
    dob: dt.date | None = BIRTHDAY,
    nationality: str | None = "Paraguay",
    club: str | None = None,
) -> Identity:
    return Identity(
        source="x",
        source_player_id=name,
        full_name=name,
        date_of_birth=dob,
        nationality=nationality,
        club_name=club,
    )


#: Observed pairs where the two names are one footballer. Full registered name
#: first, as FootyStats carries it; the shorter form second.
SAME_PERSON = [
    ("Ramon Sosa Acosta", "Ramon Sosa"),
    ("Guilherme Castilho Carvalho", "Guilherme Castilho"),
    ("Guilherme Neiva Silva", "Guilherme Neiva"),
    ("Gorka Carrera Zarranz", "Gorka Carrera"),
    ("Ignacio Sosa Ospital", "Ignacio Sosa"),
    ("Alexis Serna Romana", "Alexis Serna"),
    ("Andres Alarcon Mendoza", "Andres Alarcon"),
    ("Victor Parada Gonzalez", "Victor Parada"),
    ("Amaury Garcia Moreno", "Amaury Garcia"),
    ("Sebastian Jurado Roca", "Sebastian Jurado"),
    ("Michael Ngadeu-Ngadjui", "Michael Ngadeu"),
    ("Fabricio Garcia Andrade", "Fabricio Garcia"),
]


class TestTheStructureIsRecognised:
    @pytest.mark.parametrize(("full", "short"), SAME_PERSON)
    def test_a_dropped_surname_is_containment(self, full: str, short: str) -> None:
        assert _name_contained(identity(full), identity(short))
        # Symmetric: which source is which must not matter.
        assert _name_contained(identity(short), identity(full))

    @pytest.mark.parametrize(("full", "short"), SAME_PERSON)
    def test_the_fuzzy_score_alone_would_have_refused_them(self, full: str, short: str) -> None:
        """The reason this rule exists rather than a lower threshold."""
        assert name_similarity(identity(full), identity(short)) < STRONG_NAME

    @pytest.mark.parametrize(("full", "short"), SAME_PERSON)
    def test_they_now_reach_the_auto_match_threshold(self, full: str, short: str) -> None:
        confidence, method, reasons = score_pair(identity(full), identity(short))
        assert confidence >= DEFAULT_THRESHOLD, (full, short, confidence, method)
        assert method == "dob+contained_name+supporting"
        assert "name=contained" in reasons

    def test_a_matching_club_as_well_is_recorded_but_does_not_overreach(self) -> None:
        # Stronger than nationality alone, and still below an exact name.
        confidence, method, _ = score_pair(
            identity("Ramon Sosa Acosta", club="Nottingham Forest"),
            identity("Ramon Sosa", club="Nottingham Forest"),
        )
        assert method == "dob+contained_name+nationality+club"
        assert confidence == 0.92
        exact, _, _ = score_pair(identity("Ramon Sosa"), identity("Ramon Sosa"))
        assert confidence < exact


class TestNamesThatMustStayRefused:
    """The half of this file that matters.

    Each of these shares a birthday with its pair and would be a different
    footballer. Every one was observed in the same resolution, scoring around
    0.75 - the same band as the pairs above.
    """

    @pytest.mark.parametrize(("left", "right"), DIFFERENT_PEOPLE)
    def test_a_shared_surname_with_a_different_given_name_is_not_containment(
        self, left: str, right: str
    ) -> None:
        assert not _name_contained(identity(left), identity(right))

    @pytest.mark.parametrize(("left", "right"), DIFFERENT_PEOPLE)
    def test_and_they_stay_below_the_threshold(self, left: str, right: str) -> None:
        confidence, method, _ = score_pair(identity(left), identity(right))
        assert confidence < DEFAULT_THRESHOLD, (left, right, confidence, method)

    def test_a_single_given_name_is_not_enough(self) -> None:
        """A playing name alone, which is where the risk concentrates.

        "Murillo" is contained in "Murillo Santiago Costa dos Santos" and in
        every other Murillo. 88 of the 732 observed containments are of this
        shape; they are left to a person to confirm.
        """
        assert not _name_contained(
            identity("Murillo Santiago Costa dos Santos"), identity("Murillo")
        )
        confidence, _, _ = score_pair(
            identity("Murillo Santiago Costa dos Santos"), identity("Murillo")
        )
        assert confidence < DEFAULT_THRESHOLD

    def test_the_given_name_must_match_in_first_position(self) -> None:
        """As a set member it would be satisfied by a surname matching a middle
        name, which is how unrelated people with long names look alike."""
        assert not _name_contained(
            identity("Silva Pereira Costa"), identity("Costa Silva Pereira Santos")
        )

    def test_containment_needs_supporting_evidence(self) -> None:
        # Containment plus a birthday alone would merge a common given name and
        # a common surname on a shared birthday, which in a Brazilian or Spanish
        # population is not remote.
        confidence, method, _ = score_pair(
            identity("Ramon Sosa Acosta", nationality="Paraguay"),
            identity("Ramon Sosa", nationality="Brazil"),
        )
        assert confidence < DEFAULT_THRESHOLD, method

        confidence, method, _ = score_pair(
            identity("Ramon Sosa Acosta", nationality=None),
            identity("Ramon Sosa", nationality=None),
        )
        assert confidence < DEFAULT_THRESHOLD, method

    def test_a_different_birthday_is_still_fatal(self) -> None:
        """Containment is evidence on top of a date of birth, never instead."""
        confidence, _, _ = score_pair(
            identity("Ramon Sosa Acosta"),
            identity("Ramon Sosa", dob=dt.date(1995, 1, 1)),
        )
        assert confidence < DEFAULT_THRESHOLD

    def test_a_missing_birthday_is_not_a_match_either(self) -> None:
        confidence, _, _ = score_pair(
            identity("Ramon Sosa Acosta"), identity("Ramon Sosa", dob=None)
        )
        assert confidence < DEFAULT_THRESHOLD

    def test_a_repeated_token_is_not_satisfied_once(self) -> None:
        """Multiset, not set: "Santos Santos" is not covered by one "Santos"."""
        assert not _name_contained(
            identity("Joao Santos Santos"), identity("Joao Santos Pereira Lima")
        )


class TestItDoesNotDisturbWhatAlreadyWorked:
    def test_an_identical_name_is_unchanged(self) -> None:
        confidence, method, _ = score_pair(identity("Ramon Sosa"), identity("Ramon Sosa"))
        assert method == "exact_name+dob"
        assert confidence == 0.95

    def test_a_reordered_name_is_still_handled_by_similarity(self) -> None:
        # Equal length is not containment, so this must come out of the fuzzy
        # path exactly as it did before.
        _, method, _ = score_pair(identity("Sosa Ramon"), identity("Ramon Sosa"))
        assert method == "dob+very_strong_name"

    def test_the_commonest_names_are_protected_by_the_ambiguity_margin(self) -> None:
        """Where the residual risk lives, and what bounds it.

        The weakest accepted pairs are the commonest names: "Jose Garcia" and
        "Jesus Rodriguez" and "Carlos Rodriguez" all appear among the new
        matches. The evidence for each is an exact date - not a year - plus a
        nationality plus containment.

        What makes that safe enough is the blocking: every Transfermarkt player
        born that day is a candidate, so a second Jose Garcia born the same day
        would also qualify, score identically, and fall inside
        `DEFAULT_MARGIN`. The resolver then refuses both. Three of the 592
        containments found in the real data came out ambiguous for exactly
        this reason.

        A unique qualifying candidate therefore means there is only one Jose
        Garcia born that day in the whole 50,149-player set.
        """
        source = identity("Jose Daniel Garcia Aragon", nationality="Mexico")
        one = Identity(
            source="tm",
            source_player_id="tm-1",
            full_name="Jose Garcia",
            date_of_birth=BIRTHDAY,
            nationality="Mexico",
        )
        # The coincidence this has to survive: a SECOND Jose Garcia, a different
        # footballer, born the same day. Both names are contained in the source
        # and both score identically, so neither can be preferred.
        another = Identity(
            source="tm",
            source_player_id="tm-2",
            full_name="Jose Garcia",
            date_of_birth=BIRTHDAY,
            nationality="Mexico",
        )

        alone = IdentityResolver([one]).resolve(source)
        assert alone.status is MatchStatus.MATCHED
        assert alone.method == "dob+contained_name+supporting"

        both = IdentityResolver([one, another]).resolve(source)
        assert both.status is MatchStatus.AMBIGUOUS
        assert both.target is None

    def test_two_candidates_that_both_qualify_stay_within_the_margin(self) -> None:
        """So the resolver calls them ambiguous rather than picking one."""
        # Both targets are genuinely contained in the source: one is a prefix
        # of the other, which is exactly how a registered name can cover two
        # different Transfermarkt players at once.
        source = identity("Ramon Sosa Acosta Pereira")
        targets = [identity("Ramon Sosa"), identity("Ramon Sosa Acosta")]
        for target in targets:
            assert _name_contained(source, target)

        first, _, _ = score_pair(source, targets[0])
        second, _, _ = score_pair(source, targets[1])
        assert first == second
        assert abs(first - second) < DEFAULT_MARGIN

        result = IdentityResolver(targets).resolve(source)
        assert result.status is MatchStatus.AMBIGUOUS, result.method
