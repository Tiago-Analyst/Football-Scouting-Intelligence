"""Recruitment weights that start from a named role.

WHY THIS EXISTS

The recruitment builder asks for eight numbers before it will do anything, and
the page opens on one profile - a progressive defensive midfielder - that most
visitors are not recruiting for. Someone who knows they want a ball-winning
midfielder has to guess how much "defensive activity" that is, and a guess
they cannot check is a worse starting point than the role definitions already
sitting in `config/player_roles.yaml`.

WHAT A PRESET IS

A translation, not a second scoring engine. Roles are defined mostly in
metrics; the builder weights intelligence scores. So each role's metric weight
is handed to the scores that contain that metric, split evenly when several
do, and the totals are rescaled to 100. The search that follows is the same
weighted search as before, over weights the user can see and change. Nothing
here ranks anybody.

WHAT IT CANNOT DO, AND SAYS SO

A role metric that belongs to no intelligence score has nowhere to go. It is
dropped and counted, never redistributed to a score that does not contain it,
because spreading an unmapped weight across the others would invent an
emphasis the role never had. `expressible` reports what survived.

Shot Stopper loses everything that way: its goalkeeping metrics are in no
intelligence score, so it has no preset at all rather than a misleading one.

ON EXPOSURE

Section 28 keeps role weights server-side, and these eight rounded numbers are
a coarse projection of them: they say how a role leans across the scores, not
which metrics it uses or what each is worth. The alternative - a preset the
user cannot see or adjust - would not be a starting point.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache

from app.analytics.intelligence import get_definitions
from app.analytics.metrics import DerivedMetric
from app.analytics.roles import RoleDefinition, get_roles

#: Weights are presented in steps of five. The builder's inputs step by five,
#: and a starting point offered to the nearest percentage point would imply a
#: precision this derivation does not have.
STEP = 5.0

#: Below this share of the role's own weight, what is left is not the role.
MINIMUM_EXPRESSIBLE = 0.5


@dataclass(frozen=True)
class RolePreset:
    """One role, expressed in the builder's vocabulary."""

    key: str
    label: str
    description: str
    position_groups: tuple[str, ...]
    #: Intelligence score key -> weight, in steps of five, summing to 100.
    weights: dict[str, float]
    #: Share of the role's own weight the scores could carry, 0-1.
    expressible: float
    caveat: str | None = None
    #: Role components no intelligence score covers, by label.
    unmapped: tuple[str, ...] = field(default_factory=tuple)


def _owners() -> dict[DerivedMetric, list[str]]:
    """Which intelligence scores each metric belongs to.

    A metric can sit in more than one - completed passes counts towards both
    ball progression and ball security - so attribution is shared rather than
    assigned to a winner.
    """
    owners: dict[DerivedMetric, list[str]] = defaultdict(list)
    for key, definition in get_definitions().items():
        for metric in definition.components:
            owners[metric].append(key)
    return owners


def _round_to_step(weights: dict[str, float]) -> dict[str, float]:
    """Round to the nearest `STEP`, keeping the total at 100.

    Rounding each weight on its own leaves a total of 95 or 105 often enough
    to be noticed, and a builder that says "100%" beside a column adding to
    105 undermines every other number on the page. The residue goes to the
    largest weight, where it moves the profile least in relative terms.
    """
    rounded = {k: round(v / STEP) * STEP for k, v in weights.items()}
    rounded = {k: v for k, v in rounded.items() if v > 0}
    if not rounded:
        return {}
    residue = 100.0 - sum(rounded.values())
    if residue:
        largest = max(rounded, key=lambda k: (rounded[k], k))
        rounded[largest] = max(STEP, rounded[largest] + residue)
    return dict(sorted(rounded.items(), key=lambda kv: (-kv[1], kv[0])))


def derive(role: RoleDefinition) -> RolePreset | None:
    """A role as builder weights, or `None` when too little of it survives.

    Returning `None` is the honest answer for a role the intelligence scores
    cannot describe. Offering a preset built from the fragment that happens to
    map would put a name on a profile that is not that role.
    """
    owners = _owners()
    accumulated: dict[str, float] = defaultdict(float)
    unmapped: list[str] = []
    total = 0.0

    for metric, weight in role.metric_weights.items():
        total += weight
        carriers = owners.get(metric)
        if not carriers:
            unmapped.append(metric.value)
            continue
        share = weight / len(carriers)
        for score in carriers:
            accumulated[score] += share

    # A role may also weight an intelligence score directly, in which case it
    # needs no translation.
    for score, weight in role.score_weights.items():
        total += weight
        accumulated[score] += weight

    carried = sum(accumulated.values())
    if total <= 0 or carried <= 0:
        return None

    expressible = carried / total
    if expressible < MINIMUM_EXPRESSIBLE:
        return None

    scaled = {k: v / carried * 100.0 for k, v in accumulated.items()}
    weights = _round_to_step(scaled)
    if not weights:
        return None

    return RolePreset(
        key=role.key,
        label=role.label,
        description=role.description,
        position_groups=tuple(g.value for g in role.position_groups),
        weights=weights,
        expressible=expressible,
        caveat=role.caveat,
        unmapped=tuple(sorted(unmapped)),
    )


@lru_cache(maxsize=1)
def get_presets() -> tuple[RolePreset, ...]:
    """Every role that can be expressed as builder weights."""
    return tuple(preset for role in get_roles().values() if (preset := derive(role)) is not None)
