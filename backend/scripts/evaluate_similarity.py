"""Compare percentile and z-score feature representations.

Run from backend/:
    python -m scripts.evaluate_similarity

The spec (section 12) asks which representation "provides more stable results",
so this measures it rather than picking one and asserting.

TWO THINGS ARE MEASURED

**Stability.** A player's metrics are perturbed by a few percent — the scale of
disagreement two providers would show for the same player — and their top-10
similar list is recomputed. The overlap with the unperturbed list says how much
a small change in the input moves the answer. A representation that reshuffles
its results when a number moves 3% cannot be trusted to rank strangers.

**Discrimination.** If every pair scores 95, the index is not saying anything.
The spread between the best match and the tenth tells whether the ranking has
content.

Reads only. No database, no network.
"""

from __future__ import annotations

import random
import statistics
import sys

from app.analytics.metrics import DerivedMetric, DerivedMetrics, compute_derived
from app.analytics.percentiles import PercentileEngine, PlayerMetrics
from app.analytics.similarity import (
    FeatureRepresentation,
    SimilarityCandidate,
    SimilarityEngine,
)
from app.providers.mock import SEASON_ID, MockPerformanceProvider
from app.schemas.canonical import PositionGroup

SAMPLE_PLAYERS = 120
TOP_N = 10
#: Relative noise applied to each metric. Chosen to match the scale of
#: disagreement two providers show for the same player, not to break the engine.
NOISE = 0.03


def build() -> tuple[dict[str, PlayerMetrics], dict[str, SimilarityCandidate]]:
    provider = MockPerformanceProvider()
    players: dict[str, PlayerMetrics] = {}
    candidates: dict[str, SimilarityCandidate] = {}

    for competition in provider.get_competitions():
        squad = provider.get_players(competition.competition_id, SEASON_ID)
        groups = {p.source_player_id: p.position_group for p in squad}
        names = {p.source_player_id: p.full_name for p in squad}
        clubs = {p.source_player_id: p.club_id for p in squad}
        births = {p.source_player_id: p.date_of_birth for p in squad}

        for record in provider.get_competition_stats(competition.competition_id, SEASON_ID):
            key = record.source_player_id
            players[key] = PlayerMetrics(
                player_key=key,
                position_group=groups[key],
                competition_id=record.competition_id,
                season_id=record.season_id,
                metrics=compute_derived(record),
            )
            birth = births[key]
            candidates[key] = SimilarityCandidate(
                player_key=key,
                display_name=names[key],
                position_group=groups[key],
                competition_id=record.competition_id,
                club_id=clubs[key],
                age=(2027 - birth.year) if birth else None,
            )
    return players, candidates


def perturb(record: PlayerMetrics, rng: random.Random) -> PlayerMetrics:
    """A copy of the player with every metric nudged by a few percent."""
    updates: dict[str, float] = {}
    for metric in DerivedMetric:
        value = record.metrics.get(metric)
        if value is not None:
            updates[metric.value] = max(0.0, value * (1.0 + rng.gauss(0.0, NOISE)))
    return PlayerMetrics(
        player_key=record.player_key,
        position_group=record.position_group,
        competition_id=record.competition_id,
        season_id=record.season_id,
        metrics=DerivedMetrics(minutes=record.minutes, **updates),  # type: ignore[arg-type]
    )


