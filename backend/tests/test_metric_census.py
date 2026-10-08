"""The metric counts, and the one place they are allowed to come from.

Four public pages each wrote these numbers into their own prose, and three of
the four were wrong - in different directions, all from the same mapping:

  - Methodology:  "thirty-four of thirty-nine are mapped and in use" and
                  "the remaining five are not supplied"
  - About:        "five of the thirty-nine canonical metrics are not supplied"
  - System Status: "36 of 39 canonical metrics mapped", three named unavailable
  - Data Quality: three unsupplied, two more listed as derived

The categories had been conflated. Thirty-four are supplied as fields; two
more are assembled from fields that are, and those exist as much as any other;
three cannot be produced at all. Five is a count of provider FIELDS examined
and refused during profiling - a declared-but-empty tackles column, a
percentage reading zero for everybody - and two of those five belong to
metrics already counted once among the three.

These hold the census to its arithmetic and the pages to the census.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.providers.footystats_mapping import get_mapping
from app.schemas.canonical import CanonicalMetric

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"
PUBLIC_PAGES = (
    "app/about/page.tsx",
    "app/methodology/page.tsx",
    "app/data-quality/page.tsx",
    "app/status/page.tsx",
)


class TestTheCensusAddsUp:
    def test_every_canonical_metric_is_in_exactly_one_category(self) -> None:
        census = get_mapping().census()
        assert census.native + census.derived + census.unavailable == census.total

    def test_the_total_is_the_canonical_enum_and_not_a_written_number(self) -> None:
        assert get_mapping().census().total == len(CanonicalMetric)

    def test_usable_counts_derived_metrics_as_existing(self) -> None:
        """A derived metric is computed from observed values, not substituted."""
        census = get_mapping().census()
        assert census.usable == census.native + census.derived

    def test_rejected_fields_are_not_counted_as_canonical_metrics(self) -> None:
        """The source of "five metrics are not supplied", which was never true."""
        census = get_mapping().census()
        assert census.rejected_provider_fields != census.unavailable
        # And it is deliberately outside the sum, so adding it cannot balance.
        assert (
            census.native + census.derived + census.unavailable + census.rejected_provider_fields
            != census.total
        )


class TestThePagesReadItRatherThanRestateIt:
    @pytest.mark.parametrize("page", PUBLIC_PAGES)
    def test_no_public_page_writes_a_metric_count_in_prose(self, page: str) -> None:
        """The drift that produced four answers to one question.

        Any of these numbers spelled out in copy is a second opinion with no
        way of noticing when it becomes wrong. The pages take them from the
        census the API sends.
        """
        source = (FRONTEND / page).read_text(encoding="utf8")
        flat = " ".join(source.split()).lower()
        for written in (
            "thirty-nine canonical",
            "thirty-four of thirty-nine",
            "thirty-six of thirty-nine",
            "34 of 39",
            "36 of 39",
        ):
            assert written not in flat, f"{page} states a metric count in prose: {written}"

    @pytest.mark.parametrize("page", PUBLIC_PAGES)
    def test_no_public_page_spells_a_count_of_unsupplied_metrics(self, page: str) -> None:
        """ "Five are not supplied" was the specific sentence that was false."""
        source = (FRONTEND / page).read_text(encoding="utf8")
        flat = " ".join(source.split()).lower()
        for written in ("five of the", "five metrics", "three metrics the provider"):
            assert written not in flat, f"{page} counts unsupplied metrics in prose: {written}"


class TestTheApiPublishesIt:
    def test_meta_carries_the_census(self, client: TestClient) -> None:
        body = client.get("/api/v1/meta").json()
        census = body.get("metric_census")
        if census is None:
            pytest.skip("no verified mapping in this mode")
        assert census["native"] + census["derived"] + census["unavailable"] == census["total"]
        assert census["usable"] == census["native"] + census["derived"]

    def test_the_provider_note_agrees_with_the_census(self, client: TestClient) -> None:
        """One string, one object, and they must not disagree."""
        body = client.get("/api/v1/meta").json()
        census = body.get("metric_census")
        if census is None:
            pytest.skip("no verified mapping in this mode")
        performance = next(s for s in body["data_sources"] if s["kind"] == "performance")
        if performance["is_mock"]:
            pytest.skip("the mock provider does not describe a real mapping")
        numbers = {int(n) for n in re.findall(r"\b\d+\b", performance["notes"] or "")}
        assert census["usable"] in numbers
        assert census["total"] in numbers
