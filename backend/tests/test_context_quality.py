"""The checks that watch the reconciliation between the two providers.

WHY THESE EXIST

A profile shows the club that played the season beside the club the player is
at now, and the competition each belongs to. Those come from two sources that
share no vocabulary - not for clubs, not for competitions, not entirely for
countries - so the page is trustworthy only as far as the reconciliation
between them holds.

Nothing watched it. The country spellings disagreed on three names and the
only symptom was a sentence on a profile saying a player had moved abroad
when he was at the same club he had always been at. Nobody saw it because
nobody was counting.

WHAT THEY DO NOT DO

None of them treats a transfer as a defect. Players move, the market source
and the performance source describe different moments, and a difference
between them is ordinary - the profile says so in its own words. These look
for the page asserting two things that cannot both be true.
"""

from __future__ import annotations

import pytest
from pipelines.quality.report import (
    MAX_EXPIRED_CONTRACT_SHARE,
    context_checks,
    one_club_in_two_countries,
)


class TestOneClubInTwoCountries:
    """The contradiction, and everything that is not one."""

    def test_the_korea_case_that_had_no_symptom_but_a_wrong_sentence(self) -> None:
        """Before the aliases, this is what a reader was shown.

        Same club, same country, two provider spellings - and a note saying
        the player had moved to another country. `in_the_same_country` fixes
        the sentence; this is the check that would have found it.
        """
        assert (
            one_club_in_two_countries(
                "Gangwon FC", "Gangwon Football Club", "South Korea", "Korea, South"
            )
            is False
        )
        # And the same pair with the alias removed is exactly what this
        # detects, which is the point of it.
        assert (
            one_club_in_two_countries(
                "Gangwon FC", "Gangwon Football Club", "South Korea", "Freedonia"
            )
            is True
        )

    def test_a_transfer_is_not_a_contradiction(self) -> None:
        # Two clubs, two countries. Ordinary, and the profile explains it.
        assert one_club_in_two_countries("Houston Dynamo", "CD Cruz Azul", "USA", "Mexico") is False

    def test_a_domestic_move_is_not_a_contradiction(self) -> None:
        assert one_club_in_two_countries("AD Pasto", "Deportivo Cali", "Colombia", "Colombia") is (
            False
        )

    def test_names_that_settle_nothing_raise_nothing(self) -> None:
        """`same_club` answers `None` for Manchester United against Manchester
        City: a shared city and nothing else. A check that read that as "the
        same club" would then call the two countries a contradiction."""
        assert (
            one_club_in_two_countries(
                "Manchester United", "Manchester City", "England", "Freedonia"
            )
            is False
        )

    def test_a_continental_competition_raises_nothing(self) -> None:
        # One side's country is a continent, so there is no comparison to
        # make and `in_the_same_country` says so.
        assert (
            one_club_in_two_countries(
                "Gangwon FC", "Gangwon Football Club", "Europe", "South Korea"
            )
            is False
        )

    @pytest.mark.parametrize(
        ("season_club", "current_club", "here", "there"),
        [
            (None, "Gangwon Football Club", "South Korea", "Denmark"),
            ("Gangwon FC", None, "South Korea", "Denmark"),
            ("Gangwon FC", "Gangwon Football Club", None, "Denmark"),
            ("Gangwon FC", "Gangwon Football Club", "South Korea", None),
        ],
    )
    def test_a_missing_half_is_not_a_contradiction(
        self, season_club: str | None, current_club: str | None, here: str | None, there: str | None
    ) -> None:
        """Absent is not disagreement.

        The market source does not cover every player, and a check that read
        a gap as a defect would report thousands of them.
        """
        assert one_club_in_two_countries(season_club, current_club, here, there) is False


@pytest.mark.integration
class TestAgainstTheLoadedDatabase:
    def test_the_checks_run_and_report_a_verdict(self, db_session) -> None:
        checks = context_checks(db_session)
        names = {c.name for c in checks}
        assert names == {
            "one_club_is_in_one_country",
            "season_club_plays_in_its_competitions_country",
            "contracts_are_current",
        }
        for check in checks:
            assert check.status in {"pass", "warn", "fail"}

    def test_a_contradiction_is_a_failure_and_the_others_are_warnings(self, db_session) -> None:
        """The severities are deliberate and different.

        One club in two countries cannot be true, so it fails and stops a
        promotion. A club filed under the wrong country and an expired
        contract are both things the provider said, so they warn: the
        pipeline has no business refusing to publish because a footballer's
        contract ran out.
        """
        by_name = {c.name: c for c in context_checks(db_session)}
        contradiction = by_name["one_club_is_in_one_country"]
        if contradiction.count:
            assert contradiction.status == "fail"
        assert by_name["contracts_are_current"].status != "fail"
        assert by_name["season_club_plays_in_its_competitions_country"].status != "fail"

    def test_every_finding_carries_a_code_as_well_as_the_english(self, db_session) -> None:
        # The same rule the rest of the report follows: prose is for whoever
        # reads English, and the code is what the interface renders.
        for check in context_checks(db_session):
            if check.detail:
                assert check.explain is not None, f"{check.name} has prose and no code"

    def test_the_expired_contract_bound_is_a_share_not_a_count(self) -> None:
        # A count would mean the check tightens every time the universe grows.
        assert 0 < MAX_EXPIRED_CONTRACT_SHARE < 1
