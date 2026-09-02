"""Placing a role score within its own role's distribution.

WHY THIS IS NEEDED
------------------

A raw role score is a weighted average of percentiles, and averaging pulls
results towards the middle. How far depends on how the weight is spread. A role
resting mostly on one component inherits that component's full spread, so its
scores run high and low freely. A role averaging six evenly weighted components
compresses: its very best player scores lower than the very best of the
concentrated role while being no less suited to the role.

So `Deep-Lying Playmaker 72` and `Shot Stopper 78` are not comparable numbers.
Picking a player's best role by comparing them directly picks the role with the
looser distribution, not the role the player suits.

These tests hold the fix: a second figure measured *within* one role's
distribution, which is comparable, with the raw score kept and shown because it
is the one that decomposes into an explanation.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.analytics.percentiles import ComparisonContext, PercentileScope
from app.analytics.roles import MIN_ROLE_POPULATION, RoleFit, RoleScore, normalise_fits
from app.schemas.canonical import PositionGroup


def context(population: int = 50) -> ComparisonContext:
    return ComparisonContext(
        scope=PercentileScope.COMPETITION,
        position_group=PositionGroup.DM,
        season_id="2026",
        competition_ids=("c1",),
        population_size=population,
        minimum_minutes=0,
    )


def score(key: str, value: float | None) -> RoleScore:
    return RoleScore(
        key=key,
        label=key.replace("_", " ").title(),
        score=value,
        coverage=1.0,
        context=context(),
        components=[],
        missing=[],
    )


def fits_from(scores_by_player: dict[str, list[RoleScore]]) -> dict[str, RoleFit]:
    return {
        key: RoleFit(best=scores[0], alternatives=scores[1:])
        for key, scores in scores_by_player.items()
    }


class TestTheRawScoreIsPreserved:
    def test_normalising_never_changes_a_raw_score(self) -> None:
        """The explainable number must survive untouched.

        It decomposes into the components that produced it. Rescaling it would
        buy comparability at the cost of the only thing that makes a role fit
        arguable with.
        """
        raw = {f"p{i}": [score("a", float(i))] for i in range(30)}
        placed = normalise_fits(fits_from(raw))
        for key, fit in placed.items():
            assert fit.best is not None
            assert fit.best.score == raw[key][0].score

    def test_an_unavailable_score_stays_unavailable(self) -> None:
        """A role that could not be computed is not a role scored at nought."""
        players = {f"p{i}": [score("a", float(i))] for i in range(15)}
        players["missing"] = [score("a", None)]
        placed = normalise_fits(fits_from(players))
        best = placed["missing"].best
        assert best is not None
        assert best.score is None
        assert best.role_fit_percentile is None


class TestTheStanding:
    def test_a_percentile_is_computed_within_the_role(self) -> None:
        players = {f"p{i}": [score("a", float(i))] for i in range(20)}
        placed = normalise_fits(fits_from(players))

        assert placed["p19"].best is not None
        assert placed["p19"].best.role_fit_percentile == pytest.approx(97.5)
        assert placed["p0"].best is not None
        assert placed["p0"].best.role_fit_percentile == pytest.approx(2.5)

    def test_the_population_it_was_measured_against_is_reported(self) -> None:
        players = {f"p{i}": [score("a", float(i))] for i in range(20)}
        placed = normalise_fits(fits_from(players))
        assert placed["p5"].best is not None
        assert placed["p5"].best.role_population == 20

    def test_too_few_players_means_no_standing_rather_than_a_bad_one(self) -> None:
        """A rank against four players is noise wearing a number."""
        few = MIN_ROLE_POPULATION - 1
        players = {f"p{i}": [score("a", float(i))] for i in range(few)}
        placed = normalise_fits(fits_from(players))
        for fit in placed.values():
            assert fit.best is not None
            assert fit.best.role_fit_percentile is None
            assert fit.best.role_population == few

    def test_without_a_standing_the_raw_score_still_orders_the_roles(self) -> None:
        """Falling back is stated, not silent, and beats naming no best role."""
        players = {"solo": [score("a", 40.0), score("b", 70.0)]}
        placed = normalise_fits(fits_from(players))
        assert placed["solo"].best is not None
        assert placed["solo"].best.key == "b"
        assert placed["solo"].best.role_fit_percentile is None


class TestDifferentlyShapedDistributions:
    """The case the whole change exists for.

    `concentrated` is a role whose weight sits mostly on one component, so its
    raw scores span nearly the full range. `compressed` averages many evenly
    weighted components, so its scores bunch in the middle. Both are modelled
    directly here rather than through the scoring engine, because what is being
    tested is the comparison, not the weighting.
    """

    #: 30 players. Concentrated spans 10-90; compressed spans 45-59.
    @staticmethod
    def population() -> dict[str, list[RoleScore]]:
        players: dict[str, list[RoleScore]] = {}
        for i in range(30):
            players[f"p{i}"] = [
                score("concentrated", 10.0 + (80.0 * i / 29)),
                score("compressed", 45.0 + (14.0 * i / 29)),
            ]
        return players

    def test_raw_scores_are_not_comparable_across_roles(self) -> None:
        """The premise. Without this being true there is nothing to fix."""
        players = self.population()
        top = players["p29"]
        concentrated = next(s for s in top if s.key == "concentrated")
        compressed = next(s for s in top if s.key == "compressed")

        assert concentrated.score is not None and compressed.score is not None
        # The same player is top of both roles, and the raw numbers disagree
        # by more than 30 points about how well they fit.
        assert concentrated.score - compressed.score > 30

    def test_the_best_of_each_role_reaches_the_same_standing(self) -> None:
        """Fairness, stated as an equality.

        Being the best of thirty at a compressed role is the same achievement
        as being the best of thirty at a spread one, and the normalised figure
        says so where the raw one does not.
        """
        placed = normalise_fits(fits_from(self.population()))
        top = {s.key: s for s in placed["p29"].all_scores}
        assert top["concentrated"].role_fit_percentile == pytest.approx(
            top["compressed"].role_fit_percentile
        )

    def test_best_role_is_chosen_by_standing_not_by_raw_score(self) -> None:
        """A player better suited to the compressed role must be told so.

        Here p10 is ordinary at the concentrated role and near the top of the
        compressed one. The raw scores still favour the concentrated role -
        which is exactly the mistake.
        """
        players = self.population()
        # Lift this player to near the top of the compressed distribution while
        # leaving them mid-table in the concentrated one.
        players["p10"] = [
            score("concentrated", 38.0),
            score("compressed", 58.5),
        ]
        placed = normalise_fits(fits_from(players))

        best = placed["p10"].best
        assert best is not None
        assert best.key == "compressed"
        # And the raw score that would have chosen otherwise is still there.
        assert best.score == 58.5
        assert best.role_fit_percentile is not None
        assert best.role_fit_percentile > 80

    def test_ordering_inside_one_role_is_unchanged(self) -> None:
        """Normalisation is monotonic: it re-scales, it does not re-order."""
        placed = normalise_fits(fits_from(self.population()))
        standings = [
            next(
                s.role_fit_percentile for s in placed[f"p{i}"].all_scores if s.key == "concentrated"
            )
            for i in range(30)
        ]
        assert standings == sorted(s or 0.0 for s in standings)


class TestTheShapeOfTheResult:
    def test_every_role_a_player_was_scored_for_survives(self) -> None:
        players = {f"p{i}": [score("a", float(i)), score("b", float(30 - i))] for i in range(20)}
        placed = normalise_fits(fits_from(players))
        for fit in placed.values():
            assert {s.key for s in fit.all_scores} == {"a", "b"}

    def test_a_player_with_no_roles_stays_empty(self) -> None:
        empty = {"nobody": RoleFit(best=None, alternatives=[])}
        placed = normalise_fits(empty)
        assert placed["nobody"].best is None
        assert placed["nobody"].alternatives == []

    def test_the_caveat_on_a_role_is_carried_through(self) -> None:
        """Roles built on substituted metrics carry a warning. Losing it in the
        normalisation pass would strip the qualification from the number."""
        players = {
            f"p{i}": [replace(score("a", float(i)), caveat="Tackle volume, not success.")]
            for i in range(20)
        }
        placed = normalise_fits(fits_from(players))
        assert placed["p5"].best is not None
        assert placed["p5"].best.caveat == "Tackle volume, not success."
