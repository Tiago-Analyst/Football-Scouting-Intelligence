"""Inspect percentile output across the demo dataset.

Run from backend/:
    python -m scripts.profile_percentiles

Percentiles are the layer every score, role and recruitment ranking is built on,
and a mistake here is invisible downstream: a wrongly-scoped population produces
numbers that look entirely reasonable and rank the wrong players. This prints
the population sizes, checks the distribution behaves, and shows the same player
measured against all three comparison contexts.

Reads only. No database, no network.
"""

from __future__ import annotations

import statistics
import sys
from collections import defaultdict

from app.analytics.metrics import DerivedMetric, compute_derived
from app.analytics.percentiles import (
    MIN_POPULATION,
    PercentileEngine,
    PercentileScope,
    PlayerMetrics,
)
from app.analytics.sample import classify_minutes
from app.providers.mock import SEASON_ID, MockPerformanceProvider
from app.schemas.canonical import PositionGroup

SHOWN_METRICS = [
    DerivedMetric.PROGRESSIVE_PASSES_PER90,
    DerivedMetric.PASS_COMPLETION,
    DerivedMetric.KEY_PASSES_PER90,
    DerivedMetric.TACKLES_PER90,
    DerivedMetric.INTERCEPTIONS_PER90,
    DerivedMetric.DUEL_WIN_PERCENTAGE,
    DerivedMetric.NPXG_PER90,
    DerivedMetric.DISPOSSESSED_PER90,
]


def build_population(provider: MockPerformanceProvider) -> list[PlayerMetrics]:
    population: list[PlayerMetrics] = []
    for competition in provider.get_competitions():
        groups = {
            p.source_player_id: p.position_group
            for p in provider.get_players(competition.competition_id, SEASON_ID)
        }
        names = {
            p.source_player_id: p.full_name
            for p in provider.get_players(competition.competition_id, SEASON_ID)
        }
        for record in provider.get_competition_stats(competition.competition_id, SEASON_ID):
            population.append(
                PlayerMetrics(
                    player_key=f"{record.source_player_id}|{names[record.source_player_id]}",
                    position_group=groups[record.source_player_id],
                    competition_id=record.competition_id,
                    season_id=record.season_id,
                    metrics=compute_derived(record),
                )
            )
    return population


def main() -> int:
    provider = MockPerformanceProvider()
    population = build_population(provider)
    engine = PercentileEngine(population)

    print("=" * 78)
    print("PERCENTILE ENGINE")
    print("=" * 78)
    print(f"players in dataset     {len(population):,}")
    print(f"eligible for reference {engine.eligible_count:,}  (meet the minutes threshold)")
    print(f"minimum population     {MIN_POPULATION}")

    # -- Population sizes ---------------------------------------------------
    by_scope: dict[tuple[PositionGroup, str], int] = defaultdict(int)
    global_by_group: dict[PositionGroup, int] = defaultdict(int)
    for record in population:
        if classify_minutes(record.minutes).value == "insufficient":
            continue
        by_scope[(record.position_group, record.competition_id)] += 1
        global_by_group[record.position_group] += 1

    print("\nREFERENCE POPULATION BY POSITION GROUP")
    print(f"  {'group':<10}{'per competition':>18}{'global':>10}   {'usable?':<8}")
    thin = 0
    for group in PositionGroup:
        per_competition = [count for (g, _), count in by_scope.items() if g is group]
        smallest = min(per_competition) if per_competition else 0
        usable = "yes" if smallest >= MIN_POPULATION else "TOO SMALL"
        if smallest < MIN_POPULATION:
            thin += 1
        print(
            f"  {group.value:<10}{f'{smallest}-{max(per_competition or [0])}':>18}"
            f"{global_by_group[group]:>10}   {usable:<8}"
        )

    # -- Distribution sanity ------------------------------------------------
    print("\nDISTRIBUTION CHECK (median player should rank near the 50th percentile)")
    problems = 0
    for metric in SHOWN_METRICS:
        ranks = []
        for record in population:
            if record.metrics.get(metric) is None:
                continue
            result = engine.rank(record, metric)
            if result.percentile is not None:
                ranks.append(result.percentile)
        if not ranks:
            continue
        median = statistics.median(ranks)
        low, high = min(ranks), max(ranks)
        flag = "" if 40 <= median <= 60 else "   <-- SKEWED"
        if flag:
            problems += 1
        print(
            f"  {metric.value:<28} median={median:6.1f}  min={low:5.1f}  max={high:5.1f}"
            f"  n={len(ranks):>5}{flag}"
        )

    # -- The same player in three contexts ----------------------------------
    eligible = [
        r
        for r in population
        if r.position_group is PositionGroup.DM
        and (r.minutes or 0) >= 900
        and r.metrics.get(DerivedMetric.PROGRESSIVE_PASSES_PER90) is not None
    ]
    subject = max(
        eligible, key=lambda r: r.metrics.get(DerivedMetric.PROGRESSIVE_PASSES_PER90) or 0
    )
    all_competitions = frozenset(r.competition_id for r in population)
    two_leagues = frozenset(sorted(all_competitions)[:2]) | {subject.competition_id}

    print("\nSAME PLAYER, THREE COMPARISON CONTEXTS")
    print(f"  player   {subject.player_key.split('|')[1]}  ({subject.position_group.value})")
    print(f"  minutes  {subject.minutes}")

    for scope, competitions in [
        (PercentileScope.COMPETITION, None),
        (PercentileScope.LEAGUE_GROUP, two_leagues),
        (PercentileScope.GLOBAL, None),
    ]:
        print(f"\n  --- {scope.value} ---")
        first = True
        for metric in SHOWN_METRICS:
            result = engine.rank(subject, metric, scope=scope, competition_ids=competitions)
            if first:
                print(f"      compared with: {result.context.label}")
                print(f"      population:    {result.context.population_size}")
                if result.context.caveat:
                    print(f"      caveat:        {result.context.caveat}")
                first = False
            if result.percentile is None:
                continue
            arrow = " (lower is better)" if result.lower_is_better else ""
            print(
                f"      {metric.value:<28} value={result.value:8.2f}  "
                f"percentile={result.percentile:5.1f}  scoring={result.oriented:5.1f}{arrow}"
            )

    print("\n" + ("=" * 78))
    if thin or problems:
        print(f"REVIEW: {thin} thin position group(s), {problems} skewed distribution(s)")
        return 1
    print("OK: populations are large enough and distributions are centred")
    return 0


if __name__ == "__main__":
    sys.exit(main())
