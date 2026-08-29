"""What the loaded data actually lets the analytical layer produce.

    python -m pipelines.quality.derived_coverage
    python -m pipelines.quality.derived_coverage --source footystats

Specification Phase 16: replace mock analytical input with verified real
metrics, disable or adapt what is unavailable, and never silently substitute.

---------------------------------------------------------------------------
WHY THIS IS MEASURED RATHER THAN DECLARED
---------------------------------------------------------------------------

`pipelines.quality.coverage` answers a different question. It probes a
*synthetic* record with one field blanked and reports what stops computing -
which is the dependency graph, and is a fact about the code.

This runs the real engines over the real rows and counts what came out, which
is a fact about the data. The two disagree in the direction that matters: a
metric the graph calls computable is still useless if the provider populates it
for one player in three, and nothing about the code would ever say so.

The distinction is not academic. `successful_tackles` was mapped on the
strength of a naming pattern, satisfied every structural check, and is null in
all 10,464 sampled records that carry the key. Only counting real output found
it.

---------------------------------------------------------------------------
WHY THE DENOMINATOR IS NOT EVERY ROW
---------------------------------------------------------------------------

A per-90 needs minutes. A player who never played has none, so every rate is
correctly `None` - and counting them as missing coverage would report the squad
list as a data quality problem.

Goalkeeping metrics have the same shape one level up: `save_percentage` is
absent for most players because most players are not goalkeepers. So coverage
is judged **within the position group where the metric belongs**, exactly as
the canonical coverage check learned to.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO_ROOT / "docs"

#: Below this a rate is noise rather than a measurement, and counting it as
#: coverage would flatter the report.
MINIMUM_MINUTES = 450


@dataclass(frozen=True)
class DerivedCoverage:
    """How often one derived metric actually came out of the engine."""

    metric: str
    eligible: int
    computed: int
    best_group: str | None
    best_group_coverage: float

    @property
    def coverage(self) -> float:
        return self.computed / self.eligible if self.eligible else 0.0

    @property
    def status(self) -> str:
        if self.eligible == 0:
            return "unknown"
        if self.computed == 0:
            # Not a gap to chase. The provider does not supply an input, and
            # everything downstream must be switched off rather than filled in.
            return "absent"
        effective = max(self.coverage, self.best_group_coverage)
        if effective < 0.5:
            return "sparse"
        if effective < 0.95:
            return "partial"
        return "complete"


@dataclass(frozen=True)
class FeatureCoverage:
    """Whether a score or role can be produced, and for how many players."""

    name: str
    kind: str
    eligible: int
    produced: int
    caveated: int
    #: Components whose input the provider never supplies.
    absent_components: tuple[str, ...] = ()
    #: The share of this feature's weight that survives those absences, against
    #: the share its definition requires. Below the threshold is permanent.
    surviving_weight: float = 1.0
    min_coverage: float = 1.0

    @property
    def coverage(self) -> float:
        return self.produced / self.eligible if self.eligible else 0.0

    @property
    def status(self) -> str:
        if self.eligible == 0:
            return "unknown"
        if self.produced == 0:
            return "withheld"
        if self.caveated >= self.produced * 0.5:
            return "caveated"
        return "available"

    @property
    def is_permanently_withheld(self) -> bool:
        """Whether the absences alone are enough to withhold it.

        Missing a component is not the same as being disabled by it. Several
        roles carry a `min_coverage` set precisely so they survive a known
        absence with renormalised weights and a caveat. Blaming the provider
        wherever a component happens to be missing would write those off, so
        the arithmetic decides: only a feature whose surviving weight falls
        below its own threshold is beyond help.
        """
        return bool(self.absent_components) and self.surviving_weight < self.min_coverage

    @property
    def reason(self) -> str:
        """Why it came out the way it did - the distinction that matters.

        A feature the provider disables stays disabled however much data
        arrives. A feature short of ten comparable players is a half-finished
        ingest. Reading the two as one would either write off a working feature
        or promise one that can never work.
        """
        if self.is_permanently_withheld:
            return (
                f"provider: {', '.join(self.absent_components)} "
                f"({self.surviving_weight:.0%} of weight survives, needs {self.min_coverage:.0%})"
            )
        if self.status == "withheld":
            return "sample: no comparison population reached the minimum"
        if self.coverage < 0.5:
            return "sample: most comparison populations are below the minimum"
        if self.absent_components:
            return (
                f"partial: computed without {', '.join(self.absent_components)}, "
                "on renormalised weights"
            )
        return ""


def measure(  # type: ignore[no-untyped-def]
    view, *, keys: set[str] | None = None
) -> tuple[list[DerivedCoverage], list[FeatureCoverage]]:
    """Count what the engines produced, per metric and per feature.

    `keys` restricts the measurement to one source's players; without it the
    whole served population is measured, which is what the site shows.
    """
    from app.analytics.metrics import DerivedMetric

    eligible = [
        record
        for record in view.players.values()
        if (keys is None or record.player_key in keys) and (record.minutes or 0) >= MINIMUM_MINUTES
    ]

    computed: dict[str, int] = defaultdict(int)
    group_total: dict[str, int] = defaultdict(int)
    group_computed: dict[tuple[str, str], int] = defaultdict(int)

    for record in eligible:
        group = record.position_group.value
        group_total[group] += 1
        for metric in DerivedMetric:
            if getattr(record.metrics, metric.value, None) is not None:
                computed[metric.value] += 1
                group_computed[(metric.value, group)] += 1

    metrics: list[DerivedCoverage] = []
    for metric in DerivedMetric:
        best_group, best_share = None, 0.0
        for group, total in group_total.items():
            share = group_computed[(metric.value, group)] / total
            if share > best_share:
                best_group, best_share = group, share
        metrics.append(
            DerivedCoverage(
                metric=metric.value,
                eligible=len(eligible),
                computed=computed[metric.value],
                best_group=best_group,
                best_group_coverage=best_share,
            )
        )

    absent = frozenset(m.metric for m in metrics if m.status == "absent")
    return metrics, _measure_features(view, eligible, absent)


def _measure_features(  # type: ignore[no-untyped-def]
    view, eligible, absent: frozenset[str] = frozenset()
) -> list[FeatureCoverage]:
    """Run the scoring and role engines and count what survived.

    Asking the engines rather than reading the configuration is the point:
    `min_coverage` decides whether a partially-covered score is produced or
    withheld, and only running it says which happened.
    """
    from app.analytics.intelligence import get_definitions
    from app.analytics.roles import get_roles

    produced: dict[str, int] = defaultdict(int)
    caveated: dict[str, int] = defaultdict(int)
    role_eligible: dict[str, int] = defaultdict(int)

    definitions = get_definitions()
    roles = get_roles()

    for record in eligible:
        key = record.player_key
        for name, score in view.scores(key).items():
            if score.is_available:
                produced[f"score:{name}"] += 1
                if score.caveat:
                    caveated[f"score:{name}"] += 1

        for name, definition in roles.items():
            if definition.applies_to(record.position_group):
                role_eligible[name] += 1

        fit = view.role_fit(key)
        if fit is not None:
            for role_score in fit.all_scores:
                if role_score.is_available:
                    produced[f"role:{role_score.key}"] += 1
                    if role_score.caveat:
                        caveated[f"role:{role_score.key}"] += 1

    features = []
    dead_scores: set[str] = set()

    for name, definition in definitions.items():
        missing = tuple(sorted(m.value for m in definition.components if m.value in absent))
        total = sum(definition.components.values()) or 1.0
        lost = sum(w for m, w in definition.components.items() if m.value in absent)
        feature = FeatureCoverage(
            name=name,
            kind="score",
            eligible=len(eligible),
            produced=produced[f"score:{name}"],
            caveated=caveated[f"score:{name}"],
            absent_components=missing,
            surviving_weight=(total - lost) / total,
            min_coverage=definition.min_coverage,
        )
        features.append(feature)
        if feature.is_permanently_withheld:
            dead_scores.add(name)

    for name, definition in roles.items():
        # A role weights metrics and scores together, so a score the provider
        # has already killed costs the role its whole weight, not just the part
        # of it that was missing.
        missing = tuple(
            sorted(
                {m.value for m in definition.metric_weights if m.value in absent}
                | {s for s in definition.score_weights if s in dead_scores}
            )
        )
        total = (
            sum(definition.metric_weights.values()) + sum(definition.score_weights.values())
        ) or 1.0
        lost = sum(w for m, w in definition.metric_weights.items() if m.value in absent) + sum(
            w for s, w in definition.score_weights.items() if s in dead_scores
        )
        features.append(
            FeatureCoverage(
                name=name,
                kind="role",
                eligible=role_eligible[name],
                produced=produced[f"role:{name}"],
                caveated=caveated[f"role:{name}"],
                absent_components=missing,
                surviving_weight=(total - lost) / total,
                min_coverage=definition.min_coverage,
            )
        )

    return features


def write_report(
    metrics: list[DerivedCoverage], features: list[FeatureCoverage], *, source: str | None
) -> Path:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    target = DOCS_DIR / "derived_metric_coverage.md"

    absent = [m for m in metrics if m.status == "absent"]
    withheld = [f for f in features if f.status == "withheld"]

    lines = [
        "# What the loaded data can actually produce",
        "",
        "Generated by `python -m pipelines.quality.derived_coverage`.",
        "Do not edit by hand.",
        "",
        f"Measured over player-seasons with at least {MINIMUM_MINUTES} minutes"
        + (f", from `{source}`." if source else ", from every loaded source."),
        "",
        "This counts what the engines returned. It is not a reading of the",
        "configuration: a metric the dependency graph calls computable is still",
        "useless if the provider leaves it null, and only running it says so.",
        "",
        "## Derived metrics",
        "",
        "Coverage is judged within the position group where the metric belongs.",
        "`save_percentage` is missing for most players because most players are",
        "not goalkeepers, which is not a data quality problem.",
        "",
        "| Metric | Overall | Best group | There | Status |",
        "| --- | ---: | --- | ---: | --- |",
    ]
    order = {"absent": 0, "sparse": 1, "partial": 2, "complete": 3, "unknown": 4}
    for metric in sorted(metrics, key=lambda m: (order[m.status], m.metric)):
        group = metric.best_group or "-"
        lines.append(
            f"| `{metric.metric}` | {metric.coverage:.0%} | {group} "
            f"| {metric.best_group_coverage:.0%} | {metric.status} |"
        )

    lines += [
        "",
        "## Scores and roles",
        "",
        "`eligible` counts the players a feature could apply to: every measured",
        "player for a score, and only the compatible position groups for a role.",
        "",
        "| Feature | Kind | Produced for | Status | Why |",
        "| --- | --- | ---: | --- | --- |",
    ]
    feature_order = {"withheld": 0, "caveated": 1, "available": 2, "unknown": 3}
    for feature in sorted(features, key=lambda f: (f.kind, feature_order[f.status], f.name)):
        lines.append(
            f"| `{feature.name}` | {feature.kind} | {feature.coverage:.0%} "
            f"of {feature.eligible} | {feature.status} | {feature.reason or '-'} |"
        )

    if absent:
        lines += [
            "",
            "## Absent, and switched off",
            "",
            "These produced nothing for any player. Each is a statement about the",
            "provider rather than a gap to be filled, and nothing downstream may",
            "substitute another metric for them.",
            "",
        ]
        lines += [f"- `{m.metric}`" for m in absent]

    if withheld:
        permanent = [f for f in withheld if f.is_permanently_withheld]
        temporary = [f for f in withheld if not f.is_permanently_withheld]
        lines += [
            "",
            "## Features withheld",
            "",
            "Produced for nobody. Withheld rather than computed from whatever",
            "happened to be available: a score built from a subset is not",
            "comparable with one built from the whole, and publishing both under",
            "one name would hide that.",
            "",
            "**The two reasons below are not the same thing and must not be read",
            "as one.** One is a permanent limit of the provider; the other is a",
            "half-finished ingest that more data fixes.",
            "",
        ]
        if permanent:
            lines += [
                "### Withheld by the provider - permanent",
                "",
                "An input these are defined on does not exist in the source. No",
                "amount of further loading changes that, and substituting another",
                "metric would change what the feature means while keeping its name.",
                "",
            ]
            lines += [
                f"- `{f.name}` ({f.kind}) - needs {', '.join(f'`{c}`' for c in f.absent_components)}"
                for f in permanent
            ]
            lines.append("")
        if temporary:
            lines += [
                "### Withheld by sample size - temporary",
                "",
                "Every input exists. There were simply not enough comparable",
                "players to rank against: a percentile needs a position group",
                "within a competition, and thinly loaded competitions do not fill",
                "one. This resolves as the ingest completes.",
                "",
            ]
            lines += [f"- `{f.name}` ({f.kind})" for f in temporary]

    lines.append("")
    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def source_keys(source: str) -> set[str]:
    """The player keys one source contributed, read from the bridge."""
    from sqlalchemy import select

    from app.core.database import get_session_factory
    from app.models import BridgePlayerSource

    with get_session_factory()() as session:
        return set(
            session.scalars(
                select(BridgePlayerSource.source_player_id).where(
                    BridgePlayerSource.source == source
                )
            ).all()
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure what the loaded data can produce.")
    parser.add_argument("--source", default=None, help="Only players from this source.")
    parser.add_argument(
        "--fail-on-absent",
        action="store_true",
        help="Exit non-zero if any derived metric produced nothing. For CI.",
    )
    args = parser.parse_args(argv)

    sys.path.insert(0, str(REPO_ROOT / "backend"))
    from app.core.config import get_settings
    from app.core.logging import configure_logging, get_logger
    from app.services.analytics_service import build_view

    settings = get_settings()
    configure_logging(settings)
    log = get_logger(__name__)

    view = build_view(settings)
    if view.is_empty:
        print("Nothing is loaded. Run the load first.", file=sys.stderr)
        return 2

    keys = source_keys(args.source) if args.source else None
    metrics, features = measure(view, keys=keys)
    path = write_report(metrics, features, source=args.source)

    absent = [m for m in metrics if m.status == "absent"]
    sparse = [m for m in metrics if m.status == "sparse"]
    withheld = [f for f in features if f.status == "withheld"]

    eligible = metrics[0].eligible if metrics else 0
    print(f"{eligible:,} player-seasons with at least {MINIMUM_MINUTES} minutes.\n")
    print(f"  derived metrics absent   {len(absent):>3} of {len(metrics)}")
    print(f"  derived metrics sparse   {len(sparse):>3}")
    print(f"  features withheld        {len(withheld):>3} of {len(features)}")

    if absent:
        print("\nAbsent - nothing downstream may substitute for these:")
        for metric in absent:
            print(f"  {metric.metric}")
    permanent = [f for f in withheld if f.is_permanently_withheld]
    temporary = [f for f in withheld if not f.is_permanently_withheld]
    if permanent:
        print("\nWithheld by the provider - permanent:")
        for feature in permanent:
            print(f"  {feature.name} ({feature.kind}) needs {', '.join(feature.absent_components)}")
    if temporary:
        print("\nWithheld by sample size - resolves as the ingest completes:")
        for feature in temporary:
            print(f"  {feature.name} ({feature.kind})")

    print(f"\nReport: {path.relative_to(REPO_ROOT)}")
    log.info(
        "derived_coverage_measured",
        absent=len(absent),
        sparse=len(sparse),
        withheld=len(withheld),
    )
    return 1 if (args.fail_on_absent and absent) else 0


if __name__ == "__main__":
    raise SystemExit(main())
