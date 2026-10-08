"""The verified FootyStats field mapping, and the refusal when there isn't one.

`config/footystats_mapping.yaml` records which canonical metrics a real
FootyStats response can supply, which observed field carries each one, and who
verified it against what. This module loads that file and validates it
strictly.

It exists so that "we have not validated FootyStats yet" is a fact the system
reads from a file rather than a `raise` somebody has to remember to delete. The
provider will supply exactly the metrics recorded here — an empty mapping means
an empty provider, and every feature depending on those metrics stays off.

The validation is deliberately unforgiving. A mapping entry must name the
response it was seen in, the date a person checked it, and what convinced them.
An entry that cannot say those things is not evidence of anything, and the
whole point of this file is that it is evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.core import paths
from app.core.errors import DataNotValidatedError
from app.schemas.canonical import CanonicalMetric

REPO_ROOT = paths.REPO_ROOT
MAPPING_PATH = REPO_ROOT / "config" / "footystats_mapping.yaml"

#: Every key an entry must carry. `verified_on` and `note` are not bureaucracy:
#: a mapping nobody can audit is a mapping nobody should trust.
REQUIRED_KEYS = frozenset({"field", "response", "verified_on", "note"})


class MappingError(Exception):
    """The mapping file is malformed. Raised at load time, never ignored."""


@dataclass(frozen=True)
class MappedField:
    """One canonical metric, and the observed field a person tied it to."""

    metric: CanonicalMetric
    field: str
    response: str
    verified_on: date
    note: str


@dataclass(frozen=True)
class DerivedField:
    """One canonical metric the provider does not carry but the data yields.

    FootyStats has no non-penalty goals field; it has goals and penalty goals,
    and the difference is the answer. That is a derivation, not an absence, and
    the distinction matters to a reader: "unavailable" says the system cannot
    see something, and here it can.

    `formula` is the arithmetic as a person would write it, kept so the claim
    can be checked against the response named beside it.
    """

    metric: CanonicalMetric
    formula: str
    verified_on: date
    note: str


@dataclass(frozen=True)
class AbsentField:
    """One canonical metric the provider genuinely cannot supply, and why.

    Not a placeholder. Each of these was profiled against real responses, and
    the reason says what was found - a key declared and never populated, an
    attempt count absent where only the successes are given, a percentage that
    returns zero for everybody. A list of names tells a reader nothing; this
    tells them whether the gap could ever close.
    """

    metric: CanonicalMetric
    reason: str


@dataclass(frozen=True)
class MetricCensus:
    """How many canonical metrics there are, and what became of each.

    Every public statement about metric counts is read from here, because four
    pages reading the same object and categorising it differently is how they
    came to contradict each other.

    `native + derived + unavailable == total`, and a test holds it to that.
    """

    #: Canonical metrics the project defines.
    total: int
    #: Supplied by the provider as a field of its own.
    native: int
    #: Assembled from fields the provider does supply. These exist: a derived
    #: metric is computed from observed values, not substituted for a missing
    #: one. See `available_metrics`.
    derived: int
    #: Cannot be produced at all, however the data is combined.
    unavailable: int
    #: PROVIDER FIELDS examined during profiling and refused - not canonical
    #: metrics, and not a subset of any count above. Kept because it is where
    #: a wrong public number came from, and a reader comparing the two
    #: deserves to see both.
    rejected_provider_fields: int

    @property
    def usable(self) -> int:
        """Everything a score may be built on, native or derived."""
        return self.native + self.derived


@dataclass(frozen=True)
class FootyStatsMapping:
    """What FootyStats has been verified to supply.

    `is_empty` is the state the project is in until an API key exists and the
    profiling pipeline has run. It is a normal state, not an error — the error
    would be pretending otherwise.
    """

    metrics: dict[CanonicalMetric, MappedField]
    verified_against: tuple[str, ...]
    rejected: dict[str, str]
    derived: dict[CanonicalMetric, DerivedField] = field(default_factory=dict)
    absent: dict[CanonicalMetric, AbsentField] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not self.metrics

    @property
    def available_metrics(self) -> frozenset[CanonicalMetric]:
        """Everything the provider can produce, however it produces it.

        Derived metrics belong here. The provider computes non-penalty goals
        and penalties taken from fields it does supply, and the site has shown
        both for as long as it has shown anything - while the data quality
        page, reading this set, called them unavailable. A page whose only job
        is to be truthful about the data was wrong about the data.

        The distinction between native and derived is worth keeping, and
        `derived` keeps it. What it must not do is decide whether the metric
        exists.
        """
        return frozenset(self.metrics) | frozenset(self.derived)

    def missing(self) -> frozenset[CanonicalMetric]:
        """Canonical metrics FootyStats has not been verified to supply."""
        return frozenset(CanonicalMetric) - self.available_metrics

    def census(self) -> MetricCensus:
        """The counts four public pages were each stating differently.

        ONE QUESTION, FOUR ANSWERS
        --------------------------

        Methodology said thirty-four of thirty-nine were mapped and in use and
        that the remaining five were not supplied. System Status said
        thirty-six of thirty-nine were mapped and named three as unavailable.
        About said five were not supplied. Data Quality said three could not be
        supplied and listed two more as derived.

        Every one of those numbers was read from this object, and the readings
        disagreed because the categories were being conflated:

          - `metrics` is what the provider supplies as a field: 34.
          - `derived` is what it supplies in pieces this project assembles,
            which exist just as much as the rest: 2.
          - `absent` is what cannot be produced at all: 3.
          - `rejected` is a count of PROVIDER FIELDS examined and refused - a
            declared-but-empty tackles column, a percentage that reads zero
            for everybody. It is five, and it is where "five canonical metrics
            are not supplied" came from. It is not a count of canonical
            metrics, and two of those five are fields belonging to metrics
            counted once in `absent`.

        Derived here rather than in four pieces of page copy, so the pages
        cannot drift apart again. See `test_metric_census_is_the_only_source`.
        """
        return MetricCensus(
            total=len(CanonicalMetric),
            native=len(self.metrics),
            derived=len(self.derived),
            unavailable=len(self.missing()),
            rejected_provider_fields=len(self.rejected),
        )

    def require(self) -> None:
        """Raise unless at least one metric has been verified.

        Called before constructing a provider. A provider built on an empty
        mapping would return a player record with every metric None, which is
        indistinguishable from a player who genuinely did nothing.
        """
        if self.is_empty:
            raise DataNotValidatedError(
                "No FootyStats field has been verified against a real API response. "
                "Run the profiling pipeline and record the mapping in "
                "config/footystats_mapping.yaml before enabling this provider.",
                details={"mapping_file": "config/footystats_mapping.yaml"},
            )


def _parse_entry(name: str, raw: Any) -> MappedField:
    try:
        metric = CanonicalMetric(name)
    except ValueError as exc:
        raise MappingError(
            f"'{name}' is not a canonical metric. The mapping may only name metrics "
            "the internal model carries; inventing one here would put a field in "
            "the system that nothing else knows about."
        ) from exc

    if not isinstance(raw, dict):
        raise MappingError(f"mapping for '{name}' must be a block of keys")

    missing = REQUIRED_KEYS - set(raw)
    if missing:
        raise MappingError(
            f"mapping for '{name}' is missing {', '.join(sorted(missing))}. "
            "Every entry must say which field, in which response, verified when, "
            "and on what basis."
        )

    field_name = str(raw["field"]).strip()
    if not field_name:
        raise MappingError(f"mapping for '{name}' has an empty field name")

    note = str(raw["note"]).strip()
    if len(note) < 10:
        raise MappingError(
            f"mapping for '{name}' has no real justification. Write what convinced "
            "you this field means this metric."
        )

    verified_on = raw["verified_on"]
    if isinstance(verified_on, str):
        try:
            verified_on = date.fromisoformat(verified_on)
        except ValueError as exc:
            raise MappingError(f"mapping for '{name}' has an unparseable date") from exc
    if not isinstance(verified_on, date):
        raise MappingError(f"mapping for '{name}' needs a date for verified_on")

    return MappedField(
        metric=metric,
        field=field_name,
        response=str(raw["response"]).strip(),
        verified_on=verified_on,
        note=note,
    )


def load_mapping(path: Path | None = None) -> FootyStatsMapping:
    """Load and validate the mapping. Raises `MappingError` if it is malformed."""
    target = path or MAPPING_PATH
    if not target.exists():
        raise MappingError(f"missing mapping file: {target}")

    with target.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    if not isinstance(raw, dict):
        raise MappingError("mapping file must be a mapping at the top level")

    metrics_block = raw.get("metrics") or {}
    if not isinstance(metrics_block, dict):
        raise MappingError("'metrics' must be a mapping of metric name to definition")

    parsed = {name: _parse_entry(name, entry) for name, entry in metrics_block.items()}

    verified_against = raw.get("verified_against") or []
    if not isinstance(verified_against, list):
        raise MappingError("'verified_against' must be a list of response names")

    # A mapping that claims metrics but names no response it saw them in cannot
    # be checked by anyone. That is exactly the state this file exists to
    # prevent, so it is rejected rather than merely noted.
    if parsed and not verified_against:
        raise MappingError(
            "the mapping defines metrics but names no response in 'verified_against'. "
            "Record which recorded responses the fields were observed in."
        )

    rejected_block = raw.get("rejected") or {}
    if not isinstance(rejected_block, dict):
        raise MappingError("'rejected' must be a mapping of field name to reason")

    return FootyStatsMapping(
        metrics={entry.metric: entry for entry in parsed.values()},
        verified_against=tuple(str(item) for item in verified_against),
        rejected={str(k): str(v) for k, v in rejected_block.items()},
        derived=_parse_derived(raw.get("derived") or {}),
        absent=_parse_absent(raw.get("absent") or []),
    )


def _parse_derived(block: Any) -> dict[CanonicalMetric, DerivedField]:
    """Metrics computed from fields the provider does supply.

    Held to the same evidence standard as a direct mapping: a derivation
    nobody can check is a number nobody should trust, and arithmetic is
    exactly where a plausible-looking mistake hides.
    """
    if not isinstance(block, dict):
        raise MappingError("'derived' must be a mapping of metric name to definition")

    out: dict[CanonicalMetric, DerivedField] = {}
    for name, entry in block.items():
        try:
            metric = CanonicalMetric(str(name))
        except ValueError as exc:
            raise MappingError(f"'{name}' in 'derived' is not a canonical metric") from exc
        if not isinstance(entry, dict):
            raise MappingError(f"derivation for '{name}' must be a block of keys")
        gaps = {"from", "verified_on", "note"} - set(entry)
        if gaps:
            raise MappingError(
                f"derivation for '{name}' is missing {', '.join(sorted(gaps))}. "
                "Every derivation must say what it is computed from, when that "
                "was checked, and on what basis."
            )
        verified = entry["verified_on"]
        if not isinstance(verified, date):
            raise MappingError(f"derivation for '{name}' needs a real date in 'verified_on'")
        out[metric] = DerivedField(
            metric=metric,
            formula=str(entry["from"]).strip(),
            verified_on=verified,
            note=str(entry["note"]).strip(),
        )
    return out


def _parse_absent(block: Any) -> dict[CanonicalMetric, AbsentField]:
    """Metrics profiling established the provider cannot supply.

    A reason is required. "Unavailable" with nothing behind it reads as "not
    looked at yet", and these were looked at - with sample counts.
    """
    if not isinstance(block, list):
        raise MappingError("'absent' must be a list of {metric, reason} entries")

    out: dict[CanonicalMetric, AbsentField] = {}
    for entry in block:
        if not isinstance(entry, dict) or "metric" not in entry or "reason" not in entry:
            raise MappingError("each 'absent' entry needs a 'metric' and a 'reason'")
        try:
            metric = CanonicalMetric(str(entry["metric"]))
        except ValueError as exc:
            raise MappingError(
                f"'{entry['metric']}' in 'absent' is not a canonical metric"
            ) from exc
        out[metric] = AbsentField(metric=metric, reason=str(entry["reason"]).strip())
    return out


@lru_cache(maxsize=1)
def get_mapping() -> FootyStatsMapping:
    """The mapping, loaded once per process."""
    return load_mapping()
