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

from dataclasses import dataclass
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
class FootyStatsMapping:
    """What FootyStats has been verified to supply.

    `is_empty` is the state the project is in until an API key exists and the
    profiling pipeline has run. It is a normal state, not an error — the error
    would be pretending otherwise.
    """

    metrics: dict[CanonicalMetric, MappedField]
    verified_against: tuple[str, ...]
    rejected: dict[str, str]

    @property
    def is_empty(self) -> bool:
        return not self.metrics

    @property
    def available_metrics(self) -> frozenset[CanonicalMetric]:
        return frozenset(self.metrics)

    def missing(self) -> frozenset[CanonicalMetric]:
        """Canonical metrics FootyStats has not been verified to supply."""
        return frozenset(CanonicalMetric) - self.available_metrics

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
    )


@lru_cache(maxsize=1)
def get_mapping() -> FootyStatsMapping:
    """The mapping, loaded once per process."""
    return load_mapping()
