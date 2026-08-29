"""Sample similarity results, for a person to judge.

    python -m pipelines.quality.similarity_examples
    python -m pipelines.quality.similarity_examples --per-group 3

Specification Phase 18: recompute real similarity features, and validate the
results qualitatively.

---------------------------------------------------------------------------
WHY THIS IS NOT A PASS/FAIL CHECK
---------------------------------------------------------------------------

Whether two footballers actually resemble each other is not a property this
code can assert. It can be measured wrongly in ways arithmetic would never
catch: a vector that separates players by how much they play rather than how
they play produces confident, stable, entirely useless matches.

So this does two different jobs and keeps them apart.

The **properties** below are things that must be true whatever football says,
and a violation is a fault. A player cannot resemble themselves. Similarity
must be symmetric, because cosine is. Matches must stay inside a position
group, because comparing a centre back to a winger ranks on position rather
than style. And the index must actually spread - if every player's closest
match scores 99, the engine has stopped distinguishing anyone while still
looking like it works.

The **examples** are for a reader. Each match is printed with the features that
drove it and the features that most disagree, so a person who knows the players
can say whether the answer is sensible. That judgement is the validation; this
only lays the evidence out where it can be made.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO_ROOT / "docs"

#: A rate below this is noise, and a similarity built on noise is noise with a
#: number attached.
MINIMUM_MINUTES = 900

#: Above this, a "closest match" has stopped meaning anything: if everyone's
#: nearest neighbour scores here, the vector is not separating players.
SATURATION_INDEX = 99.0


@dataclass
class Property:
    """Something that must hold whatever the football says."""

    name: str
    checked: int
    violations: list[str] = field(default_factory=list)
    detail: str = ""

    @property
    def holds(self) -> bool:
        return not self.violations


@dataclass
class Example:
    player: str
    position: str
    competition: str
    minutes: int | None
    matches: list[dict] = field(default_factory=list)


def _real(view) -> list:  # type: ignore[no-untyped-def]
    """Players from a real source with enough minutes to be compared."""
    return [
        record
        for record in view.players.values()
        if not str(record.player_key).startswith("mock")
        and (record.minutes or 0) >= MINIMUM_MINUTES
    ]


def check_properties(view, players) -> list[Property]:  # type: ignore[no-untyped-def]
    """The claims that do not depend on knowing any footballer."""
    same_group = Property("matches stay within the position group", 0)
    no_self = Property("a player is not their own match", 0)
    symmetric = Property("similarity is symmetric", 0)
    spread = Property("the index distinguishes players", 0)

    tops: list[float] = []
    seen: dict[tuple[str, str], float] = {}

    for record in players:
        results = view.similar(record.player_key, limit=10)
        if not results:
            continue

        same_group.checked += 1
        no_self.checked += 1
        tops.append(results[0].similarity)

        for result in results:
            other = view.players.get(result.candidate.player_key)
            if other is None:
                continue
            if other.position_group is not record.position_group:
                same_group.violations.append(
                    f"{record.full_name} ({record.position_group.value}) matched "
                    f"{other.full_name} ({other.position_group.value})"
                )
            if result.candidate.player_key == record.player_key:
                no_self.violations.append(record.full_name)
            seen[(record.player_key, result.candidate.player_key)] = result.similarity

    for (left, right), value in seen.items():
        mirrored = seen.get((right, left))
        if mirrored is None:
            # Only present when each is in the other's top ten; absence is not
            # a violation, it just means the pair was not checked both ways.
            continue
        symmetric.checked += 1
        if abs(mirrored - value) > 1e-6:
            symmetric.violations.append(
                f"{view.players[left].full_name} -> {value:.2f} but back {mirrored:.2f}"
            )

    spread.checked = len(tops)
    if tops:
        saturated = sum(1 for value in tops if value >= SATURATION_INDEX)
        spread.detail = (
            f"closest match: min {min(tops):.1f}, median {statistics.median(tops):.1f}, "
            f"max {max(tops):.1f}; {saturated} of {len(tops)} at or above "
            f"{SATURATION_INDEX:.0f}"
        )
        if saturated > len(tops) * 0.1:
            spread.violations.append(
                f"{saturated} of {len(tops)} players have a closest match at "
                f"{SATURATION_INDEX:.0f} or above; the vector is not separating them"
            )

    return [same_group, no_self, symmetric, spread]


def collect_examples(view, players, *, per_group: int, matches: int) -> list[Example]:  # type: ignore[no-untyped-def]
    """The most-played players in each position group, and who they resemble."""
    by_group: dict[str, list] = {}
    for record in sorted(players, key=lambda r: -(r.minutes or 0)):
        by_group.setdefault(record.position_group.value, []).append(record)

    examples: list[Example] = []
    for group in sorted(by_group):
        shown = 0
        for record in by_group[group]:
            if shown >= per_group:
                break
            results = view.similar(record.player_key, limit=matches)
            if not results:
                # Keep looking rather than losing the group. A player with no
                # comparable peers is a real outcome - a thinly loaded
                # competition, or a vector too sparse to compare - but it must
                # not silently cost the whole position group its examples.
                continue
            shown += 1
            example = Example(
                player=record.full_name,
                position=group,
                competition=record.competition_name,
                minutes=record.minutes,
            )
            for result in results:
                other = view.players.get(result.candidate.player_key)
                gaps = result.feature_gaps
                example.matches.append(
                    {
                        "name": result.candidate.display_name,
                        "competition": other.competition_name if other else "-",
                        "index": result.similarity,
                        "shared": result.shared_features,
                        "strength": result.profile_strength_ratio,
                        "comparable": result.comparable_strength,
                        "closest": ", ".join(f"{m}" for m, _ in gaps[:3]),
                        "furthest": ", ".join(f"{m}" for m, _ in gaps[-2:]),
                    }
                )
            examples.append(example)
    return examples


def write_report(properties: list[Property], examples: list[Example]) -> Path:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    target = DOCS_DIR / "similarity_examples.md"

    lines = [
        "# Similarity, laid out to be judged",
        "",
        "Generated by `python -m pipelines.quality.similarity_examples`.",
        "Do not edit by hand.",
        "",
        "Whether two footballers actually resemble each other is not something",
        "this code can assert. What it can do is check the claims that hold",
        "whatever the football says, and then show enough of each match for a",
        "person to judge the rest.",
        "",
        "## Properties",
        "",
        "| Property | Checked | Result |",
        "| --- | ---: | --- |",
    ]
    for prop in properties:
        verdict = "holds" if prop.holds else f"**{len(prop.violations)} violations**"
        lines.append(f"| {prop.name} | {prop.checked} | {verdict} |")

    for prop in properties:
        if prop.detail:
            lines += ["", f"*{prop.name}*: {prop.detail}"]
        if prop.violations:
            lines += ["", f"**{prop.name}** failed:", ""]
            lines += [f"- {violation}" for violation in prop.violations[:10]]

    lines += [
        "",
        "## Examples",
        "",
        "The most-played player in each position group, and who the engine says",
        "they resemble. `strength` is how comparable the two are in level rather",
        "than shape - cosine measures direction, so a very good player and a",
        "middling one with the same profile point the same way.",
        "",
    ]
    for example in examples:
        lines += [
            f"### {example.player} — {example.position}, {example.competition}",
            "",
            f"{example.minutes or 0} minutes.",
            "",
            "| Similar to | Competition | Index | Shared | Strength | Closest on | Furthest on |",
            "| --- | --- | ---: | ---: | ---: | --- | --- |",
        ]
        for match in example.matches:
            flag = "" if match["comparable"] else " ⚠"
            lines.append(
                f"| {match['name']} | {match['competition']} | {match['index']:.1f} "
                f"| {match['shared']} | {match['strength']:.2f}{flag} "
                f"| {match['closest']} | {match['furthest']} |"
            )
        lines.append("")

    lines += [
        "⚠ marks a pair that matches in shape but not in level: the profiles",
        "point the same way, one is simply further along it. Recruiting on shape",
        "alone is exactly the mistake that flag exists to prevent.",
        "",
    ]
    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lay similarity results out to be judged.")
    parser.add_argument("--per-group", type=int, default=2, help="Players per position group.")
    parser.add_argument("--matches", type=int, default=5, help="Matches shown per player.")
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

    players = _real(view)
    if not players:
        print(
            f"No player from a real source has {MINIMUM_MINUTES} minutes. "
            "Similarity needs a sample worth comparing.",
            file=sys.stderr,
        )
        return 2

    properties = check_properties(view, players)
    examples = collect_examples(view, players, per_group=args.per_group, matches=args.matches)
    path = write_report(properties, examples)

    print(f"{len(players)} real players with at least {MINIMUM_MINUTES} minutes.\n")
    for prop in properties:
        verdict = "ok" if prop.holds else f"{len(prop.violations)} VIOLATIONS"
        print(f"  {prop.name:<44} {prop.checked:>5} checked  {verdict}")
        if prop.detail:
            print(f"      {prop.detail}")

    failed = [p for p in properties if not p.holds]
    if failed:
        print("\nViolations:")
        for prop in failed:
            for violation in prop.violations[:5]:
                print(f"  {prop.name}: {violation}")

    print(f"\n{len(examples)} players shown for judgement.")
    print(f"Report: {path.relative_to(REPO_ROOT)}")
    log.info(
        "similarity_examples_written",
        players=len(players),
        examples=len(examples),
        violations=sum(len(p.violations) for p in properties),
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
