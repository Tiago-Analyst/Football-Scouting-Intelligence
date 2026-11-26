"""Two things a product review found on production on 26 November.

A rate over thirteen shots was listed as a statistical highlight beside the
sentence saying thirteen shots were too few, and a competition missing from the
site could only be noticed by comparing two counts.
"""

from __future__ import annotations

import yaml

from app.analytics.interpretation import LOW_EVIDENCE_RATES, MetricReading, ScoreReading, interpret
from app.api.v1.quality import _missing_competitions
from app.core.config import REPO_ROOT

SCORES = yaml.safe_load(
    (REPO_ROOT / "config" / "intelligence_scores.yaml").read_text(encoding="utf-8")
)["scores"]


def reading(*, low: bool):
    return interpret(
        role=None,
        scores=[ScoreReading("Finishing", 83.0, low_evidence=low, key="finishing")],
        metrics=[
            MetricReading("Shot conversion %", 83.0, metric="shot_conversion"),
            MetricReading("Shot quality", 12.0, metric="shot_quality"),
            MetricReading("npxG /90", 79.0, metric="npxg_per90"),
        ],
        minutes=900,
        sample_band_label=None,
        detailed_coverage_pct=None,
    )


def test_a_rate_over_too_few_events_is_neither_highlight_nor_watch_out() -> None:
    thin = reading(low=True)
    assert [f.metric for f in thin.strengths] == ["npxg_per90"]
    assert thin.watch_outs == []


def test_with_enough_events_the_rates_are_read_as_before() -> None:
    enough = reading(low=False)
    assert [f.metric for f in enough.strengths] == ["shot_conversion", "npxg_per90"]
    assert [f.metric for f in enough.watch_outs] == ["shot_quality"]


def test_every_score_with_an_evidence_rule_names_its_rates() -> None:
    ruled = {key for key, body in SCORES.items() if "evidence" in body}
    assert set(LOW_EVIDENCE_RATES) == ruled
    for key, rates in LOW_EVIDENCE_RATES.items():
        assert rates <= set(SCORES[key]["components"])


def test_a_served_id_carries_its_source_and_the_configuration_does_not() -> None:
    configured = {"17381": "Asia AFC Champions League", "18081": "Colombia Categoria Primera A"}
    assert _missing_competitions(configured, ["footystats:17381"]) == [
        "Colombia Categoria Primera A"
    ]
    assert _missing_competitions(configured, ["footystats:17381", "footystats:18081"]) == []
