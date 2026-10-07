"""Everything a role is scored from must be printable on the player's page.

The role breakdown's whole claim is that a reader can check it. A validation
audit found six metrics that broke that claim by being used and never shown:
40% of the Poacher score came from shots on target, shot conversion and shot
quality, none of which appeared anywhere on the player's profile. Dribbled
past carried 20% of the Defensive Full-Back role - and 32% of what actually
drove one audited player's score - and was equally invisible.

Adding them to the list was the easy half. The half that matters is this file:
two hand-maintained lists in different files will drift apart again, and the
only way the rule survives is if something fails when they do.
"""

from __future__ import annotations

import pytest

from app.analytics.metrics import METRIC_FAMILIES, DerivedMetric
from app.analytics.roles import get_roles
from app.api.v1.players import PROFILE_METRICS


def role_metrics() -> dict[DerivedMetric, list[tuple[str, float]]]:
    """Every metric any role scores from, and which roles weight it."""
    used: dict[DerivedMetric, list[tuple[str, float]]] = {}
    for key, role in get_roles().items():
        for metric, weight in role.metric_weights.items():
            used.setdefault(metric, []).append((key, weight))
    return used


class TestNothingScoresInvisibly:
    def test_every_role_metric_is_inspectable(self) -> None:
        shown = set(PROFILE_METRICS)
        hidden = {m: users for m, users in role_metrics().items() if m not in shown}
        assert not hidden, (
            "these metrics contribute to a role score and appear on no profile: "
            + "; ".join(
                f"{m.value} ({', '.join(f'{k} {w:.0f}%' for k, w in users)})"
                for m, users in sorted(hidden.items(), key=lambda kv: kv[0].value)
            )
        )

    def test_the_poacher_is_fully_checkable(self) -> None:
        """The case the audit named, pinned by weight rather than by count.

        40% of this role used to be unverifiable. If a future edit moves those
        components out of the profile again, this says so in the role's own
        terms.
        """
        poacher = get_roles()["poacher"]
        shown = set(PROFILE_METRICS)
        invisible = sum(w for m, w in poacher.metric_weights.items() if m not in shown)
        assert invisible == 0, f"{invisible:.0f}% of the Poacher score cannot be checked"

    @pytest.mark.parametrize(
        ("role", "metric"),
        [
            ("defensive_full_back", DerivedMetric.DRIBBLED_PAST_PER90),
            ("target_forward", DerivedMetric.AERIAL_DUELS_WON_PER90),
            ("shot_stopper", DerivedMetric.INSIDE_BOX_SAVES_PER90),
            ("poacher", DerivedMetric.SHOT_CONVERSION),
            ("poacher", DerivedMetric.SHOT_QUALITY),
            ("poacher", DerivedMetric.SHOTS_ON_TARGET_PER90),
        ],
    )
    def test_each_metric_the_audit_found(self, role: str, metric: DerivedMetric) -> None:
        assert metric in get_roles()[role].metric_weights, "test is out of date"
        assert metric in PROFILE_METRICS


class TestTheListItself:
    def test_it_holds_no_duplicates(self) -> None:
        assert len(PROFILE_METRICS) == len(set(PROFILE_METRICS))

    def test_families_stay_contiguous(self) -> None:
        """The comparison draws a heading wherever the family changes.

        A metric inserted away from its family-mates would print that family's
        heading twice, reading as two different sections with one name.
        """
        seen: list[str] = []
        for metric in PROFILE_METRICS:
            family = METRIC_FAMILIES[metric]
            if not seen or seen[-1] != family:
                seen.append(family)
        assert len(seen) == len(set(seen)), f"a family is split across the list: {seen}"

    def test_every_listed_metric_has_a_family(self) -> None:
        missing = [m.value for m in PROFILE_METRICS if m not in METRIC_FAMILIES]
        assert missing == []
