"""When a contract runs out, and what "expiring soon" means.

This arithmetic lived in four places, written longhand each time, and carried
the same defect in all four: it asked whether an expiry was *at most* N months
away and never whether it was in the future at all. A contract that ended in
June 2024 is -31 months away, and -31 clears any threshold, so 900 loaded
players with lapsed contracts passed a filter for "expiring within 18 months"
and were offered as opportunities with "Contract expires Jun 2024" printed
underneath as a reason to sign them.
"""

from __future__ import annotations

import datetime as dt

from app.analytics.contracts import (
    expires_within,
    has_lapsed,
    months_until,
    reference_date,
)

TODAY = dt.date(2026, 8, 30)


class TestMonthsUntil:
    def test_a_future_expiry_counts_forward(self) -> None:
        assert months_until(dt.date(2027, 6, 30), today=TODAY) == 10

    def test_a_past_expiry_counts_backward(self) -> None:
        """The sign is the whole point: it is what tells a lapsed contract from
        an expiring one."""
        assert months_until(dt.date(2024, 6, 30), today=TODAY) == -26

    def test_the_same_month_is_nought(self) -> None:
        assert months_until(dt.date(2026, 8, 1), today=TODAY) == 0


class TestExpiresWithin:
    def test_an_expiry_inside_the_window_passes(self) -> None:
        assert expires_within(dt.date(2027, 6, 30), 18, today=TODAY)

    def test_an_expiry_beyond_the_window_does_not(self) -> None:
        assert not expires_within(dt.date(2029, 1, 1), 18, today=TODAY)

    def test_a_lapsed_contract_does_not_pass(self) -> None:
        """The defect. A player whose recorded contract ended two years ago is
        not a player whose contract is about to end: either they re-signed and
        the dataset has not caught up, or they left. Either way the record says
        nothing about their situation now."""
        assert not expires_within(dt.date(2024, 6, 30), 18, today=TODAY)

    def test_a_contract_that_ended_this_month_does_not_pass(self) -> None:
        """Month granularity is right for "how far ahead" and wrong for "has it
        passed": the 15th is nought months away on the 30th, and would slip back
        in through the same door."""
        assert not expires_within(dt.date(2026, 8, 15), 18, today=TODAY)

    def test_a_contract_ending_tomorrow_still_passes(self) -> None:
        assert expires_within(dt.date(2026, 8, 31), 18, today=TODAY)

    def test_no_recorded_expiry_does_not_pass(self) -> None:
        """The filter asks a question this player's data cannot answer, and
        answering it anyway is the invention this project forbids."""
        assert not expires_within(None, 18, today=TODAY)

    def test_a_window_of_nought_still_admits_this_month(self) -> None:
        assert expires_within(dt.date(2026, 8, 31), 0, today=TODAY)


class TestHasLapsed:
    def test_it_names_a_stale_record_rather_than_a_free_agent(self) -> None:
        """Worth naming separately: a lapsed record is a fact about the
        dataset's freshness, not about the player."""
        assert has_lapsed(dt.date(2024, 6, 30), today=TODAY)
        assert not has_lapsed(dt.date(2027, 6, 30), today=TODAY)
        assert not has_lapsed(None, today=TODAY)


class TestReferenceDate:
    def test_it_is_today_not_a_fixed_point(self) -> None:
        """It was pinned to 1 January 2027 so the demo universe produced stable
        ages. Against real data that showed 1,541 of 5,456 players - 28% - at an
        age they had not reached."""
        assert reference_date() == dt.date.today()
