"""What the configuration asks for, against what the provider actually supplies.

    python -m pipelines.quality.config_availability
    python -m pipelines.quality.config_availability --check

Roles, intelligence scores and similarity vectors are declared in
`config/*.yaml` and name the metrics they need. What the provider supplies is
declared in `config/footystats_mapping.yaml`. Nothing had ever compared the two
directly.

The caveats on the affected roles were written by hand, and hand-written
caveats go stale the moment a provider changes. `successful_tackles` is the
worked example: it was mapped on the strength of a naming pattern, satisfied
every structural check, and is null in all 10,464 sampled records that carry
the key. Everything built on it had to be found and annotated one definition at
a time.

This measures instead. The dependency graph comes from
`pipelines.quality.coverage`, which discovers it by blanking a field and seeing
what stops computing - the real dependency, taken from the code that implements
it rather than from a second declaration free to drift.

WHAT IT DOES NOT DO
-------------------

It does not read the database. `pipelines.quality.derived_coverage` answers the
neighbouring question - how often a metric is actually populated in the rows we
loaded - and needs data to do it. This one runs on configuration alone, so it
runs in CI, before any load, and catches a definition that asks for something
the provider has never supplied.

STATUSES
--------

OK        Every component is computable from what the provider supplies.
REDUCED   Some are not. The remaining weight still meets the definition's own
          `min_coverage`, so the score is produced from the rest with its
          coverage reported. Renormalised, never filled in with a zero.
DISABLED  Too little remains. The score is not produced at all, and the
          feature depending on it says so.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
MAPPING = REPO_ROOT / "config" / "footystats_mapping.yaml"
OUTPUT = REPO_ROOT / "docs" / "config_availability.md"


@dataclass(frozen=True)
class Line:
    """One configured definition, measured against the provider."""

    key: str
    label: str
    configured_weight: float
    available_weight: float
    missing: list[str]
    min_coverage: float

    @property
    def coverage(self) -> float:
        if self.configured_weight <= 0:
            return 0.0
        return self.available_weight / self.configured_weight

    @property
    def status(self) -> str:
        if not self.missing:
            return "OK"
        if self.coverage >= self.min_coverage:
            return "REDUCED"
        return "DISABLED"

    def cells(self) -> list[str]:
        return [
            self.label,
            f"{self.configured_weight:.0f}",
            f"{self.available_weight:.0f}",
            f"{self.coverage * 100:.0f}%",
            ", ".join(f"`{m}`" for m in self.missing) or "-",
            f"**{self.status}**",
        ]


def supplied_metrics() -> set[str]:
    """Canonical metric names the mapping grants."""
    mapping: dict[str, Any] = yaml.safe_load(MAPPING.read_text(encoding="utf-8"))
    return set(mapping.get("metrics") or {}) | set(mapping.get("derived") or {})


def measure() -> tuple[list[Line], list[Line], list[Line], list[str]]:
    """Roles, scores, similarity vectors, and the canonical metrics absent."""
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    from app.analytics.intelligence import get_definitions
    from app.analytics.roles import get_roles
    from app.analytics.similarity import get_feature_sets
    from app.schemas.canonical import CanonicalMetric
    from pipelines.quality.coverage import _computed, _probe_stats

    supplied = supplied_metrics()
    absent = {m for m in CanonicalMetric if m.value not in supplied}

    # Measured, not declared: blank the absent set and see what survives.
    computable = {m.value for m in _computed(_probe_stats(omit_all=absent))}

    scores: list[Line] = []
    for key, definition in get_definitions().items():
        weights = {metric.value: weight for metric, weight in definition.components.items()}
        missing = sorted(name for name in weights if name not in computable)
        scores.append(
            Line(
                key=key,
                label=definition.label,
                configured_weight=sum(weights.values()),
                available_weight=sum(w for n, w in weights.items() if n in computable),
                missing=missing,
                min_coverage=definition.min_coverage,
            )
        )
    disabled_scores = {line.key for line in scores if line.status == "DISABLED"}

    roles: list[Line] = []
    for role in get_roles().values():
        weights: dict[str, float] = {m.value: w for m, w in role.metric_weights.items()}
        weights.update({f"score:{k}": w for k, w in role.score_weights.items()})

        def is_available(name: str) -> bool:
            if name.startswith("score:"):
                return name.removeprefix("score:") not in disabled_scores
            return name in computable

        missing = sorted(name for name in weights if not is_available(name))
        roles.append(
            Line(
                key=role.key,
                label=role.label,
                configured_weight=sum(weights.values()),
                available_weight=sum(w for n, w in weights.items() if is_available(n)),
                missing=missing,
                min_coverage=role.min_coverage,
            )
        )

    vectors: list[Line] = []
    for group, features in sorted(get_feature_sets().items(), key=lambda kv: kv[0].value):
        names = [f.value for f in features]
        missing = sorted(n for n in names if n not in computable)
        vectors.append(
            Line(
                key=group.value,
                label=group.value,
                # Similarity weights every feature equally, so the count is the
                # weight. Reported the same way as the others so the tables read
                # alike.
                configured_weight=float(len(names)),
                available_weight=float(len(names) - len(missing)),
                missing=missing,
                # A vector is not "disabled": the engine drops absent features
                # and reports the coverage. See `MINIMUM_FEATURE_COVERAGE`.
                min_coverage=0.0,
            )
        )

    return roles, scores, vectors, sorted(m.value for m in absent)


def table(title: str, note: str, lines: list[Line], first_column: str) -> list[str]:
    out = [f"## {title}", "", note, ""]
    out.append(f"| {first_column} | Configured | Available | Coverage | Missing | Status |")
    out.append("| --- | ---: | ---: | ---: | --- | --- |")
    out += ["| " + " | ".join(line.cells()) + " |" for line in lines]
    out.append("")
    return out


def render(roles: list[Line], scores: list[Line], vectors: list[Line], absent: list[str]) -> str:
    lines = [
        "# Configuration against provider availability",
        "",
        "**Generated. Do not edit by hand.**",
        "",
        "```bash",
        "python -m pipelines.quality.config_availability",
        "```",
        "",
        "What the role, score and similarity definitions ask for, against what",
        "`config/footystats_mapping.yaml` grants. The dependency between a canonical",
        "metric and the derived figures needing it is measured rather than declared -",
        "see `pipelines/quality/coverage.py`.",
        "",
        "Nothing is substituted for a missing metric. A definition either produces its",
        "score from the components that remain, with the reduced coverage reported to",
        "the reader, or produces nothing and says so.",
        "",
        "## Canonical metrics the provider does not supply",
        "",
    ]
    lines += [f"- `{name}`" for name in absent] or ["Nothing. Every canonical metric is mapped."]
    lines += [""]

    switched_off = [line for line in roles + scores if line.status == "DISABLED"]
    if switched_off:
        lines += [
            "## Switched off entirely",
            "",
            "Too little of the definition survives to produce a number, so none is",
            "produced. These are absences a reader sees as an absence - not as a low",
            "score, which is what substituting or zero-filling would produce.",
            "",
        ]
        lines += [
            f"- **{line.label}** - {line.coverage * 100:.0f}% of weight available, "
            f"needs {line.min_coverage * 100:.0f}%. Missing "
            + ", ".join(f"`{m}`" for m in line.missing)
            for line in switched_off
        ]
        lines += [""]
    lines += table(
        "Intelligence scores",
        "Composites of percentiles. `min_coverage` is the share of weight that must "
        "survive for the score to be produced at all.",
        scores,
        "Score",
    )
    lines += table(
        "Player roles",
        "A role component can be a derived metric or a whole intelligence score. A "
        "role is disabled when a score it leans on is.",
        roles,
        "Role",
    )
    lines += table(
        "Similarity vectors",
        "Every feature carries equal weight, so the count is the weight. A vector is "
        "never disabled: the engine compares on the features two players share and "
        "reports that coverage alongside the index.",
        vectors,
        "Position group",
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Configuration against provider availability.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the written file is out of date, or a reduced definition has no caveat.",
    )
    args = parser.parse_args(argv)

    roles, scores, vectors, absent = measure()
    rendered = render(roles, scores, vectors, absent)

    if not args.check:
        OUTPUT.write_text(rendered, encoding="utf-8")
        print(f"wrote {OUTPUT.relative_to(REPO_ROOT)}")
        return 0

    problems: list[str] = []
    current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
    if current != rendered:
        problems.append(
            f"{OUTPUT.relative_to(REPO_ROOT)} is out of date. "
            "Run: python -m pipelines.quality.config_availability"
        )

    # A role that still produces a score from fewer components than it declares
    # must say so where a reader will see it. This is the check that stops a
    # provider change quietly degrading a score behind an unchanged label.
    #
    # Deliberately REDUCED only. A DISABLED role produces nothing at all, so a
    # caveat on it would never be shown to anybody - what a reader sees there is
    # the role's absence, and requiring wording that cannot appear would be a
    # check satisfied by writing something nobody reads.
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    from app.analytics.roles import get_roles

    role_caveats = {role.key: role.caveat for role in get_roles().values()}
    for line in roles:
        if line.status == "REDUCED" and not role_caveats.get(line.key):
            problems.append(
                f"Role '{line.key}' produces a score at {line.coverage * 100:.0f}% "
                f"coverage (missing {', '.join(line.missing)}) and carries no caveat."
            )

    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1

    print(f"{OUTPUT.relative_to(REPO_ROOT)} agrees with the configuration.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
