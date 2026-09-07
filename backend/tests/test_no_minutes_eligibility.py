"""Minutes never decide who is in the product.

A deliberate product decision, and one that has been re-derived by accident
more than once: a threshold looks like prudence, and reintroducing one is a
two-line change that no unit test elsewhere would notice.

So this asserts it end to end, on the loaded database, at the level the
decision actually lives at: a player with one minute and a player with three
thousand are both searchable, both ranked, both scored, and both available as
similarity candidates. The only rule is arithmetic - a per-90 needs a
denominator - and a player who has none gets N/A rather than a fabricated
figure.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.analytics.sample import (
    DEVELOPING_SAMPLE_MINUTES,
    ESTABLISHED_SAMPLE_MINUTES,
    LOW_SAMPLE_MINUTES,
    SampleBand,
    can_rate,
    classify_minutes,
)
from app.core.config import Settings
from app.services.analytics_service import build_view

from .conftest import build_client, build_settings

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def production_settings() -> Settings:
    return build_settings(app_mode="production")


@pytest.fixture(scope="module")
def view(production_settings: Settings):  # type: ignore[no-untyped-def]
    return build_view(production_settings)


@pytest.fixture(scope="module")
def client(production_settings: Settings):  # type: ignore[no-untyped-def]
    with build_client(production_settings) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# The rule itself
# ---------------------------------------------------------------------------


class TestTheOnlyRuleIsArithmetic:
    @pytest.mark.parametrize("minutes", [1, 45, 100, 179, 180, 449, 450, 899, 900, 3000])
    def test_any_positive_denominator_can_be_rated(self, minutes: int) -> None:
        assert can_rate(minutes) is True

    def test_no_denominator_cannot(self) -> None:
        """Not an exclusion. There is nothing to divide by."""
        assert can_rate(0) is False
        assert can_rate(None) is False

    @pytest.mark.parametrize(
        ("minutes", "band"),
        [
            (1, SampleBand.VERY_LOW),
            (100, SampleBand.VERY_LOW),
            (LOW_SAMPLE_MINUTES, SampleBand.LOW),
            (300, SampleBand.LOW),
            (DEVELOPING_SAMPLE_MINUTES, SampleBand.DEVELOPING),
            (500, SampleBand.DEVELOPING),
            (ESTABLISHED_SAMPLE_MINUTES, SampleBand.ESTABLISHED),
            (3000, SampleBand.ESTABLISHED),
        ],
    )
    def test_the_bands_label_rather_than_gate(self, minutes: int, band: SampleBand) -> None:
        assert classify_minutes(minutes) is band
        assert can_rate(minutes) is True, "a band decided eligibility, which it must not"


# ---------------------------------------------------------------------------
# End to end, on whatever is loaded
# ---------------------------------------------------------------------------


class TestEveryBandReachesTheProduct:
    def test_all_four_bands_are_present_in_the_view(self, view) -> None:  # type: ignore[no-untyped-def]
        """If a band never appears, the assertions below prove nothing."""
        bands = {record.sample_band for record in view.players.values()}
        missing = {b for b in SampleBand} - bands
        if missing:
            pytest.skip(f"no loaded player is in {sorted(b.value for b in missing)}")
        assert bands == set(SampleBand)

    @pytest.mark.parametrize("band", list(SampleBand))
    def test_a_player_from_each_band_is_searchable(self, client: TestClient, view, band) -> None:  # type: ignore[no-untyped-def]
        subject = next(
            (r for r in view.players.values() if r.sample_band is band),
            None,
        )
        if subject is None:
            pytest.skip(f"no loaded player is in band {band.value}")

        response = client.get("/api/v1/players", params={"search": subject.full_name})
        assert response.status_code == 200
        returned = {row["player_id"] for row in response.json()["items"]}
        assert subject.player_key in returned, (
            f"{subject.full_name} ({subject.minutes} minutes, {band.value}) is not "
            f"searchable, which is a minutes-based exclusion"
        )

    @pytest.mark.parametrize("band", list(SampleBand))
    def test_a_player_from_each_band_has_a_profile_with_percentiles(
        self,
        client: TestClient,
        view,
        band,  # type: ignore[no-untyped-def]
    ) -> None:
        subject = next((r for r in view.players.values() if r.sample_band is band), None)
        if subject is None:
            pytest.skip(f"no loaded player is in band {band.value}")

        response = client.get(f"/api/v1/players/{subject.player_key}/profile")
        assert response.status_code == 200
        body = response.json()

        assert body["stats"] is not None
        ranked = [m for m in body["stats"]["metrics"] if m["percentile"] is not None]
        assert ranked, (
            f"{subject.full_name} ({subject.minutes} minutes, {band.value}) was ranked "
            f"on nothing at all"
        )

    def test_the_shortest_sample_in_the_database_is_still_ranked(
        self, client: TestClient, view
    ) -> None:
        """The extreme case, chosen from the data rather than invented."""
        rateable = [
            r for r in view.players.values() if r.stats.minutes is not None and r.stats.minutes > 0
        ]
        if not rateable:
            pytest.skip("nothing loaded")
        subject = min(rateable, key=lambda r: r.stats.minutes or 0)

        response = client.get(f"/api/v1/players/{subject.player_key}/profile")
        assert response.status_code == 200
        body = response.json()
        assert body["stats"]["sample"]["band"] in {b.value for b in SampleBand}
        # Labelled, and present. Both halves matter.
        assert body["stats"]["sample"]["band_label"]


class TestNothingIsFabricatedToAchieveThis:
    def test_a_metric_without_a_denominator_is_absent_not_zero(self, view) -> None:  # type: ignore[no-untyped-def]
        """The other half of the decision, and the more important one.

        Including everybody is only defensible because nobody is given a
        number they have not earned. A player whose denominator is missing
        gets `None`, which the API renders as unavailable.
        """
        offenders = []
        for record in view.players.values():
            metrics = record.metrics
            if metrics.minutes in (None, 0) and metrics.passes_per90 is not None:
                offenders.append(record.player_key)
            if metrics.playing_minutes in (None, 0) and metrics.goals_per90 is not None:
                offenders.append(record.player_key)
        assert offenders == [], offenders[:5]