def assess(
    representation: FeatureRepresentation,
    players: dict[str, PlayerMetrics],
    candidates: dict[str, SimilarityCandidate],
    percentiles: PercentileEngine,
    sample: list[str],
    rng: random.Random,
) -> tuple[float, float, float, float]:
    """Return (mean overlap, mean top score, mean spread, mean self-similarity)."""
    engine = SimilarityEngine(
        percentiles, candidates, players=players, representation=representation
    )

    overlaps: list[float] = []
    tops: list[float] = []
    spreads: list[float] = []
    selves: list[float] = []

    for key in sample:
        baseline = engine.similar_to(key, limit=TOP_N, minimum_minutes=900)
        if len(baseline) < TOP_N:
            continue
        tops.append(baseline[0].similarity)
        spreads.append(baseline[0].similarity - baseline[-1].similarity)

        # A perturbed copy of the player, inserted alongside the real one. It
        # should come back as the most similar player in the database.
        twin_key = f"{key}__twin"
        twin_players = dict(players)
        twin_candidates = dict(candidates)
        twin_players[twin_key] = perturb(players[key], rng)
        twin_candidates[twin_key] = SimilarityCandidate(
            player_key=twin_key,
            display_name="twin",
            position_group=candidates[key].position_group,
            competition_id=candidates[key].competition_id,
        )
        twin_engine = SimilarityEngine(
            percentiles, twin_candidates, players=twin_players, representation=representation
        )
        twin_results = twin_engine.similar_to(key, limit=TOP_N, minimum_minutes=900)
        if twin_results:
            selves.append(
                twin_results[0].similarity
                if twin_results[0].candidate.player_key == twin_key
                else 0.0
            )

        # Stability: does the ranking survive the same noise applied to the
        # target rather than to a twin?
        shifted_players = dict(players)
        shifted_players[key] = perturb(players[key], rng)
        shifted_engine = SimilarityEngine(
            percentiles, candidates, players=shifted_players, representation=representation
        )
        shifted = shifted_engine.similar_to(key, limit=TOP_N, minimum_minutes=900)
        if shifted:
            before = {r.candidate.player_key for r in baseline}
            after = {r.candidate.player_key for r in shifted}
            overlaps.append(len(before & after) / len(before | after))

    return (
        statistics.mean(overlaps) if overlaps else 0.0,
        statistics.mean(tops) if tops else 0.0,
        statistics.mean(spreads) if spreads else 0.0,
        statistics.mean(selves) if selves else 0.0,
    )


def main() -> int:
    rng = random.Random(20260827)  # noqa: S311 - reproducible evaluation, not security
    players, candidates = build()
    percentiles = PercentileEngine(list(players.values()))

    eligible = [
        key
        for key, record in players.items()
        if (record.minutes or 0) >= 900 and record.position_group is not PositionGroup.GK
    ]
    rng.shuffle(eligible)
    sample = eligible[:SAMPLE_PLAYERS]

    print("=" * 78)
    print("SIMILARITY: PERCENTILE vs Z-SCORE")
    print("=" * 78)
    print(f"players            {len(players):,}")
    print(f"sampled            {len(sample)}")
    print(f"top-N compared     {TOP_N}")
    print(f"perturbation       {NOISE:.0%} relative noise on every metric")

    print(f"\n  {'representation':<16}{'stability':>11}{'top match':>11}{'spread':>9}{'twin':>8}")
    outcomes: dict[FeatureRepresentation, tuple[float, float, float, float]] = {}
    for representation in FeatureRepresentation:
        overlap, top, spread, twin = assess(
            representation, players, candidates, percentiles, sample, rng
        )
        outcomes[representation] = (overlap, top, spread, twin)
        print(f"  {representation.value:<16}{overlap:>10.1%}{top:>11.1f}{spread:>9.1f}{twin:>8.1f}")

    print(
        "\n  stability  overlap of the top-10 list before and after perturbation"
        "\n  top match  similarity of the single closest player"
        "\n  spread     gap between the closest and the tenth"
        "\n  twin       similarity to a perturbed copy of the player themselves"
    )

    percentile_stability = outcomes[FeatureRepresentation.PERCENTILE][0]
    zscore_stability = outcomes[FeatureRepresentation.ZSCORE][0]
    winner = (
        FeatureRepresentation.PERCENTILE
        if percentile_stability >= zscore_stability
        else FeatureRepresentation.ZSCORE
    )
    margin = abs(percentile_stability - zscore_stability)

    print(f"\nMORE STABLE: {winner.value}  (by {margin:.1%})")
    print(
        "\nWhy this is the expected outcome: percentiles are ranks, so a small\n"
        "change in a metric usually moves a player past nobody, or past one\n"
        "neighbour. A z-score moves continuously with the raw value and is\n"
        "pulled by outliers in the tail, which football metrics have plenty of."
    )

    failures = 0
    for representation, (_overlap, _top, spread, twin) in outcomes.items():
        if twin < 95.0:
            print(
                f"\nFAIL: {representation.value} does not recognise a near-identical twin ({twin:.1f})"
            )
            failures += 1
        if spread < 1.0:
            print(
                f"\nFAIL: {representation.value} does not separate the top ten (spread {spread:.1f})"
            )
            failures += 1

    print("\n" + "=" * 78)
    if failures:
        print(f"REVIEW: {failures} issue(s)")
        return 1
    print("OK: both representations recognise near-identical profiles and rank with content")
    return 0


if __name__ == "__main__":
    sys.exit(main())
