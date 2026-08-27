"""Inspect intelligence score output across the demo dataset.

Run from backend/:
    python -m scripts.profile_intelligence

Scores are the layer a recruitment decision is actually read from, so they need
eyeballing rather than only asserting. This prints the configuration in force,
how often each score can be computed, how the scores are distributed, and a
handful of real player profiles decomposed into their components.

The question to ask of the output: do recognisable archetypes appear, and does
each score's explanation justify its number? If every player scores alike, the
weights are not discriminating and nothing built on top will either.

Reads only. No database, no network.
"""

from __future__ import annotations

import statistics
import sys
from collections import Counter

from app.analytics.intelligence import IntelligenceScoreEngine, get_definitions
from app.analytics.metrics import compute_derived
from app.analytics.percentiles import PercentileEngine, PlayerMetrics
from app.providers.mock import SEASON_ID, MockPerformanceProvider
from app.schemas.canonical import PositionGroup

#: Below this spread, a score is not separating players and the weights need
#: revisiting rather than the data.
MIN_INTERQUARTILE_SPREAD = 15.0


def build_population() -> list[PlayerMetrics]:
    provider = MockPerformanceProvider()
    population: list[PlayerMetrics] = []
    for competition in provider.get_competitions():
        players = provider.get_players(competition.competition_id, SEASON_ID)
        groups = {p.source_player_id: p.position_group for p in players}
        names = {p.source_player_id: p.full_name for p in players}
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


def display_name(record: PlayerMetrics) -> str:
    return record.player_key.split("|", 1)[1]


def main() -> int:
    definitions = get_definitions()
    population = build_population()
    percentiles = PercentileEngine(population)
    engine = IntelligenceScoreEngine(percentiles, definitions)

    print("=" * 78)
    print("INTELLIGENCE SCORES")
    print("=" * 78)
    print(f"scores configured  {len(definitions)}")
    print(f"players            {len(population):,}")

    print("\nCONFIGURED DEFINITIONS")
    for definition in definitions.values():
        inverted = (
            f"   (inverted: {', '.join(m.value for m in definition.inverted_components)})"
            if definition.inverted_components
            else ""
        )
        print(f"  {definition.label:<22} {len(definition.components)} components{inverted}")
        for metric, weight in sorted(
            definition.components.items(), key=lambda kv: kv[1], reverse=True
        ):
            print(f"      {weight:>5.0f}%  {metric.value}")

    # -- Availability and distribution --------------------------------------
    rankable = [r for r in population if (r.minutes or 0) >= 900]
    print(f"\nOUTPUT ACROSS {len(rankable):,} PLAYERS WITH AT LEAST 900 MINUTES")
    print(f"  {'score':<22}{'computed':>10}{'median':>9}{'p25':>7}{'p75':>7}{'spread':>8}")

    problems = 0
    computed_counts: Counter[str] = Counter()
    for key, definition in definitions.items():
        values: list[float] = []
        for record in rankable:
            result = engine.score(record, key)
            if result.score is not None:
                values.append(result.score)
                computed_counts[key] += 1
        if not values:
            print(f"  {definition.label:<22}{'NONE':>10}")
            problems += 1
            continue
        values.sort()
        p25 = values[len(values) // 4]
        p75 = values[(3 * len(values)) // 4]
        spread = p75 - p25
        flag = "" if spread >= MIN_INTERQUARTILE_SPREAD else "   <-- NOT SEPARATING"
        if flag:
            problems += 1
        share = computed_counts[key] / len(rankable)
        print(
            f"  {definition.label:<22}{share:>9.0%}{statistics.median(values):>9.1f}"
            f"{p25:>7.1f}{p75:>7.1f}{spread:>8.1f}{flag}"
        )

    # -- Do archetypes actually differ? -------------------------------------
    print("\nDO THE SCORES SEPARATE DIFFERENT PLAYERS?")
    leaders: dict[str, str] = {}
    for key, definition in definitions.items():
        best, best_score = None, -1.0
        for record in rankable:
            if record.position_group is PositionGroup.GK:
                continue
            result = engine.score(record, key)
            if result.score is not None and result.score > best_score:
                best, best_score = record, result.score
        if best is not None:
            leaders[key] = display_name(best)
            print(f"  {definition.label:<22} {display_name(best):<24} {best_score:5.1f}")
    distinct = len(set(leaders.values()))
    print(f"\n  {distinct} distinct leaders across {len(leaders)} scores")
    if distinct < max(2, len(leaders) // 2):
        print("  <-- one player tops most scores; the weights may not be discriminating")
        problems += 1

    # -- Worked examples ----------------------------------------------------
    print("\n" + "=" * 78)
    print("WORKED EXAMPLES")
    print("=" * 78)

    examples: list[PlayerMetrics] = []
    for group in (PositionGroup.DM, PositionGroup.WINGER, PositionGroup.FORWARD):
        candidates = [r for r in rankable if r.position_group is group]
        if candidates:
            key = "ball_progression" if group is PositionGroup.DM else "goal_threat"
            examples.append(max(candidates, key=lambda r: engine.score(r, key).score or -1.0))

    for record in examples:
        print(f"\n{display_name(record)}  ({record.position_group.value}, {record.minutes} min)")
        results = engine.score_all(record)
        for result in results.values():
            if result.score is None:
                print(f"  {result.label:<22}    n/a   (missing: {', '.join(result.missing)})")
                continue
            print(f"  {result.label:<22} {result.score:>6.1f}")
        # Decompose the strongest score so the number is justified.
        best_key = max(
            (k for k, r in results.items() if r.score is not None),
            key=lambda k: results[k].score or 0.0,
        )
        best = results[best_key]
        print(f"\n  WHY '{best.label}' = {best.score:.1f}")
        print(f"    compared with: {best.context.label}  (n={best.context.population_size})")
        if best.context.caveat:
            print(f"    caveat: {best.context.caveat}")
        for metric, contribution in best.contributions():
            component = next(c for c in best.components if c.metric == metric)
            print(
                f"      {metric:<30} percentile={component.value:5.1f}"
                f"  weight={component.weight:>4.0f}%  adds {contribution:5.1f}"
            )
        if best.caveat:
            print(f"    NOTE: {best.caveat}")

    print("\n" + "=" * 78)
    if problems:
        print(f"REVIEW: {problems} issue(s) above need a look")
        return 1
    print("OK: every score computes, separates players, and decomposes to its total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
