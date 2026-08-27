"""Profile the generated demo dataset.

Run:
    python -m scripts.profile_mock_data          (from backend/)

Prints the shape of the mock universe and the per-90 distribution of each key
metric by position group. The point is to make the generated data inspectable:
a centre-back posting 40 progressive passes per 90 would silently wreck every
role score built on top of it, and a table like this is how that gets caught.

Reads only. Writes nothing, touches no database, makes no network call.
"""

from __future__ import annotations

import statistics
import sys
from collections import Counter, defaultdict

from app.providers.mock import MockPerformanceProvider
from app.schemas.canonical import PlayerSeasonStats, PositionGroup

SEASON = "2026-2027"

# Metric, label, and the per-90 ceiling a competent analyst would expect.
# There is no lower bound: a metric can legitimately be near zero for a
# position group (crosses for a centre-back), so only the top is checkable.
EXPECTED_PER90: list[tuple[str, str, float]] = [
    ("passes", "Passes", 90.0),
    ("progressive_passes", "Prog. passes", 12.0),
    ("key_passes", "Key passes", 4.5),
    ("crosses", "Crosses", 8.0),
    ("successful_dribbles", "Succ. dribbles", 6.0),
    ("tackles", "Tackles", 5.5),
    ("interceptions", "Interceptions", 4.5),
    ("clearances", "Clearances", 10.0),
    ("duels", "Duels", 20.0),
    ("aerial_duels", "Aerial duels", 9.0),
    ("shots", "Shots", 7.0),
    ("npxg", "npxG", 1.2),
    ("xa", "xA", 1.0),
    ("dispossessed", "Dispossessed", 6.0),
]

# Ratios that are impossible outside 0-1 and would corrupt any percentile.
RATIOS: list[tuple[str, str, str]] = [
    ("Pass completion", "passes_completed", "passes"),
    ("Dribble success", "successful_dribbles", "dribbles"),
    ("Tackle success", "successful_tackles", "tackles"),
    ("Duels won", "duels_won", "duels"),
    ("Aerial won", "aerial_duels_won", "aerial_duels"),
    ("Shot accuracy", "shots_on_target", "shots"),
]

MIN_MINUTES_FOR_RATES = 900


def per90(stats: PlayerSeasonStats, metric: str) -> float | None:
    value = getattr(stats, metric)
    minutes = stats.minutes
    if value is None or not minutes:
        return None
    return value * 90.0 / minutes


def main() -> int:
    provider = MockPerformanceProvider()
    info = provider.info

    print("=" * 78)
    print("MOCK PERFORMANCE DATASET")
    print("=" * 78)
    print(f"provider        : {info.name}")
    print(f"is_mock         : {info.is_mock}")
    print(f"validated       : {info.validated}")
    print(f"metrics offered : {len(info.available_metrics)}")
    print(f"note            : {info.notes}")

    competitions = provider.get_competitions()
    all_stats: list[PlayerSeasonStats] = []
    by_group: dict[PositionGroup, list[PlayerSeasonStats]] = defaultdict(list)
    group_of: dict[str, PositionGroup] = {}

    print(f"\ncompetitions    : {len(competitions)}")
    for competition in competitions:
        players = provider.get_players(competition.competition_id, SEASON)
        stats = provider.get_competition_stats(competition.competition_id, SEASON)
        clubs = provider.get_clubs(competition.competition_id, SEASON)
        for player in players:
            group_of[player.source_player_id] = player.position_group
        all_stats.extend(stats)
        print(
            f"  {competition.name:<22} {competition.country:<12} "
            f"clubs={len(clubs):<3} players={len(players)}"
        )

    for record in all_stats:
        by_group[group_of[record.source_player_id]].append(record)

    print(f"\ntotal players   : {len(all_stats)}")

    # -- Sample-size bands ---------------------------------------------------
    bands = Counter()
    for record in all_stats:
        minutes = record.minutes or 0
        bands[
            "full (>=900)"
            if minutes >= 900
            else "low (450-899)"
            if minutes >= 450
            else "insufficient (<450)"
        ] += 1
    print("\nSAMPLE-SIZE BANDS")
    for band, count in sorted(bands.items()):
        print(f"  {band:<22} {count:>5}  ({count / len(all_stats):.0%})")

    # -- Consistency ---------------------------------------------------------
    violations = [(r.source_player_id, e) for r in all_stats if (e := r.consistency_errors())]
    print(f"\nCONSISTENCY VIOLATIONS: {len(violations)}")
    for player_id, errors in violations[:10]:
        print(f"  {player_id}: {'; '.join(errors)}")

    # -- Ratio bounds --------------------------------------------------------
    print("\nRATIO BOUNDS (must all sit within 0-1)")
    ratio_problems = 0
    for label, part_name, whole_name in RATIOS:
        values = []
        for record in all_stats:
            whole = getattr(record, whole_name)
            part = getattr(record, part_name)
            if whole:
                values.append(part / whole)
        if not values:
            continue
        low, high = min(values), max(values)
        flag = "" if low >= 0.0 and high <= 1.0 else "   <-- OUT OF BOUNDS"
        ratio_problems += 0 if not flag else 1
        print(
            f"  {label:<18} min={low:5.3f}  median={statistics.median(values):5.3f}  max={high:5.3f}{flag}"
        )

    # -- Per-90 by position group -------------------------------------------
    print(f"\nPER-90 MEDIANS BY POSITION GROUP (players with >={MIN_MINUTES_FOR_RATES} minutes)")
    groups = [g for g in PositionGroup]
    header = f"  {'Metric':<16}" + "".join(f"{g.value:>9}" for g in groups)
    print(header)
    print("  " + "-" * (len(header) - 2))

    out_of_range: list[str] = []
    for metric, label, hi in EXPECTED_PER90:
        cells = []
        for group in groups:
            values = [
                v
                for record in by_group[group]
                if (record.minutes or 0) >= MIN_MINUTES_FOR_RATES
                and (v := per90(record, metric)) is not None
            ]
            if not values:
                cells.append(f"{'-':>9}")
                continue
            median = statistics.median(values)
            cells.append(f"{median:>9.2f}")
            p99 = sorted(values)[int(len(values) * 0.99) - 1]
            if p99 > hi or median < 0:
                out_of_range.append(
                    f"{label} / {group.value}: 99th pct {p99:.2f} exceeds expected max {hi:.2f}"
                )
        print(f"  {label:<16}" + "".join(cells))

    print(f"\nPLAUSIBILITY FLAGS: {len(out_of_range)}")
    for line in out_of_range:
        print(f"  {line}")

    failed = bool(violations) or ratio_problems > 0
    print(
        "\n"
        + (
            "FAILED: dataset is not internally consistent"
            if failed
            else "OK: dataset is internally consistent"
        )
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
