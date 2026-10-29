"""The frontend's copy of this API's vocabulary is still this API's vocabulary.

Every metric key and coverage band below reaches a reader as a word on a page,
and the interface writes that word itself, in its own language, keyed by the
key this module emits. So the set of keys is part of the contract, not an
implementation detail.

`frontend/tests/helpers/api-vocabulary.json` is that set, copied, because a
Node test cannot import Python. This test is the other half: it fails the
moment the enums here gain or lose a member without the copy being regenerated,
and the frontend test then fails if the new member has no translation.

Without this pair, adding a metric is silently an English leak. That is not
hypothetical - 16 of the 43 metrics had no Portuguese name on 29 October 2026,
and every i18n test passed, because both dictionaries agreed completely about
a vocabulary that was too small.

Regenerate with:

    python -m tests.test_api_vocabulary
"""

from __future__ import annotations

import json
from pathlib import Path

from app.analytics.coverage import CoverageBand
from app.analytics.metrics import DerivedMetric
from app.analytics.roles import RoleCoverage
from app.analytics.similarity import FeatureCoverage

VOCABULARY_PATH = (
    Path(__file__).resolve().parents[2] / "frontend" / "tests" / "helpers" / "api-vocabulary.json"
)


def current() -> dict[str, list[str]]:
    """The vocabulary as the analytics modules define it right now.

    The three coverage enums are merged into one list because the interface
    has one map for them: the bands do not collide, and where two of them
    share a name - `limited`, `good` - they also share a meaning and an
    English label.
    """
    bands = {
        *(band.value for band in CoverageBand),
        *(band.value for band in RoleCoverage),
        *(band.value for band in FeatureCoverage),
    }
    return {
        "metrics": sorted(metric.value for metric in DerivedMetric),
        "coverage_bands": sorted(bands),
    }


def test_frontend_vocabulary_matches_the_enums() -> None:
    recorded = json.loads(VOCABULARY_PATH.read_text(encoding="utf-8"))
    live = current()

    for field in ("metrics", "coverage_bands"):
        added = sorted(set(live[field]) - set(recorded[field]))
        removed = sorted(set(recorded[field]) - set(live[field]))
        assert not added, (
            f"{field}: new in the API and not in the frontend's copy: {added}. "
            "Regenerate with `python -m tests.test_api_vocabulary`, then give "
            "each one a name in both dictionaries."
        )
        assert not removed, (
            f"{field}: in the frontend's copy and no longer in the API: {removed}. "
            "Regenerate, and drop the dictionary entries that are now dead."
        )


def test_every_metric_has_an_english_label() -> None:
    """`metric_label` must produce a readable label for every key.

    It is the fallback the interface shows for a key no dictionary knows yet,
    so a key that falls through the override table and comes out still
    carrying its underscores reaches a reader as `aerial_duel_win_percentage`.

    Capitalisation is deliberately not asserted: `xG /90` and `xA /90` are
    notation and begin lower case on purpose.
    """
    from app.api.v1.players import metric_label

    for metric in DerivedMetric:
        label = metric_label(metric.value)
        assert label, f"{metric.value} has no label"
        assert "_" not in label, f"{metric.value} -> {label!r} still carries its underscores"


if __name__ == "__main__":  # pragma: no cover - regeneration helper
    VOCABULARY_PATH.write_bytes(
        (json.dumps(current(), indent=2) + "\n").encode("utf-8"),
    )
    print(f"wrote {VOCABULARY_PATH}")
