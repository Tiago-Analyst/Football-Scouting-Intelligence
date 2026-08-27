"""Provider-independent identity resolution.

Two providers describe the same footballer with different identifiers, and
nothing guarantees their spellings agree. This resolves one source's players
against another's using several signals together, and reports how confident it
is about each decision.

The rule that shapes everything here: **never match on name alone** (spec
section 6). Names are not unique — a squad list will contain two players called
Silva — and providers disagree constantly about accents, middle names and name
order. A name is one signal among date of birth, nationality, club and position,
and on its own it is never enough.

Equally important, and easier to get wrong: **a wrong match is worse than no
match**. An unmatched player is visibly missing; a wrongly matched one silently
attaches somebody else's statistics to a real person's profile, and every
percentile, role score and recruitment ranking built on it inherits the error.
Everything below is therefore biased towards refusing: candidates that are too
close to each other are reported as ambiguous rather than resolved by picking
the higher score.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher
from enum import StrEnum

from app.schemas.canonical import PositionGroup
from app.schemas.market import normalize_name

# Auto-match floor. Below this nothing is written automatically; the pair goes
# to manual review instead.
DEFAULT_THRESHOLD = 0.90

# A best candidate must beat its runner-up by at least this much. Two players
# scoring 0.95 and 0.94 are not a 0.95 match - they are an unresolved question,
# and picking the higher one would be arbitrary.
DEFAULT_MARGIN = 0.05

# Fuzzy name bands, used by the confidence ladder.
VERY_STRONG_NAME = 0.92
STRONG_NAME = 0.85

# Blocks larger than this are skipped when a candidate has no date of birth.
# Without it, a common surname would pull thousands of comparisons.
MAX_SURNAME_BLOCK = 400


class MatchStatus(StrEnum):
    MATCHED = "matched"
    AMBIGUOUS = "ambiguous"
    UNMATCHED = "unmatched"
    MANUAL = "manual"


@dataclass(frozen=True)
class Identity:
    """One player as a single source describes them.

    Deliberately not tied to any provider: both sides of a resolution are
    expressed in this shape, so the engine never learns a provider's vocabulary.
    """

    source: str
    source_player_id: str
    full_name: str
    date_of_birth: date | None = None
    nationality: str | None = None
    club_name: str | None = None
    position_group: PositionGroup | None = None

    @property
    def normalized(self) -> str:
        return normalize_name(self.full_name)

    @property
    def tokens(self) -> tuple[str, ...]:
        return tuple(self.normalized.split())

    @property
    def surname(self) -> str:
        """Last token. A weak notion of surname, used only for blocking, never
        for deciding a match."""
        parts = self.tokens
        return parts[-1] if parts else ""


@dataclass
class MatchResult:
    source: Identity
    target: Identity | None
    confidence: float
    method: str
    status: MatchStatus
    reasons: list[str] = field(default_factory=list)
    runner_up: Identity | None = None
    runner_up_confidence: float = 0.0

    @property
    def is_decided(self) -> bool:
        return self.status in (MatchStatus.MATCHED, MatchStatus.MANUAL)


# ---------------------------------------------------------------------------
# Name comparison
# ---------------------------------------------------------------------------


def _token_score(left: str, right: str) -> float:
    """Similarity between two individual name tokens.

    Two cases matter enough to handle explicitly, because both are ordinary
    provider behaviour rather than corruption:

    - **An initial standing in for a given name.** "L. Farrugia" and "Liam
      Farrugia" are the same person, and treating `l` and `liam` as unrelated
      tokens loses a large share of real matches.
    - **A one-character difference.** "Vylius" against "Vilius" is a
      transliteration choice, not a different player.

    Anything below the near-identical band is discounted hard, so genuinely
    different names do not accumulate credit from incidental letter overlap.
    """
    if left == right:
        return 1.0
    if not left or not right:
        return 0.0

    # Initial against full given name.
    if len(left) == 1 and right.startswith(left):
        return 0.85
    if len(right) == 1 and left.startswith(right):
        return 0.85

    ratio = SequenceMatcher(None, left, right).ratio()
    # Only near-identical tokens count as agreement; the rest are damped so a
    # coincidental prefix cannot masquerade as a match.
    return ratio if ratio >= 0.80 else ratio * 0.5


def name_similarity(left: Identity, right: Identity) -> float:
    """Similarity between two player names, 0 to 1.

    Token-aware rather than a plain string ratio, because the disagreements that
    actually occur in football data are structural: one source carries the full
    registered name and the other a playing name, or the given and family names
    arrive in a different order. A character-level ratio handles neither well.

    Tokens are aligned greedily, then combined from three parts: how well the
    matched tokens agree, whether the surnames agree, and how much of the longer
    name was accounted for. Surname agreement is weighted separately because it
    discriminates far better than a given name does.
    """
    a, b = left.normalized, right.normalized
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    left_tokens, right_tokens = list(left.tokens), list(right.tokens)
    if set(left_tokens) == set(right_tokens):
        # Same words, different order.
        return 0.98

    smaller, larger = (
        (left_tokens, right_tokens)
        if len(left_tokens) <= len(right_tokens)
        else (right_tokens, left_tokens)
    )

    used: set[int] = set()
    scores: list[float] = []
    for token in smaller:
        best_score, best_index = 0.0, None
        for index, other in enumerate(larger):
            if index in used:
                continue
            score = _token_score(token, other)
            if score > best_score:
                best_score, best_index = score, index
        if best_index is not None:
            used.add(best_index)
        scores.append(best_score)

    if not scores:
        return 0.0

    mean_token = sum(scores) / len(scores)
    surname = _token_score(left.surname, right.surname)
    # A dropped middle name is normal, so incomplete coverage is penalised but
    # not treated as disagreement.
    coverage = len(scores) / len(larger)

    combined = 0.55 * mean_token + 0.30 * surname + 0.15 * coverage
    # Never returns 1.0: only an exact string match is certain.
    return min(0.97, combined)


def _same_club(left: Identity, right: Identity) -> bool | None:
    """Whether both sides agree on the club. `None` when either is unknown.

    Tri-state on purpose: a missing club must not read as a disagreement, or
    every player without club data would be penalised for it.
    """
    if not left.club_name or not right.club_name:
        return None
    a, b = normalize_name(left.club_name), normalize_name(right.club_name)
    if not a or not b:
        return None
    if a == b:
        return True
    # Club naming varies wildly ("Manchester United" / "Man Utd FC"), so a
    # shared distinctive token counts as agreement.
    return bool(set(a.split()) & set(b.split()))


def _same_nationality(left: Identity, right: Identity) -> bool | None:
    if not left.nationality or not right.nationality:
        return None
    return left.nationality.strip().lower() == right.nationality.strip().lower()


def _compatible_position(left: Identity, right: Identity) -> bool | None:
    if left.position_group is None or right.position_group is None:
        return None
    return left.position_group is right.position_group


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def score_pair(source: Identity, target: Identity) -> tuple[float, str, list[str]]:
    """Confidence that two identities describe the same player.

    Implements the ladder in spec section 6. Date of birth does the heavy
    lifting: it is high-cardinality, stable across providers, and present for
    99.9% of the Transfermarkt set. Name similarity alone never reaches the
    auto-match threshold, whatever its value.
    """
    reasons: list[str] = []
    name = name_similarity(source, target)
    dob_exact = source.date_of_birth is not None and source.date_of_birth == target.date_of_birth
    club = _same_club(source, target)
    nationality = _same_nationality(source, target)
    position = _compatible_position(source, target)

    reasons.append(f"name~{name:.2f}")
    if dob_exact:
        reasons.append("dob=exact")
    if club is not None:
        reasons.append(f"club={'same' if club else 'different'}")
    if nationality is not None:
        reasons.append(f"nationality={'same' if nationality else 'different'}")
    if position is not None:
        reasons.append(f"position={'same' if position else 'different'}")

    if dob_exact:
        if name >= 1.0:
            if club:
                return 1.00, "exact_name+dob+club", reasons
            return 0.95, "exact_name+dob", reasons
        if name >= VERY_STRONG_NAME:
            return 0.98, "dob+very_strong_name", reasons
        if name >= STRONG_NAME:
            # Supporting evidence lifts a merely strong name over the line;
            # without it this stays below the threshold on purpose.
            if nationality and club:
                return 0.92, "dob+strong_name+nationality+club", reasons
            if nationality or club:
                return 0.90, "dob+strong_name+supporting", reasons
            return 0.86, "dob+strong_name", reasons
        # A shared birthday is common enough that it cannot carry a weak name.
        return min(0.70, 0.45 + name * 0.3), "dob_only_weak_name", reasons

    # -- No exact date of birth ---------------------------------------------
    # Everything below stays under the auto-match threshold by construction.
    # Without a date of birth the evidence is not strong enough to write a
    # mapping automatically, however good the name looks.
    if source.date_of_birth and target.date_of_birth:
        same_year = source.date_of_birth.year == target.date_of_birth.year
        if not same_year:
            # Different birth years is positive evidence *against* a match.
            reasons.append("dob=conflicting")
            return min(0.30, name * 0.3), "dob_conflict", reasons
        reasons.append("dob=year_only")
        if name >= VERY_STRONG_NAME and (nationality or club):
            return 0.88, "birth_year+very_strong_name+supporting", reasons
        return min(0.75, name * 0.75), "birth_year+name", reasons

    reasons.append("dob=missing")
    if name >= 1.0 and nationality and club:
        return 0.85, "exact_name+nationality+club_no_dob", reasons
    if name >= VERY_STRONG_NAME and (nationality or club):
        return 0.72, "strong_name+supporting_no_dob", reasons
    return min(0.65, name * 0.65), "name_only", reasons


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


class IdentityResolver:
    """Resolves source identities against a fixed set of target identities."""

    def __init__(
        self,
        targets: list[Identity],
        *,
        threshold: float = DEFAULT_THRESHOLD,
        margin: float = DEFAULT_MARGIN,
        manual_overrides: dict[tuple[str, str], str] | None = None,
    ) -> None:
        self.targets = targets
        self.threshold = threshold
        self.margin = margin
        # (source, source_player_id) -> target source_player_id
        self.manual_overrides = manual_overrides or {}

        self._by_dob: dict[date, list[int]] = defaultdict(list)
        self._by_surname_year: dict[tuple[str, int], list[int]] = defaultdict(list)
        self._by_surname: dict[str, list[int]] = defaultdict(list)
        self._by_source_id: dict[str, Identity] = {}

        for index, identity in enumerate(targets):
            self._by_source_id[identity.source_player_id] = identity
            if identity.date_of_birth is not None:
                self._by_dob[identity.date_of_birth].append(index)
                self._by_surname_year[(identity.surname, identity.date_of_birth.year)].append(index)
            if identity.surname:
                self._by_surname[identity.surname].append(index)

    def _candidates(self, source: Identity) -> list[Identity]:
        """Narrow 50,000 targets to a handful worth scoring.

        Comparing every pair would be 50,000 comparisons per player. Blocking on
        date of birth and on surname-plus-birth-year keeps recall high while
        making the work linear in practice.
        """
        indexes: set[int] = set()
        if source.date_of_birth is not None:
            indexes.update(self._by_dob.get(source.date_of_birth, ()))
            indexes.update(
                self._by_surname_year.get((source.surname, source.date_of_birth.year), ())
            )
        elif source.surname:
            block = self._by_surname.get(source.surname, [])
            # A very large surname block without a date of birth cannot be
            # resolved confidently anyway, so scoring it wastes time.
            if len(block) <= MAX_SURNAME_BLOCK:
                indexes.update(block)
        return [self.targets[i] for i in indexes]

    def resolve(self, source: Identity) -> MatchResult:
        override = self.manual_overrides.get((source.source, source.source_player_id))
        if override is not None:
            target = self._by_source_id.get(override)
            if target is not None:
                return MatchResult(
                    source=source,
                    target=target,
                    confidence=1.0,
                    method="manual_override",
                    status=MatchStatus.MANUAL,
                    reasons=["manually confirmed"],
                )
            return MatchResult(
                source=source,
                target=None,
                confidence=0.0,
                method="manual_override_target_missing",
                status=MatchStatus.UNMATCHED,
                reasons=[f"override points at unknown target {override}"],
            )

        scored = [
            (confidence, method, reasons, target)
            for target in self._candidates(source)
            for confidence, method, reasons in [score_pair(source, target)]
        ]
        if not scored:
            return MatchResult(
                source=source,
                target=None,
                confidence=0.0,
                method="no_candidates",
                status=MatchStatus.UNMATCHED,
                reasons=["no blocking candidates"],
            )

        scored.sort(key=lambda item: item[0], reverse=True)
        best_confidence, best_method, best_reasons, best_target = scored[0]
        runner_up_confidence, runner_up = (
            (scored[1][0], scored[1][3]) if len(scored) > 1 else (0.0, None)
        )

        if best_confidence < self.threshold:
            return MatchResult(
                source=source,
                target=None,
                confidence=best_confidence,
                method=best_method,
                status=MatchStatus.UNMATCHED,
                reasons=best_reasons,
                runner_up=best_target,
                runner_up_confidence=best_confidence,
            )

        if best_confidence - runner_up_confidence < self.margin:
            # Two candidates this close is an unresolved question, not a match.
            return MatchResult(
                source=source,
                target=None,
                confidence=best_confidence,
                method=best_method,
                status=MatchStatus.AMBIGUOUS,
                reasons=[*best_reasons, f"runner-up {runner_up_confidence:.2f} within margin"],
                runner_up=runner_up,
                runner_up_confidence=runner_up_confidence,
            )

        return MatchResult(
            source=source,
            target=best_target,
            confidence=best_confidence,
            method=best_method,
            status=MatchStatus.MATCHED,
            reasons=best_reasons,
            runner_up=runner_up,
            runner_up_confidence=runner_up_confidence,
        )

    def resolve_all(self, sources: list[Identity]) -> list[MatchResult]:
        return [self.resolve(source) for source in sources]
