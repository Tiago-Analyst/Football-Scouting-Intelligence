"""A search body refuses a filter it will not apply.

WHAT IT USED TO DO

`RecruitmentRequest` and `ReplacementRequest` accepted any extra top-level
key, dropped it, and answered 200. A search sent with `position_group` and
`min_minutes` at the top level - rather than under `filters`, as
`position_groups` and `min_minutes` - was served as an unfiltered search over
the whole population, with nothing in the response to say that both
constraints had been discarded.

It was sent by someone measuring this endpoint with its source open beside
them. The filtered brief looked to have regressed from 0.2s to 4.5s, and the
reason was that both the filtered and the unfiltered request were the same
unfiltered request. An integrator gets neither the source nor the suspicion.

WHY THIS MATTERS MORE THAN A TIDY SCHEMA

The failure is not that a key was wrong. It is that the answer was plausible.
A shortlist narrowed to an under-21 budget signing, returned as the whole
population ranked by the same weights, looks exactly like a shortlist. Nobody
checks the count of a list that came back full.

WHAT THESE ASSERT

That the refusal happens, that it names where a misplaced filter belongs, and
that the names come from the filter model rather than from a list written
twice. Above all, that the bodies the site actually sends still pass: a schema
that refuses its own frontend has traded one silent defect for a loud one.
"""

from __future__ import annotations

import pytest

from app.schemas.api import (
    RecruitmentFilters,
    ReplacementRequest,
    SearchRequest,
)

pytestmark = pytest.mark.integration


def _fields(response) -> list[dict[str, str]]:  # type: ignore[no-untyped-def]
    return response.json()["error"]["details"]["fields"]


def _reasons(response) -> str:  # type: ignore[no-untyped-def]
    return " ".join(field["reason"] for field in _fields(response))


class TestTheMistakeThatWasMade:
    """The exact request that was served as something else."""

    def test_it_is_refused_rather_than_quietly_widened(self, client) -> None:  # type: ignore[no-untyped-def]
        response = client.post(
            "/api/v1/recruitment/search",
            json={
                "weights": {"ball_security": 36, "defensive_activity": 46},
                "position_group": "CM",
                "min_minutes": 900,
            },
        )
        assert response.status_code == 422

    def test_it_says_where_both_of_them_belong(self, client) -> None:  # type: ignore[no-untyped-def]
        response = client.post(
            "/api/v1/recruitment/search",
            json={
                "weights": {"ball_security": 36},
                "position_group": "CM",
                "min_minutes": 900,
            },
        )
        reasons = _reasons(response)
        # The one that needed a plural, and the one that was spelled correctly
        # and still in the wrong place.
        assert "position_group -> filters.position_groups" in reasons
        assert "min_minutes -> filters.min_minutes" in reasons

    def test_the_replacement_body_had_the_same_hole(self, client) -> None:  # type: ignore[no-untyped-def]
        response = client.post(
            "/api/v1/replacement/search",
            json={"player_id": "x", "max_age": 28},
        )
        assert response.status_code == 422
        assert "max_age -> filters.max_age" in _reasons(response)


class TestWhatTheRefusalCovers:
    def test_a_key_that_is_not_a_filter_is_still_refused(self, client) -> None:  # type: ignore[no-untyped-def]
        # No hint to give, and it still may not be ignored: a caller who sends
        # a key this API does not know is working from a belief about it.
        response = client.post(
            "/api/v1/recruitment/search",
            json={"weights": {"ball_security": 36}, "sort_by": "age"},
        )
        assert response.status_code == 422
        assert any(field["field"].endswith("sort_by") for field in _fields(response))

    def test_an_unknown_filter_inside_filters_is_refused_too(self, client) -> None:  # type: ignore[no-untyped-def]
        # The same defect one level down: a constraint the caller believes is
        # being applied, which is not.
        response = client.post(
            "/api/v1/recruitment/search",
            json={"weights": {"ball_security": 36}, "filters": {"position_group": ["CM"]}},
        )
        assert response.status_code == 422
        assert any("filters.position_group" in field["field"] for field in _fields(response))


class TestTheHintIsDerivedRatherThanListed:
    """A second copy of the filter names is the defect, not the fix."""

    def test_every_filter_can_be_pointed_at_by_its_own_name(self, client) -> None:  # type: ignore[no-untyped-def]
        for name in RecruitmentFilters.model_fields:
            response = client.post(
                "/api/v1/recruitment/search",
                json={"weights": {"ball_security": 36}, name: None},
            )
            assert response.status_code == 422, name
            assert f"{name} -> filters.{name}" in _reasons(response), name

    def test_a_filter_renamed_tomorrow_is_covered_without_editing_a_list(self) -> None:
        # The names are read from the model at validation time. This asserts
        # the wiring rather than the behaviour, because the behaviour above
        # would keep passing against a hardcoded copy that happens to agree.
        import inspect

        source = inspect.getsource(SearchRequest)
        assert "RecruitmentFilters.model_fields" in source, (
            "the hint no longer reads the filter names from the filter model"
        )


class TestTheSiteStillWorks:
    """A schema that refuses its own frontend is a worse bug than the one fixed."""

    def test_the_recruitment_body_the_site_sends(self, client) -> None:  # type: ignore[no-untyped-def]
        response = client.post(
            "/api/v1/recruitment/search",
            json={
                "weights": {"ball_security": 20, "defensive_activity": 25, "chance_creation": 10},
                "filters": {
                    "position_groups": None,
                    "max_age": None,
                    "min_age": None,
                    "max_market_value_eur": None,
                    "competitions": None,
                    "min_minutes": 0,
                    "contract_expiring_within_months": None,
                },
                "limit": 20,
            },
        )
        assert response.status_code == 200, response.text

    def test_the_replacement_body_the_site_sends(self, client) -> None:  # type: ignore[no-untyped-def]
        response = client.post(
            "/api/v1/replacement/search",
            json={
                "player_id": "nobody",
                "filters": {
                    "max_market_value_eur": None,
                    "max_age": None,
                    "competitions": None,
                    "min_minutes": 0,
                    "contract_expiring_within_months": None,
                },
                "limit": 20,
            },
        )
        # 404 for the unknown player is the right answer; what must not happen
        # is 422, which would mean the site's own body no longer validates.
        assert response.status_code != 422, response.text

    def test_every_field_the_site_fills_is_declared(self) -> None:
        # Cheaper than the two above and says the thing directly: these are
        # the keys the two pages build, and `extra="forbid"` now makes any
        # undeclared one fatal rather than ignored.
        for name in (
            "position_groups",
            "min_age",
            "max_age",
            "max_market_value_eur",
            "competitions",
            "min_minutes",
            "contract_expiring_within_months",
        ):
            assert name in RecruitmentFilters.model_fields, name
        assert set(ReplacementRequest.model_fields) >= {"player_id", "filters", "limit"}
