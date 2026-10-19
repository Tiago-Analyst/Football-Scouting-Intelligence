"""A competition the subscription does not carry is a third kind of failure.

THE TWO THAT EXISTED, AND WHY NEITHER FITS

`test_footystats_failure_modes` separates a per-player failure (the run working:
the player stays pending and the next run retries them) from a rejected key (the
run condemned: every call after it fails identically). A competition outside the
plan is neither. Every other competition in the run succeeds, so it is not
fatal; and no re-run will ever acquire this one, so it is not transient.

Treated as transient, it is the worst of both. The roster is refused, so the
competition keeps players pending, so the generation is never complete, so the
load refuses to publish a partial universe - correctly. The result is an hourly
job that fetches nothing, publishes nothing, and reports "at least one
competition could not be read at all. Run again to continue."

That is what happened. Russia Russian Premier League (17178) and Spain Segunda
División (17269) were listed for ingest on 2026-08-29 and are not on the
subscription. From 2026-10-14, when every one of the generation's 8,859 players
had in fact been fetched, the pipeline refused to publish once an hour, and the
log said `roster failed: FootyStatsError` - the exception's class and not its
message, so the reason never reached it.

Two things are pinned here: that 417 is recognised and explained, and that the
message is never again reduced to a class name.
"""

from __future__ import annotations

import io
import json
import urllib.error
from typing import Any

import pytest
from pipelines.footystats.ingest import (
    CompetitionResult,
    RunReport,
    ingest_competition,
    verdict,
)

from app.providers.footystats import (
    NOT_SUBSCRIBED_STATUS,
    FootyStatsAuthError,
    FootyStatsError,
    FootyStatsNotSubscribedError,
    _explain,
)

#: The body FootyStats actually returns, recorded from /league-players for
#: season 17178 on 2026-10-19. Trimmed to the fields under test.
REAL_417_BODY = {
    "success": False,
    "data": [],
    "message": (
        "League is not chosen by the user (this might be delayed by cache if you "
        "chose the league recently, wait 1 hour). League may also not be available "
        "on your plan."
    ),
}


def http_error(status: int, body: object) -> urllib.error.HTTPError:
    payload = json.dumps(body).encode()
    return urllib.error.HTTPError(
        url="https://api.example.test/league-players?key=SECRET",
        code=status,
        msg="Expectation Failed",
        hdrs=None,  # type: ignore[arg-type]
        fp=io.BytesIO(payload),
    )


# ---------------------------------------------------------------------------
# Reading the reason out of the response
# ---------------------------------------------------------------------------


class TestExplanation:
    def test_the_api_s_own_words_are_read_out_of_the_body(self) -> None:
        # Without this the exception says "HTTP 417" and nothing else, which
        # names neither the cause nor the fix.
        assert "League is not chosen by the user" in _explain(http_error(417, REAL_417_BODY))

    def test_whitespace_is_collapsed_and_the_text_is_bounded(self) -> None:
        # Free text from a service, landing in an exception message that reaches
        # the logs.
        sprawling = {"message": "a\n\n   b\t" + ("x" * 500)}
        explained = _explain(http_error(417, sprawling))
        assert explained.startswith("a b ")
        assert "\n" not in explained
        assert len(explained) <= 200

    @pytest.mark.parametrize(
        "body",
        [
            b"not json at all",
            b"",
            json.dumps({"no_message_field": True}).encode(),
            json.dumps({"message": {"nested": "object"}}).encode(),
            json.dumps(["a list, not an object"]).encode(),
        ],
        ids=["garbage", "empty", "absent", "wrong-type", "not-a-dict"],
    )
    def test_an_unreadable_body_yields_no_explanation_rather_than_an_error(
        self, body: bytes
    ) -> None:
        # This runs while an error is already being handled. An explanation
        # attempt that raised would replace a known status code with its own
        # traceback, which is strictly worse than no explanation.
        error = urllib.error.HTTPError(
            url="https://api.example.test/x",
            code=417,
            msg="x",
            hdrs=None,  # type: ignore[arg-type]
            fp=io.BytesIO(body),
        )
        assert _explain(error) == ""

    def test_a_body_that_cannot_be_read_at_all_yields_no_explanation(self) -> None:
        class Unreadable:
            def read(self) -> bytes:
                raise OSError("connection reset while reading the body")

            def close(self) -> None:
                # `HTTPError` closes its file object on collection; without this
                # the teardown raises where the test cannot see it.
                return None

        error = urllib.error.HTTPError(
            url="https://api.example.test/x",
            code=417,
            msg="x",
            hdrs=None,  # type: ignore[arg-type]
            fp=Unreadable(),  # type: ignore[arg-type]
        )
        assert _explain(error) == ""


# ---------------------------------------------------------------------------
# 417 is its own kind, and says what to do about it
# ---------------------------------------------------------------------------


