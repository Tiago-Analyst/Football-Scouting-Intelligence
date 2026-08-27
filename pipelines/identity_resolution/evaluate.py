"""Measure the resolver against known truth.

Resolving the mock performance players against Transfermarkt tests only one
half of the problem. Their names are invented, so the correct answer is "no
match" for every one of them: a useful check that the resolver does not invent
links, but it says nothing about whether it *finds* real ones.

Recall needs ground truth, so this builds a shadow source by perturbing real
Transfermarkt identities the way a second provider would actually differ from
the first — name order swapped, middle names dropped, a playing name instead of
a registered one, a missing birth date, a club written differently, the
occasional typo. Because each perturbed record remembers which player it came
from, precision and recall are measurable rather than asserted.

The perturbations are deliberately harsher than a real provider pairing, and
some are unresolvable by design (no date of birth and a truncated name). Recall
below 100% is therefore expected and correct: those records *should* fall to
manual review.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from pipelines.identity_resolution.matcher import (
    Identity,
    IdentityResolver,
    MatchResult,
    MatchStatus,
)


@dataclass
class Evaluation:
    total: int
    matched: int
    correct: int
    incorrect: int
    ambiguous: int
    unmatched: int

    @property
    def precision(self) -> float:
        """Of the matches made, how many were right.

        The number that matters most: a wrong match silently attaches one
        player's statistics to another's profile.
        """
        return self.correct / self.matched if self.matched else 1.0

    @property
    def recall(self) -> float:
        """Of the pairs that could have been found, how many were."""
        return self.correct / self.total if self.total else 0.0

    def render(self) -> str:
        lines = [
            f"  records            {self.total:>7,}",
            f"  matched            {self.matched:>7,}",
            f"    correct          {self.correct:>7,}",
            f"    incorrect        {self.incorrect:>7,}",
            f"  ambiguous          {self.ambiguous:>7,}",
            f"  unmatched          {self.unmatched:>7,}",
            "",
            f"  precision          {self.precision:>7.3%}",
            f"  recall             {self.recall:>7.3%}",
        ]
        return "\n".join(lines)


# Perturbations a second provider plausibly applies to the same player.
# Single-character substitutions only: str.maketrans rejects longer keys.
_TYPO_SWAPS = str.maketrans({"i": "y", "k": "c", "s": "z", "c": "k"})


def _swap_name_order(name: str, rng: random.Random) -> str:
    parts = name.split()
    if len(parts) < 2:
        return name
    return " ".join([parts[-1], *parts[:-1]])


def _drop_middle(name: str, rng: random.Random) -> str:
    parts = name.split()
    if len(parts) < 3:
        return name
    return f"{parts[0]} {parts[-1]}"


def _surname_only(name: str, rng: random.Random) -> str:
    parts = name.split()
    return parts[-1] if parts else name


def _initial_and_surname(name: str, rng: random.Random) -> str:
    parts = name.split()
    if len(parts) < 2:
        return name
    return f"{parts[0][0]}. {parts[-1]}"


def _typo(name: str, rng: random.Random) -> str:
    if len(name) < 5:
        return name
    index = rng.randrange(1, len(name) - 1)
    if name[index] == " ":
        return name
    return name[:index] + name[index].translate(_TYPO_SWAPS) + name[index + 1 :]


_NAME_PERTURBATIONS = [
    (0.40, lambda n, r: n),  # unchanged: providers often do agree
    (0.15, _swap_name_order),
    (0.15, _drop_middle),
    (0.10, _initial_and_surname),
    (0.10, _typo),
    (0.10, _surname_only),
]


def _perturb_name(name: str, rng: random.Random) -> str:
    roll = rng.random()
    cumulative = 0.0
    for weight, transform in _NAME_PERTURBATIONS:
        cumulative += weight
        if roll <= cumulative:
            return transform(name, rng)
    return name


def build_shadow_source(
    targets: list[Identity],
    *,
    sample: int = 2000,
    seed: int = 20260827,
    source_name: str = "shadow",
) -> tuple[list[Identity], dict[str, str]]:
    """Create a perturbed copy of `targets` plus the ground-truth mapping.

    Returns the shadow identities and `{shadow_id: true_target_id}`.
    """
    # S311: a seeded, reproducible generator is the point - the evaluation
    # must produce the same shadow set every run. No security use.
    rng = random.Random(seed)  # noqa: S311
    pool = list(targets)
    rng.shuffle(pool)
    chosen = pool[:sample]

    shadows: list[Identity] = []
    truth: dict[str, str] = {}

    for index, target in enumerate(chosen):
        shadow_id = f"s{index:06d}"
        truth[shadow_id] = target.source_player_id

        # 12% lose their date of birth, matching the coverage gaps a real
        # provider pairing shows.
        keep_dob = rng.random() > 0.12
        keep_nationality = rng.random() > 0.20
        keep_club = rng.random() > 0.30

        club = target.club_name
        if club and keep_club and rng.random() < 0.35:
            # Same club, written differently.
            club = club.replace(" FC", "").replace("FC ", "").strip() or club

        shadows.append(
            Identity(
                source=source_name,
                source_player_id=shadow_id,
                full_name=_perturb_name(target.full_name, rng),
                date_of_birth=target.date_of_birth if keep_dob else None,
                nationality=target.nationality if keep_nationality else None,
                club_name=club if keep_club else None,
                position_group=target.position_group,
            )
        )

    return shadows, truth


def evaluate(results: list[MatchResult], truth: dict[str, str]) -> Evaluation:
    matched = correct = incorrect = ambiguous = unmatched = 0

    for result in results:
        expected = truth.get(result.source.source_player_id)
        if result.status is MatchStatus.AMBIGUOUS:
            ambiguous += 1
        elif result.status is MatchStatus.UNMATCHED:
            unmatched += 1
        elif result.is_decided and result.target is not None:
            matched += 1
            if result.target.source_player_id == expected:
                correct += 1
            else:
                incorrect += 1

    return Evaluation(
        total=len(results),
        matched=matched,
        correct=correct,
        incorrect=incorrect,
        ambiguous=ambiguous,
        unmatched=unmatched,
    )


def evaluate_against_shadow(
    targets: list[Identity],
    *,
    sample: int = 2000,
    seed: int = 20260827,
    threshold: float | None = None,
) -> tuple[Evaluation, list[MatchResult], dict[str, str]]:
    shadows, truth = build_shadow_source(targets, sample=sample, seed=seed)
    resolver = (
        IdentityResolver(targets, threshold=threshold)
        if threshold is not None
        else IdentityResolver(targets)
    )
    results = resolver.resolve_all(shadows)
    return evaluate(results, truth), results, truth
