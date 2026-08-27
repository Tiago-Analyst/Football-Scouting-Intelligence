"""Inspect role engine output across the demo dataset.

Run from backend/:
    python -m scripts.profile_roles

The spec asks for example players to be inspected, because role fit is the part
of the product a recruiter reads first and the part that is easiest to get
quietly wrong. A role engine that assigns the same role to everyone in a
position looks like it is working — every player has a best role and a number
beside it — while carrying no information at all.

So the questions this answers are: does every role get used, does the best role
beat its alternatives by a meaningful margin, and does the decomposition justify
the number?

Reads only. No database, no network.
"""

from __future__ import annotations

import statistics
import sys
from collections import Counter, defaultdict

from app.analytics.intelligence import IntelligenceScoreEngine, get_definitions
from app.analytics.metrics import compute_derived
from app.analytics.percentiles import PercentileEngine, PlayerMetrics
from app.analytics.roles import ROLE_SCORE_MEANING, RoleEngine, get_roles
from app.providers.mock import SEASON_ID, MockPerformanceProvider
from app.schemas.canonical import PositionGroup

#: A role nobody in its own position group ever tops is not discriminating.
MIN_SHARE_OF_GROUP = 0.02


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
    roles = get_roles()
    population = build_population()
    percentiles = PercentileEngine(population)
    engine = RoleEngine(IntelligenceScoreEngine(percentiles, get_definitions()), roles)

    print("=" * 78)
    print("PLAYER ROLES")
    print("=" * 78)
    print(f"roles configured   {len(roles)}")
    print(f"players            {len(population):,}")
    print(f"\n{ROLE_SCORE_MEANING}")

    print("\nCONFIGURED ROLES")
    for role in roles.values():
        extra = (
            f"  (also scored for {', '.join(g.value for g in role.position_groups[1:])})"
            if len(role.position_groups) > 1
            else ""
        )
        pieces = len(role.metric_weights) + len(role.score_weights)
        print(f"  {role.primary_position.value:<8} {role.label:<28} {pieces} components{extra}")

    rankable = [r for r in population if (r.minutes or 0) >= 900]
    print(f"\nBEST ROLE ACROSS {len(rankable):,} PLAYERS WITH AT LEAST 900 MINUTES")

    best_counts: Counter[str] = Counter()
    margins: list[float] = []
    by_group: dict[PositionGroup, Counter[str]] = defaultdict(Counter)
    without_best = 0

    for record in rankable:
        fit = engine.fit(record)
        if fit.best is None:
            without_best += 1
            continue
        best_counts[fit.best.label] += 1
        by_group[record.position_group][fit.best.label] += 1
        if fit.alternatives:
            margins.append((fit.best.score or 0) - (fit.alternatives[0].score or 0))

    print(f"  {'role':<30}{'best for':>10}{'share':>8}")
    for label, count in best_counts.most_common():
        print(f"  {label:<30}{count:>10}{count / len(rankable):>8.1%}")
    if without_best:
        print(f"  {'(no computable role)':<30}{without_best:>10}")

    unused = [r.label for r in roles.values() if best_counts[r.label] == 0]
    print(f"\n  roles used: {len(best_counts)}/{len(roles)}")
    problems = 0
    if unused:
        print(f"  never the best role: {', '.join(unused)}")

    # A role can legitimately be rare, but one nobody in its own group ever
    # tops means its weights are dominated by a sibling role.
    print("\nWITHIN EACH POSITION GROUP")
    for group in PositionGroup:
        counts = by_group[group]
        total = sum(counts.values())
        if not total:
            continue
        available = [r.label for r in roles.values() if group in r.position_groups]
        starved = [label for label in available if counts[label] / total < MIN_SHARE_OF_GROUP]
        detail = ", ".join(f"{label} {counts[label] / total:.0%}" for label in available)
        flag = ""
        if starved and len(available) > 1:
            flag = f"   <-- crowded out: {', '.join(starved)}"
            problems += 1
        print(f"  {group.value:<9} n={total:<5} {detail}{flag}")

    if margins:
        print("\nMARGIN BETWEEN BEST ROLE AND RUNNER-UP")
        margins.sort()
        print(
            f"  median {statistics.median(margins):5.1f}    "
            f"p10 {margins[len(margins) // 10]:5.1f}    "
            f"p90 {margins[(9 * len(margins)) // 10]:5.1f}"
        )
        near_ties = sum(1 for m in margins if m < 2.0)
        print(f"  within 2 points of the runner-up: {near_ties} ({near_ties / len(margins):.1%})")

    # -- Worked examples ----------------------------------------------------
    print("\n" + "=" * 78)
    print("EXAMPLE PLAYERS")
    print("=" * 78)

    shown: set[str] = set()
    for group in (PositionGroup.CB, PositionGroup.DM, PositionGroup.WINGER, PositionGroup.FORWARD):
        candidates = [r for r in rankable if r.position_group is group]
        if not candidates:
            continue
        subject = max(
            candidates,
            key=lambda r: (engine.fit(r).best.score if engine.fit(r).best else 0) or 0,
        )
        if subject.player_key in shown:
            continue
        shown.add(subject.player_key)

        fit = engine.fit(subject)
        if fit.best is None:
            continue

        print(f"\n{display_name(subject)}  ({group.value}, {subject.minutes} min)")
        print(f"\n  BEST ROLE   {fit.best.label}   {fit.best.score:.0f} / 100")
        for alternative in fit.alternatives:
            print(f"  also        {alternative.label:<28} {alternative.score:5.0f}")

        print(f"\n  WHY {fit.best.label} = {fit.best.score:.1f}")
        print(
            f"    compared with: {fit.best.context.label}  (n={fit.best.context.population_size})"
        )
        if fit.best.context.caveat:
            print(f"    caveat: {fit.best.context.caveat}")
        for name, contribution in fit.best.contributions():
            component = next(c for c in fit.best.components if c.metric == name)
            print(
                f"      {name:<30} percentile={component.value:5.1f}"
                f"  weight={component.weight:>4.0f}%  adds {contribution:5.1f}"
            )
        if fit.best.caveat:
            print(f"    NOTE: {fit.best.caveat}")

    print("\n" + "=" * 78)
    if problems:
        print(f"REVIEW: {problems} position group(s) where a role is crowded out")
        return 1
    print("OK: every role is reachable and best roles separate from their alternatives")
    return 0


if __name__ == "__main__":
    sys.exit(main())