class TestNotSubscribedIsDistinguished:
    def test_it_is_not_an_auth_error(self) -> None:
        # The key is fine - it reads forty-five other competitions on the same
        # run. Folding this in with 401/403 would condemn the whole run, and
        # the forty-five would stop being fetched.
        assert not issubclass(FootyStatsNotSubscribedError, FootyStatsAuthError)
        assert issubclass(FootyStatsNotSubscribedError, FootyStatsError)
        assert NOT_SUBSCRIBED_STATUS not in {401, 403}

    def test_the_message_names_both_ways_out(self) -> None:
        # The operator has two choices and neither is obvious from a status
        # code: choose the league on the account, or declare the exclusion.
        message = str(
            FootyStatsNotSubscribedError(
                "/league-players refused: HTTP 417 (League is not chosen by the user). "
                "This competition is not on the subscription, so no re-run will fetch it. "
                "Choose the league on the FootyStats account, or record it under "
                "`excluded` in config/competitions.yaml."
            )
        )
        assert "no re-run will fetch it" in message
        assert "FootyStats account" in message
        assert "config/competitions.yaml" in message


# ---------------------------------------------------------------------------
# What the ingest does with it
# ---------------------------------------------------------------------------


class RefusedCompetition:
    """The roster is refused for a reason no re-run will change."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    def _roster(self, season_id: str) -> list[dict[str, Any]]:
        raise self._error

    def _get(self, path: str, **params: object) -> Any:  # pragma: no cover - never reached
        raise AssertionError("no player should be fetched for a refused roster")


class TestIngestRecordsIt:
    def test_the_competition_is_flagged_rather_than_merely_errored(self) -> None:
        result = ingest_competition(
            RefusedCompetition(FootyStatsNotSubscribedError("/league-players refused: HTTP 417")),
            season_id="17178",
            name="Russia Russian Premier League",
            resume=False,
        )
        assert result.not_subscribed is True
        # Still an error, and still not fatal: the run carries on to the next
        # competition, and the exit code refuses to call the run a success.
        assert result.error
        assert result.fatal is False

    def test_a_transient_failure_is_not_flagged_as_unsubscribed(self) -> None:
        # The distinction is the whole point. A 500 should keep inviting the
        # re-run that a 417 must not.
        result = ingest_competition(
            RefusedCompetition(
                FootyStatsError("/league-players failed after 3 attempts: HTTP 500")
            ),
            season_id="17084",
            name="Italy Serie A",
            resume=False,
        )
        assert result.not_subscribed is False
        assert result.error

    def test_the_recorded_error_carries_the_message_and_not_just_the_class(self) -> None:
        # `roster failed: FootyStatsError` is what the log said for five days of
        # hourly failures. It names no status, no endpoint and no cause.
        result = ingest_competition(
            RefusedCompetition(
                FootyStatsError("/league-players failed: HTTP 417 (League is not chosen)")
            ),
            season_id="17269",
            name="Spain Segunda División",
            resume=False,
        )
        assert result.error is not None
        assert "League is not chosen" in result.error
        assert result.error != "roster failed: FootyStatsError"


def report_with(*competitions: CompetitionResult) -> RunReport:
    return RunReport(started_at="2026-10-19T09:40:00Z", competitions=list(competitions))


class TestTheVerdictNamesThem:
    def test_the_unsubscribed_competitions_are_reported_by_name(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Four scheduled runs failed with a message that named nothing."""
        report = report_with(
            CompetitionResult(season_id="17199", name="Spain La Liga", skipped=200),
            CompetitionResult(
                season_id="17178",
                name="Russia Russian Premier League",
                error="roster refused: HTTP 417 (League is not chosen by the user)",
                not_subscribed=True,
            ),
        )

        assert verdict(report) == 1
        printed = capsys.readouterr().out

        assert "17178" in printed
        assert "Russia Russian Premier League" in printed
        # Only the refused one. Naming all forty-six is how a verdict becomes
        # something nobody reads.
        assert "Spain La Liga" not in printed
        # And it must not repeat the instruction that wasted five days.
        assert "run again to continue" not in printed.lower()
        assert "Re-running will not change this" in printed
        assert "config/competitions.yaml" in printed

    def test_a_transient_refusal_still_prints_its_own_reason(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # The generic branch, which used to print one line naming nothing.
        report = report_with(
            CompetitionResult(
                season_id="17084",
                name="Italy Serie A",
                error="roster failed: FootyStatsError: /league-players failed: HTTP 503",
            )
        )

        assert verdict(report) == 1
        printed = capsys.readouterr().out
        assert "17084" in printed
        assert "HTTP 503" in printed
        # Not the subscription message: this one genuinely may fix itself.
        assert "subscription" not in printed.lower()

    def test_a_clean_run_says_nothing_and_succeeds(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        report = report_with(
            CompetitionResult(season_id="17199", name="Spain La Liga", skipped=200)
        )
        assert verdict(report) == 0
        assert capsys.readouterr().out == ""

    def test_a_rejected_key_outranks_everything(self, capsys: pytest.CaptureFixture[str]) -> None:
        # Fatal first: with the key refused, what the subscription carries is
        # not yet knowable. `RunReport.fatal` is derived from the competitions,
        # so this is set where the run would really set it.
        report = report_with(
            CompetitionResult(
                season_id="17178",
                name="Russia Russian Premier League",
                error="roster refused: HTTP 417",
                not_subscribed=True,
            ),
            CompetitionResult(
                season_id="17199",
                name="Spain La Liga",
                error="roster refused: HTTP 403",
                fatal=True,
            ),
        )

        assert verdict(report) == 1
        assert "retrying will not fix" in capsys.readouterr().out
