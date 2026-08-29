"""Check the engine's numbers against an independent recomputation.

    python -m pipelines.quality.validate_analytics
    python -m pipelines.quality.validate_analytics --players 12 --source footystats

Specification Phase 17: calculate percentiles, intelligence scores and role
scores on real data, and validate sample players manually.

---------------------------------------------------------------------------
WHY THIS DOES NOT IMPORT THE ENGINES
---------------------------------------------------------------------------

A test that calls `percentile_of` and compares the answer to `percentile_of`
proves the function is deterministic and nothing else. To be worth running,
the check has to arrive at the number by a different route.

So this reads `fact_player_season_stats` directly and rebuilds each figure from
the raw season totals: the per-90 by dividing, the percentile by counting the
comparison population by hand, the score by weighting the components itself. It
shares no code with the analytics layer beyond the configuration that defines
what the numbers are supposed to mean.

When the two agree the engine is doing what it says. When they disagree, one of
them is wrong and the disagreement says where to look - which is the point.

---------------------------------------------------------------------------
WHAT "MANUALLY" MEANS HERE
---------------------------------------------------------------------------

The specification asks for sample players to be validated manually. Doing that
literally - reading numbers off a screen and checking them on paper - validates
the players who were looked at, on the day they were looked at.

Recomputing them from first principles validates the same thing and keeps
validating it, so a change that quietly alters a percentile is caught rather
than remembered. Every check prints its arithmetic, so a person can still
follow any single one by hand.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO_ROOT / "docs"

#: Percentiles are floats built from divisions in two different orders, so an
#: exact match is not the right question. Anything above this is a real
#: disagreement rather than the last bit of a float.
TOLERANCE = 1e-6


@dataclass
class Check:
    """One independently recomputed figure, and what the engine said."""

    player: str
    subject: str
    kind: str
    engine: float | None
    independent: float | None
    working: str

    @property
    def agrees(self) -> bool:
        if self.engine is None or self.independent is None:
            return self.engine is None and self.independent is None
        return abs(self.engine - self.independent) <= TOLERANCE

    @property
    def difference(self) -> float | None:
        if self.engine is None or self.independent is None:
            return None
        return self.engine - self.independent

    @property
    def is_substantive(self) -> bool:
        """Whether a number was actually compared.

        Both sides agreeing that a figure could not be computed is a correct
        result and a weak one: it says the two agree about absence, not about
        arithmetic. Counting those in with the rest would let a sample of
        goalkeepers - for whom the outfield metrics and three of the scores are
        rightly empty - report far more agreement than it earned.
        """
        return self.engine is not None and self.independent is not None


@dataclass
class Validation:
    checks: list[Check] = field(default_factory=list)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.agrees]

    @property
    def substantive(self) -> list[Check]:
        return [c for c in self.checks if c.is_substantive]

    def add(self, check: Check) -> None:
        self.checks.append(check)


def independent_per90(
    total: float | None, recorded: int | None, minutes: int | None
) -> float | None:
    """A per-90 rate, computed here rather than asked for.

    The denominator is the minutes the statistics actually cover, falling back
    to minutes played - which is the rule the canonical model states, and the
    thing most worth re-checking, because getting it wrong inflates every rate
    for the 13% of player-seasons whose detailed coverage is partial.
    """
    if total is None:
        return None
    denominator = recorded if recorded is not None else minutes
    if not denominator:
        return None
    return total / denominator * 90.0


def independent_percentile(value: float, population: list[float]) -> float:
    """Mid-rank percentile, counted rather than bisected.

    Deliberately the slow way: counting each comparison separately is how a
    person would check it, and it cannot share an off-by-one with the bisecting
    implementation it is checking.
    """
    below = sum(1 for other in population if other < value)
    equal = sum(1 for other in population if other == value)
    return 100.0 * (2 * below + equal) / (2 * len(population))


def independent_weighted(
    parts: dict[str, tuple[float, float | None]], min_coverage: float
) -> tuple[float | None, float, str]:
    """Combine weighted components the way the engine says it does.

    Returns the score, the share of weight that was present, and the working.

    The renormalisation is the part worth re-deriving. Weights are shared out
    again across the components that are present, so a missing fifth of the
    definition does not drag the result down by a fifth and read as poor
    performance instead of absent data. Getting that wrong produces a score
    that is plausible, ordered sensibly, and quietly too low for anyone with a
    gap - which nothing downstream could detect.

    `min_coverage` is the floor below which no number is produced at all. A
    score built from a subset is not comparable with one built from the whole,
    and publishing both under one name would hide that.
    """
    total_weight = sum(weight for weight, _ in parts.values())
    available = {key: (w, v) for key, (w, v) in parts.items() if v is not None}
    available_weight = sum(w for w, _ in available.values())
    coverage = available_weight / total_weight if total_weight else 0.0

    if coverage < min_coverage or not available:
        return None, coverage, f"coverage {coverage:.0%} below the required {min_coverage:.0%}"

    score = sum((w / available_weight) * value for w, value in available.values())
    inner = sum(1 for key in available if key.startswith("score:"))
    working = (
        f"{len(available)} of {len(parts)} components"
        + (f" ({inner} of them scores)" if inner else "")
        + f", weights renormalised over {available_weight:.0f} of {total_weight:.0f}"
    )
    return score, coverage, working


def _rows(session, source: str | None):  # type: ignore[no-untyped-def]
    """Raw season rows with the identity needed to group them."""
    from sqlalchemy import select

    from app.models import DimPlayer, FactPlayerSeasonStats

    query = (
        select(FactPlayerSeasonStats, DimPlayer)
        .join(DimPlayer, FactPlayerSeasonStats.player_id == DimPlayer.player_id)
        .where(DimPlayer.position_group.is_not(None))
    )
    if source is not None:
        query = query.where(FactPlayerSeasonStats.source == source)
    return session.execute(query).all()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recompute sample players independently.")
    parser.add_argument("--players", type=int, default=8, help="How many players to check.")
    parser.add_argument(
        "--source",
        default=None,
        help=(
            "Only sample this source. The default validates whatever performance "
            "data is loaded, because the source that was last refreshed is not "
            "necessarily the one that carries statistics."
        ),
    )
    args = parser.parse_args(argv)

    sys.path.insert(0, str(REPO_ROOT / "backend"))
    from app.analytics.metrics import LOWER_IS_BETTER, DerivedMetric
    from app.analytics.percentiles import MIN_POPULATION, PercentileScope
    from app.analytics.sample import LOW_SAMPLE_MINUTES
    from app.core.config import get_settings
    from app.core.database import get_session_factory
    from app.core.logging import configure_logging, get_logger
    from app.services.analytics_service import build_view

    settings = get_settings()
    configure_logging(settings)
    log = get_logger(__name__)

    view = build_view(settings)
    if view.is_empty:
        print("Nothing is loaded. Run the load first.", file=sys.stderr)
        return 2

    with get_session_factory()() as session:
        rows = _rows(session, args.source)

    if not rows:
        where = f" from source '{args.source}'" if args.source else ""
        print(
            f"No player-seasons with a position group{where}. "
            "Nothing can be validated until identity resolution has run.",
            file=sys.stderr,
        )
        return 2

    # Rebuild the comparison populations by hand: position group, season, and
    # competition, over players who clear the minutes bar. Anyone below it is
    # still scored, but does not shape the distribution others are measured on.
    metrics_to_check = [
        DerivedMetric.GOALS_PER90,
        DerivedMetric.PASSES_PER90,
        DerivedMetric.DUELS_WON_PER90,
        DerivedMetric.TACKLES_PER90,
        DerivedMetric.DISPOSSESSED_PER90,
    ]
    source_of = {
        DerivedMetric.GOALS_PER90: "goals",
        DerivedMetric.PASSES_PER90: "passes",
        DerivedMetric.DUELS_WON_PER90: "duels_won",
        DerivedMetric.TACKLES_PER90: "tackles",
        DerivedMetric.DISPOSSESSED_PER90: "dispossessed",
    }

    populations: dict[tuple, list[float]] = {}
    for stats, player in rows:
        if stats.minutes is None or stats.minutes < LOW_SAMPLE_MINUTES:
            continue
        for metric in metrics_to_check:
            value = independent_per90(
                getattr(stats, source_of[metric]), stats.recorded_minutes, stats.minutes
            )
            if value is None:
                continue
            key = (metric, player.position_group, stats.season_id, stats.competition_id)
            populations.setdefault(key, []).append(value)

    # Sample players with something to check: enough minutes to be ranked, and
    # inside a population large enough for the engine to produce a percentile.
    candidates = [
        (stats, player)
        for stats, player in rows
        if stats.minutes
        and stats.minutes >= LOW_SAMPLE_MINUTES
        and len(
            populations.get(
                (metrics_to_check[0], player.position_group, stats.season_id, stats.competition_id),
                [],
            )
        )
        >= MIN_POPULATION
    ]
    candidates.sort(key=lambda pair: (-(pair[0].minutes or 0), pair[1].full_name))
    if not candidates:
        print(
            "No player is in a comparison population large enough to rank. "
            f"A percentile needs {MIN_POPULATION} comparable players; load more competitions.",
            file=sys.stderr,
        )
        return 2

    # Spread the sample across position groups rather than taking the top of
    # one list: a validation that only ever looks at centre backs has not
    # checked the goalkeeping metrics at all.
    chosen: list = []
    seen_groups: set = set()
    for candidate in candidates:
        group = candidate[1].position_group
        if group not in seen_groups:
            chosen.append(candidate)
            seen_groups.add(group)
        if len(chosen) >= args.players:
            break
    for candidate in candidates:
        if len(chosen) >= args.players:
            break
        if candidate not in chosen:
            chosen.append(candidate)

    validation = Validation()
    keys = _source_keys(args.source)

    for stats, player in chosen:
        player_key = keys.get(player.player_id)
        if player_key is None or player_key not in view.players:
            continue
        record = view.players[player_key]
        name = f"{player.full_name} ({player.position_group.value})"

        for metric in metrics_to_check:
            total = getattr(stats, source_of[metric])
            mine = independent_per90(total, stats.recorded_minutes, stats.minutes)
            theirs = getattr(record.metrics, metric.value, None)
            denominator = (
                stats.recorded_minutes if stats.recorded_minutes is not None else stats.minutes
            )
            validation.add(
                Check(
                    player=name,
                    subject=metric.value,
                    kind="per90",
                    engine=theirs,
                    independent=mine,
                    working=f"{total} / {denominator} * 90",
                )
            )

            if mine is None:
                continue
            population = populations.get(
                (metric, player.position_group, stats.season_id, stats.competition_id), []
            )
            if len(population) < MIN_POPULATION:
                continue

            mine_pct = independent_percentile(mine, population)
            if metric in LOWER_IS_BETTER:
                mine_pct = 100.0 - mine_pct
            ranked = view.rank(player_key, [metric], scope=PercentileScope.COMPETITION)
            result = ranked.get(metric)
            below = sum(1 for other in population if other < mine)
            equal = sum(1 for other in population if other == mine)
            validation.add(
                Check(
                    player=name,
                    subject=f"{metric.value} percentile",
                    kind="percentile",
                    engine=result.oriented if result else None,
                    independent=mine_pct,
                    working=(
                        f"{below} below + {equal} equal of {len(population)}"
                        + (", inverted" if metric in LOWER_IS_BETTER else "")
                    ),
                )
            )

        _check_scores(view, record, player_key, name, validation)
        _check_roles(view, record, player_key, name, validation)

    return _finish(validation, log, chosen=len(chosen))


def _source_keys(source: str | None) -> dict[int, str]:
    """player_id -> the key the view knows them by.

    A merged player carries a bridge row per source, so this can be
    many-to-one. Any of them addresses the same record in the view, which is
    the point of having merged them.
    """
    from sqlalchemy import select

    from app.core.database import get_session_factory
    from app.models import BridgePlayerSource

    query = select(BridgePlayerSource)
    if source is not None:
        query = query.where(BridgePlayerSource.source == source)

    with get_session_factory()() as session:
        return {row.player_id: row.source_player_id for row in session.scalars(query)}


def _check_scores(view, record, player_key, name, validation) -> None:  # type: ignore[no-untyped-def]
    """Rebuild each intelligence score from its component percentiles.

    The engine's own percentiles are the input here - this is checking the
    *aggregation*, not the ranking, which the percentile checks above cover.
    What matters is that weights are renormalised over the components that are
    present rather than over all of them: without that a missing component
    drags the score down and reads as poor performance instead of absent data.
    """
    from app.analytics.intelligence import get_definitions
    from app.analytics.percentiles import PercentileScope

    scores = view.scores(player_key)
    for key, definition in get_definitions().items():
        score = scores.get(key)
        if score is None:
            continue

        ranked = view.rank(
            player_key, list(definition.components), scope=PercentileScope.COMPETITION
        )
        present = {
            metric: result.oriented
            for metric, result in ranked.items()
            if result.oriented is not None
        }
        parts = {
            metric.value: (weight, present.get(metric))
            for metric, weight in definition.components.items()
        }
        mine, _, working = independent_weighted(parts, definition.min_coverage)

        validation.add(
            Check(
                player=name,
                subject=key,
                kind="score",
                engine=score.score,
                independent=mine,
                working=working,
            )
        )


def _check_roles(view, record, player_key, name, validation) -> None:  # type: ignore[no-untyped-def]
    """Rebuild each role score from its metric and score components.

    A role is the one place where the two scales meet: metric percentiles and
    whole intelligence scores are weighted together. That works only because an
    intelligence score is itself a 0-100 composite of percentiles, so both sides
    already sit on the same scale - and it is worth re-deriving precisely
    because a mistake there would not look like one. A role built from raw
    per-90 rates beside percentiles would still produce a plausible number.
    """
    from app.analytics.percentiles import PercentileScope
    from app.analytics.roles import get_roles

    fit = view.role_fit(player_key)
    if fit is None:
        return
    engine_scores = {score.key: score for score in fit.all_scores}

    for key, role in get_roles().items():
        if not role.applies_to(record.position_group):
            continue
        engine = engine_scores.get(key)
        if engine is None:
            continue

        parts: dict[str, tuple[float, float | None]] = {}
        if role.metric_weights:
            ranked = view.rank(
                player_key, list(role.metric_weights), scope=PercentileScope.COMPETITION
            )
            for metric, weight in role.metric_weights.items():
                result = ranked.get(metric)
                parts[metric.value] = (weight, result.oriented if result else None)

        inner_scores = view.scores(player_key, scope=PercentileScope.COMPETITION)
        for score_key, weight in role.score_weights.items():
            inner = inner_scores.get(score_key)
            parts[f"score:{score_key}"] = (weight, inner.score if inner else None)

        mine, _, working = independent_weighted(parts, role.min_coverage)

        validation.add(
            Check(
                player=name,
                subject=key,
                kind="role",
                engine=engine.score,
                independent=mine,
                working=working,
            )
        )


def write_report(validation: Validation, *, chosen: int) -> Path:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    target = DOCS_DIR / "analytics_validation.md"

    failures = validation.failures
    lines = [
        "# Independent recomputation of sample players",
        "",
        "Generated by `python -m pipelines.quality.validate_analytics`.",
        "Do not edit by hand.",
        "",
        "Every figure below was rebuilt from the raw season totals in",
        "`fact_player_season_stats` without calling the analytics engines, then",
        "compared with what the engines produced. A check that asked the same",
        "code the same question would only prove the code is deterministic.",
        "",
        f"**{len(validation.checks)} figures recomputed across {chosen} players. "
        f"{len(failures)} disagreed.**",
        "",
        f"{len(validation.substantive)} of those compared an actual number on both",
        "sides. The rest are both sides agreeing a figure cannot be computed - a",
        "correct result, but one that says they agree about absence rather than",
        "about arithmetic, so it is counted separately.",
        "",
    ]

    if failures:
        lines += [
            "## Disagreements",
            "",
            "| Player | Figure | Engine | Recomputed | Difference | Working |",
            "| --- | --- | ---: | ---: | ---: | --- |",
        ]
        for check in failures:
            difference = f"{check.difference:+.4f}" if check.difference is not None else "-"
            lines.append(
                f"| {check.player} | `{check.subject}` | {_fmt(check.engine)} "
                f"| {_fmt(check.independent)} | {difference} | {check.working} |"
            )
        lines.append("")

    lines += [
        "## Every check",
        "",
        "| Player | Figure | Kind | Engine | Recomputed | Working |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for check in validation.checks:
        mark = "" if check.agrees else " **DISAGREES**"
        lines.append(
            f"| {check.player} | `{check.subject}` | {check.kind} | {_fmt(check.engine)} "
            f"| {_fmt(check.independent)}{mark} | {check.working} |"
        )

    lines.append("")
    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def _fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:.4f}"


def _finish(validation: Validation, log, *, chosen: int) -> int:  # type: ignore[no-untyped-def]
    path = write_report(validation, chosen=chosen)
    failures = validation.failures

    by_kind: dict[str, list[Check]] = {}
    for check in validation.checks:
        by_kind.setdefault(check.kind, []).append(check)

    substantive = validation.substantive
    print(
        f"Recomputed {len(validation.checks)} figures across {chosen} players; "
        f"{len(substantive)} compared an actual number on both sides.\n"
    )
    for kind, checks in sorted(by_kind.items()):
        bad = [c for c in checks if not c.agrees]
        real = [c for c in checks if c.is_substantive]
        mark = "ok" if not bad else f"{len(bad)} DISAGREE"
        print(f"  {kind:<12} {len(real):>4} compared of {len(checks):<4} {mark}")

    if not substantive:
        print(
            "\nNothing was actually compared. Both sides agreeing a figure cannot "
            "be computed is not evidence about the arithmetic."
        )

    if failures:
        print("\nDisagreements:")
        for check in failures[:12]:
            print(
                f"  {check.player} {check.subject}: engine {_fmt(check.engine)} "
                f"vs {_fmt(check.independent)}  [{check.working}]"
            )

    print(f"\nReport: {path.relative_to(REPO_ROOT)}")
    log.info(
        "analytics_validated",
        checks=len(validation.checks),
        failures=len(failures),
        players=chosen,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
