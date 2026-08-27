"""Fabricated performance data for demo mode.

EVERY NAME AND NUMBER PRODUCED HERE IS INVENTED. No competition, club or player
below corresponds to a real one, and no figure describes a real performance.
Any resemblance to a real person is coincidental. `ProviderInfo.is_mock` is
True so the UI can label it, and `validated` is False because nothing here has
been checked against a real data source - there is no real data source.

Its purpose is to exercise the whole analytical stack - percentiles, intelligence
scores, role scores, similarity, recruitment ranking - before a real provider
exists. That imposes two requirements a naive random generator would fail:

**Internal consistency.** Completed passes cannot exceed attempted, goals cannot
exceed shots on target, aerial duels are a subset of duels. Violations would not
merely look wrong; they would produce impossible ratios and poison every
percentile computed from them. Totals are therefore derived from rates and
clamped against their parent quantity.

**Structure, not noise.** Uniform random numbers would make every player
identical once ranked, so role scores and similarity would be meaningless. Each
player instead gets independent ability factors per skill family - progression,
creation, defending, duelling, dribbling, finishing, aerial - so recognisable
archetypes emerge and the engines above have real signal to find.

Generation is seeded and deterministic: the same seed always yields the same
dataset, so tests and screenshots are stable.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache

from app.providers.base import PerformanceDataProvider, UnknownEntityError
from app.schemas.canonical import (
    CanonicalMetric,
    Club,
    Competition,
    PlayerIdentity,
    PlayerSeasonStats,
    PositionGroup,
    PreferredFoot,
    ProviderInfo,
    Season,
)

DEMO_DATA_WARNING = (
    "Fabricated demonstration data. Players, clubs and competitions are "
    "invented and no figure describes a real performance."
)

MATCHES_PER_SEASON = 34
SEASON_ID = "2026-2027"
REFERENCE_DATE = date(2027, 1, 1)

# --------------------------------------------------------------------------
# Naming
# --------------------------------------------------------------------------
# Syllable pools rather than real-name lists, so generated names are
# pronounceable but are not drawn from any register of actual people.

_FIRST_A = [
    "Ar",
    "Bel",
    "Cor",
    "Dan",
    "El",
    "Fen",
    "Gar",
    "Hal",
    "Iv",
    "Jor",
    "Kal",
    "Lem",
    "Mar",
    "Nor",
    "Ost",
    "Pel",
    "Rin",
    "Sav",
    "Tor",
    "Vel",
]
_FIRST_B = ["an", "en", "im", "os", "ur", "ik", "el", "ar", "us", "io"]

_LAST_A = [
    "Brack",
    "Cald",
    "Dorn",
    "Ellsh",
    "Farn",
    "Grish",
    "Holm",
    "Isk",
    "Kren",
    "Lund",
    "Merv",
    "Norr",
    "Ovel",
    "Presk",
    "Quill",
    "Rask",
    "Sten",
    "Thal",
    "Urven",
    "Vask",
    "Wender",
    "Yarn",
    "Zelm",
]
_LAST_B = [
    "ard",
    "berg",
    "dahl",
    "ens",
    "ford",
    "gaard",
    "holt",
    "ijk",
    "kov",
    "lund",
    "mark",
    "nes",
    "orp",
    "quist",
    "rud",
    "sen",
    "strom",
    "vik",
]

_NATIONALITIES = [
    "Portugal",
    "Spain",
    "France",
    "Netherlands",
    "Belgium",
    "Denmark",
    "Sweden",
    "Norway",
    "Austria",
    "Croatia",
    "Serbia",
    "Poland",
    "Brazil",
    "Argentina",
    "Uruguay",
    "Colombia",
    "Nigeria",
    "Ghana",
    "Senegal",
    "Morocco",
    "Japan",
    "South Korea",
    "United States",
    "Canada",
]

# Fictional competitions. Deliberately not modelled on real leagues.
_COMPETITION_BLUEPRINTS = [
    ("Verdant League", "Verdania", 1),
    ("Northlands Premier", "Northland", 1),
    ("Meridian Liga", "Meridia", 1),
    ("Kestrel Division", "Kestria", 1),
]

_CLUB_PREFIX = [
    "Alder",
    "Bram",
    "Coval",
    "Dunmar",
    "Eskval",
    "Fairholt",
    "Glenn",
    "Harrow",
    "Ilmen",
    "Jarvic",
    "Kelby",
    "Larkin",
    "Mordenn",
    "Netherby",
    "Ostmark",
    "Pellar",
    "Rothen",
    "Selby",
    "Tarnow",
    "Underhill",
]
_CLUB_SUFFIX = ["City", "United", "Athletic", "Rovers", "FC", "Town", "Wanderers", "Sporting"]


# --------------------------------------------------------------------------
# Position profiles
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PositionProfile:
    """Baseline per-90 output for a position group.

    Rates, not totals: multiplying by actual minutes is what makes a fringe
    player's totals small without distorting their per-90 profile, which is
    exactly the behaviour the sample-size rules need to be tested against.
    """

    raw_positions: tuple[str, ...]
    squad_slots: int

    passes: float
    pass_completion: float
    progressive_passes: float
    key_passes: float
    crosses: float
    cross_accuracy: float
    dribbles: float
    dribble_success: float
    tackles: float
    tackle_success: float
    interceptions: float
    blocks: float
    clearances: float
    duels: float
    duel_win_rate: float
    aerial_share: float
    aerial_win_rate: float
    fouls_committed: float
    fouls_drawn: float
    dispossessed: float
    dribbled_past: float
    shots: float
    shot_accuracy: float
    npxg: float
    xa: float
    penalty_taker: float = 0.0

    # Goalkeeping. Zero for outfield profiles.
    saves: float = 0.0
    inside_box_share: float = 0.0
    goals_conceded: float = 0.0
    clean_sheet_rate: float = 0.0

    height_mean: int = 181
    height_sd: int = 6


PROFILES: dict[PositionGroup, PositionProfile] = {
    PositionGroup.GK: PositionProfile(
        raw_positions=("GK",),
        squad_slots=3,
        passes=30.0,
        pass_completion=0.72,
        progressive_passes=2.0,
        key_passes=0.02,
        crosses=0.0,
        cross_accuracy=0.0,
        dribbles=0.1,
        dribble_success=0.60,
        tackles=0.08,
        tackle_success=0.70,
        interceptions=0.20,
        blocks=0.05,
        clearances=1.10,
        duels=0.70,
        duel_win_rate=0.62,
        aerial_share=0.55,
        aerial_win_rate=0.68,
        fouls_committed=0.06,
        fouls_drawn=0.15,
        dispossessed=0.10,
        dribbled_past=0.10,
        shots=0.01,
        shot_accuracy=0.10,
        npxg=0.002,
        xa=0.01,
        saves=3.10,
        inside_box_share=0.62,
        goals_conceded=1.25,
        clean_sheet_rate=0.28,
        height_mean=190,
        height_sd=4,
    ),
    PositionGroup.CB: PositionProfile(
        raw_positions=("CB", "LCB", "RCB"),
        squad_slots=5,
        passes=55.0,
        pass_completion=0.88,
        progressive_passes=4.0,
        key_passes=0.20,
        crosses=0.15,
        cross_accuracy=0.22,
        dribbles=0.40,
        dribble_success=0.58,
        tackles=1.60,
        tackle_success=0.66,
        interceptions=1.50,
        blocks=0.90,
        clearances=4.20,
        duels=9.50,
        duel_win_rate=0.60,
        aerial_share=0.47,
        aerial_win_rate=0.62,
        fouls_committed=1.00,
        fouls_drawn=0.70,
        dispossessed=0.50,
        dribbled_past=0.60,
        shots=0.50,
        shot_accuracy=0.30,
        npxg=0.060,
        xa=0.030,
        height_mean=188,
        height_sd=5,
    ),
    PositionGroup.FB_WB: PositionProfile(
        raw_positions=("LB", "RB", "LWB", "RWB"),
        squad_slots=4,
        passes=48.0,
        pass_completion=0.82,
        progressive_passes=4.5,
        key_passes=0.90,
        crosses=2.80,
        cross_accuracy=0.25,
        dribbles=1.80,
        dribble_success=0.55,
        tackles=2.20,
        tackle_success=0.62,
        interceptions=1.30,
        blocks=0.50,
        clearances=1.80,
        duels=10.00,
        duel_win_rate=0.52,
        aerial_share=0.20,
        aerial_win_rate=0.50,
        fouls_committed=1.20,
        fouls_drawn=1.00,
        dispossessed=1.20,
        dribbled_past=1.10,
        shots=0.70,
        shot_accuracy=0.30,
        npxg=0.080,
        xa=0.150,
        height_mean=179,
        height_sd=5,
    ),
    PositionGroup.DM: PositionProfile(
        raw_positions=("DM", "CDM"),
        squad_slots=3,
        passes=62.0,
        pass_completion=0.89,
        progressive_passes=5.5,
        key_passes=0.80,
        crosses=0.50,
        cross_accuracy=0.24,
        dribbles=1.00,
        dribble_success=0.60,
        tackles=2.60,
        tackle_success=0.65,
        interceptions=1.80,
        blocks=0.70,
        clearances=1.50,
        duels=11.00,
        duel_win_rate=0.55,
        aerial_share=0.23,
        aerial_win_rate=0.55,
        fouls_committed=1.50,
        fouls_drawn=1.20,
        dispossessed=1.00,
        dribbled_past=0.90,
        shots=0.80,
        shot_accuracy=0.30,
        npxg=0.080,
        xa=0.100,
        height_mean=183,
        height_sd=5,
    ),
    PositionGroup.CM: PositionProfile(
        raw_positions=("CM", "LCM", "RCM"),
        squad_slots=3,
        passes=58.0,
        pass_completion=0.87,
        progressive_passes=5.0,
        key_passes=1.30,
        crosses=0.80,
        cross_accuracy=0.24,
        dribbles=1.60,
        dribble_success=0.60,
        tackles=2.10,
        tackle_success=0.62,
        interceptions=1.30,
        blocks=0.50,
        clearances=0.90,
        duels=10.50,
        duel_win_rate=0.53,
        aerial_share=0.19,
        aerial_win_rate=0.50,
        fouls_committed=1.40,
        fouls_drawn=1.30,
        dispossessed=1.40,
        dribbled_past=0.80,
        shots=1.20,
        shot_accuracy=0.33,
        npxg=0.150,
        xa=0.160,
        height_mean=181,
        height_sd=5,
    ),
    PositionGroup.AM: PositionProfile(
        raw_positions=("AM", "CAM"),
        squad_slots=2,
        passes=45.0,
        pass_completion=0.84,
        progressive_passes=4.2,
        key_passes=2.20,
        crosses=1.20,
        cross_accuracy=0.24,
        dribbles=3.00,
        dribble_success=0.55,
        tackles=1.40,
        tackle_success=0.60,
        interceptions=0.80,
        blocks=0.30,
        clearances=0.40,
        duels=9.50,
        duel_win_rate=0.48,
        aerial_share=0.13,
        aerial_win_rate=0.42,
        fouls_committed=1.10,
        fouls_drawn=1.80,
        dispossessed=2.20,
        dribbled_past=0.50,
        shots=2.00,
        shot_accuracy=0.36,
        npxg=0.280,
        xa=0.280,
        penalty_taker=0.25,
        height_mean=178,
        height_sd=5,
    ),
    PositionGroup.WINGER: PositionProfile(
        raw_positions=("LW", "RW", "LM", "RM"),
        squad_slots=2,
        passes=35.0,
        pass_completion=0.80,
        progressive_passes=3.2,
        key_passes=1.80,
        crosses=3.20,
        cross_accuracy=0.24,
        dribbles=5.00,
        dribble_success=0.50,
        tackles=1.20,
        tackle_success=0.58,
        interceptions=0.60,
        blocks=0.25,
        clearances=0.40,
        duels=11.00,
        duel_win_rate=0.45,
        aerial_share=0.12,
        aerial_win_rate=0.40,
        fouls_committed=0.90,
        fouls_drawn=2.20,
        dispossessed=2.80,
        dribbled_past=0.50,
        shots=2.20,
        shot_accuracy=0.35,
        npxg=0.300,
        xa=0.240,
        penalty_taker=0.15,
        height_mean=177,
        height_sd=5,
    ),
    PositionGroup.FORWARD: PositionProfile(
        raw_positions=("ST", "CF"),
        squad_slots=2,
        passes=24.0,
        pass_completion=0.75,
        progressive_passes=1.60,
        key_passes=1.10,
        crosses=0.50,
        cross_accuracy=0.22,
        dribbles=2.60,
        dribble_success=0.50,
        tackles=0.70,
        tackle_success=0.55,
        interceptions=0.40,
        blocks=0.25,
        clearances=0.60,
        duels=11.00,
        duel_win_rate=0.44,
        aerial_share=0.41,
        aerial_win_rate=0.45,
        fouls_committed=1.20,
        fouls_drawn=1.60,
        dispossessed=2.40,
        dribbled_past=0.30,
        shots=3.20,
        shot_accuracy=0.38,
        npxg=0.480,
        xa=0.150,
        penalty_taker=0.45,
        height_mean=185,
        height_sd=6,
    ),
}


@dataclass
class _Abilities:
    """Independent skill factors, centred on 1.0.

    Independence is the point: a player can progress the ball well and defend
    badly. Scaling every metric by one overall rating would make all players
    collinear, and similarity and role scores would collapse to a single
    quality ordering.
    """

    progression: float
    creation: float
    defending: float
    duelling: float
    dribbling: float
    finishing: float
    aerial: float
    retention: float


@dataclass
class MockDataset:
    """A generated demo universe."""

    competitions: list[Competition] = field(default_factory=list)
    seasons: list[Season] = field(default_factory=list)
    clubs: list[Club] = field(default_factory=list)
    players: list[PlayerIdentity] = field(default_factory=list)
    stats: list[PlayerSeasonStats] = field(default_factory=list)
    # Mean ability per player, keyed by source id. Internal to the mock
    # modules: it lets MockMarketProvider make valuations track output, so demo
    # market data is not simply unrelated to demo performance data.
    player_quality: dict[str, float] = field(default_factory=dict)

    def stats_by_player(self) -> dict[tuple[str, str], PlayerSeasonStats]:
        return {(s.source_player_id, s.season_id): s for s in self.stats}


def _jitter(rng: random.Random, spread: float = 0.18) -> float:
    """Multiplicative noise, clamped so a single draw cannot produce an outlier
    that dominates an entire percentile distribution."""
    return max(0.35, min(2.20, rng.gauss(1.0, spread)))


def _ability(rng: random.Random) -> float:
    """One skill factor. Slightly right-skewed, as real talent distributions are."""
    return max(0.40, min(2.30, rng.lognormvariate(0.0, 0.26)))


def _damped(ability: float, weight: float) -> float:
    """Blend a skill factor towards 1.0.

    Applied where an undamped factor produces an unrealistic tail. Key passes
    are the clearest case: the median was right, but multiplying a 2.2/90
    baseline by an unconstrained ability factor pushed the 99th percentile to
    5.05 per 90 - a figure no real creator sustains over a season. Damping
    keeps the centre of the distribution while pulling the extremes in, so the
    spread still carries signal for role scoring.
    """
    return (1.0 - weight) + weight * ability


def _count(rate_per90: float, minutes: int, rng: random.Random, spread: float = 0.18) -> int:
    """Convert a per-90 rate into a season total for the minutes actually played."""
    expected = rate_per90 * (minutes / 90.0) * _jitter(rng, spread)
    return max(0, round(expected))


def _subset(total: int, rate: float, rng: random.Random, spread: float = 0.10) -> int:
    """A quantity that is by definition part of `total` - completed of attempted,
    won of contested. Clamped to `total`, which is what keeps every derived
    ratio inside 0-1."""
    if total <= 0:
        return 0
    value = round(total * max(0.0, min(1.0, rate * _jitter(rng, spread))))
    return max(0, min(total, value))


def _generate_dataset(seed: int, competitions: int, clubs_per_competition: int) -> MockDataset:
    # S311: a seeded, reproducible PRNG is exactly what is wanted. This
    # generates demonstration statistics, never tokens or secrets, and a
    # cryptographic generator could not produce a repeatable dataset.
    rng = random.Random(seed)  # noqa: S311
    dataset = MockDataset()

    dataset.seasons = [Season(season_id=SEASON_ID, name="2026/27", start_year=2026, end_year=2027)]

    used_club_names: set[str] = set()
    player_counter = 0

    for comp_index in range(min(competitions, len(_COMPETITION_BLUEPRINTS))):
        comp_name, country, tier = _COMPETITION_BLUEPRINTS[comp_index]
        competition = Competition(
            competition_id=f"mock-comp-{comp_index + 1:02d}",
            name=comp_name,
            country=country,
            tier=tier,
        )
        dataset.competitions.append(competition)

        for club_index in range(clubs_per_competition):
            club_name = (
                f"{_CLUB_PREFIX[club_index % len(_CLUB_PREFIX)]} "
                f"{_CLUB_SUFFIX[(club_index + comp_index) % len(_CLUB_SUFFIX)]}"
            )
            while club_name in used_club_names:
                club_name += "."
            used_club_names.add(club_name)

            club = Club(
                club_id=f"{competition.competition_id}-club-{club_index + 1:02d}",
                name=club_name,
                country=country,
                competition_id=competition.competition_id,
            )
            dataset.clubs.append(club)

            for group, profile in PROFILES.items():
                for _ in range(profile.squad_slots):
                    player_counter += 1
                    identity, stats, quality = _generate_player(
                        rng, player_counter, group, profile, club, competition
                    )
                    dataset.players.append(identity)
                    dataset.stats.append(stats)
                    dataset.player_quality[identity.source_player_id] = quality

    return dataset


def _generate_player(
    rng: random.Random,
    counter: int,
    group: PositionGroup,
    profile: PositionProfile,
    club: Club,
    competition: Competition,
) -> tuple[PlayerIdentity, PlayerSeasonStats, float]:
    player_id = f"mock-p-{counter:06d}"

    name = (
        f"{rng.choice(_FIRST_A)}{rng.choice(_FIRST_B)} {rng.choice(_LAST_A)}{rng.choice(_LAST_B)}"
    )

    age = max(16, min(38, round(rng.gauss(25.0, 4.2))))
    birth_year = REFERENCE_DATE.year - age
    date_of_birth = date(birth_year, rng.randint(1, 12), rng.randint(1, 28))

    # Squad role drives playing time, which is what produces the full-sample,
    # low-sample and insufficient-sample populations the minutes rules need.
    role_roll = rng.random()
    if role_roll < 0.55:
        appearances = rng.randint(24, MATCHES_PER_SEASON)
        minutes_per_appearance = rng.uniform(72, 89)
    elif role_roll < 0.82:
        appearances = rng.randint(12, 27)
        minutes_per_appearance = rng.uniform(45, 72)
    else:
        appearances = rng.randint(2, 14)
        minutes_per_appearance = rng.uniform(18, 48)

    minutes = int(min(appearances * 90, round(appearances * minutes_per_appearance)))
    starts = min(appearances, round(appearances * min(1.0, minutes_per_appearance / 90.0)))

    abilities = _Abilities(
        progression=_ability(rng),
        creation=_ability(rng),
        defending=_ability(rng),
        duelling=_ability(rng),
        dribbling=_ability(rng),
        finishing=_ability(rng),
        aerial=_ability(rng),
        retention=_ability(rng),
    )

    stats = _generate_stats(
        rng,
        player_id,
        group,
        profile,
        club,
        competition,
        abilities,
        appearances,
        starts,
        minutes,
    )

    identity = PlayerIdentity(
        source_player_id=player_id,
        full_name=name,
        date_of_birth=date_of_birth,
        nationality=rng.choice(_NATIONALITIES),
        secondary_nationality=(rng.choice(_NATIONALITIES) if rng.random() < 0.18 else None),
        preferred_foot=_pick_foot(rng, group),
        height_cm=max(155, min(215, round(rng.gauss(profile.height_mean, profile.height_sd)))),
        raw_position=rng.choice(profile.raw_positions),
        position_group=group,
        club_id=club.club_id,
        competition_id=competition.competition_id,
    )

    quality = (
        abilities.progression
        + abilities.creation
        + abilities.defending
        + abilities.duelling
        + abilities.dribbling
        + abilities.finishing
        + abilities.aerial
        + abilities.retention
    ) / 8.0
    return identity, stats, quality


def _pick_foot(rng: random.Random, group: PositionGroup) -> PreferredFoot:
    roll = rng.random()
    if roll < 0.06:
        return PreferredFoot.BOTH
    # Left-footedness is over-represented on the left of defence and midfield.
    left_bias = 0.42 if group in {PositionGroup.CB, PositionGroup.FB_WB} else 0.26
    return PreferredFoot.LEFT if rng.random() < left_bias else PreferredFoot.RIGHT


def _generate_stats(
    rng: random.Random,
    player_id: str,
    group: PositionGroup,
    profile: PositionProfile,
    club: Club,
    competition: Competition,
    ab: _Abilities,
    appearances: int,
    starts: int,
    minutes: int,
) -> PlayerSeasonStats:
    """Build season totals, deriving every dependent quantity from its parent.

    Order matters: a subset is always computed from the total it belongs to, so
    the constraints hold by construction rather than by a later repair pass.
    """
    # -- Passing -------------------------------------------------------------
    passes = _count(profile.passes, minutes, rng, 0.14)
    passes_completed = _subset(
        passes, profile.pass_completion * (0.94 + 0.06 * ab.retention), rng, 0.05
    )
    progressive_passes = min(
        passes, _count(profile.progressive_passes * ab.progression, minutes, rng)
    )
    key_passes = min(
        passes, _count(profile.key_passes * _damped(ab.creation, 0.62), minutes, rng, 0.20)
    )

    crosses = _count(profile.crosses * ab.creation, minutes, rng, 0.28)
    accurate_crosses = _subset(crosses, profile.cross_accuracy, rng, 0.16)

    # -- Dribbling -----------------------------------------------------------
    dribbles = _count(profile.dribbles * ab.dribbling, minutes, rng, 0.24)
    successful_dribbles = _subset(
        dribbles, profile.dribble_success * (0.92 + 0.08 * ab.dribbling), rng, 0.10
    )

    # -- Defending -----------------------------------------------------------
    tackles = _count(profile.tackles * ab.defending, minutes, rng)
    successful_tackles = _subset(
        tackles, profile.tackle_success * (0.94 + 0.06 * ab.defending), rng, 0.08
    )
    interceptions = _count(profile.interceptions * ab.defending, minutes, rng)
    blocks = _count(profile.blocks * ab.defending, minutes, rng, 0.26)
    clearances = _count(profile.clearances * ab.defending, minutes, rng, 0.22)

    # -- Duels ---------------------------------------------------------------
    duels = _count(profile.duels, minutes, rng, 0.12)
    duels_won = _subset(duels, profile.duel_win_rate * (0.90 + 0.10 * ab.duelling), rng, 0.06)
    aerial_duels = _subset(duels, profile.aerial_share, rng, 0.12)
    aerial_duels_won = _subset(
        aerial_duels, profile.aerial_win_rate * (0.88 + 0.12 * ab.aerial), rng, 0.08
    )

    # -- Shooting ------------------------------------------------------------
    shots = _count(profile.shots * (0.85 + 0.15 * ab.finishing), minutes, rng, 0.24)
    shots_on_target = _subset(
        shots, profile.shot_accuracy * (0.92 + 0.08 * ab.finishing), rng, 0.12
    )

    penalties_taken = 0
    if profile.penalty_taker > 0 and rng.random() < profile.penalty_taker:
        penalties_taken = min(shots, rng.randint(1, 7))

    non_penalty_shots = max(0, shots - penalties_taken)
    npxg = round(profile.npxg * (minutes / 90.0) * _jitter(rng, 0.22), 3)
    # Expected goals cannot exceed the chances actually taken.
    npxg = round(min(npxg, non_penalty_shots * 0.55), 3)
    xg = round(npxg + penalties_taken * 0.79, 3)

    # Finishing varies around expectation rather than tracking it exactly -
    # that variance is precisely what makes finishing metrics noisy, which the
    # methodology warns about.
    non_penalty_goals = max(0, round(npxg * _jitter(rng, 0.34)))
    non_penalty_goals = min(non_penalty_goals, shots_on_target)
    penalties_scored = _subset(penalties_taken, 0.78, rng, 0.10)
    goals = min(shots_on_target, non_penalty_goals + penalties_scored)
    # Clamping goals may have eaten into the non-penalty portion.
    non_penalty_goals = min(non_penalty_goals, goals)

    xa = round(profile.xa * (minutes / 90.0) * ab.creation * _jitter(rng, 0.26), 3)
    assists = max(0, round(xa * _jitter(rng, 0.38)))
    assists = min(assists, key_passes) if key_passes else min(assists, 1)

    # -- Discipline and losses ----------------------------------------------
    # Inverse metrics: a more able player loses the ball and is beaten less.
    fouls_committed = _count(profile.fouls_committed / max(0.5, ab.defending), minutes, rng, 0.24)
    fouls_drawn = _count(profile.fouls_drawn * ab.dribbling, minutes, rng, 0.26)
    dispossessed = _count(profile.dispossessed / max(0.5, ab.retention), minutes, rng, 0.24)
    dribbled_past = _count(profile.dribbled_past / max(0.5, ab.defending), minutes, rng, 0.26)

    # -- Goalkeeping ---------------------------------------------------------
    saves = inside_box_saves = goals_conceded = clean_sheets = penalties_saved = None
    if group is PositionGroup.GK:
        saves = _count(profile.saves, minutes, rng, 0.20)
        inside_box_saves = _subset(saves, profile.inside_box_share, rng, 0.10)
        # A better keeper concedes less; shot volume is a team property.
        goals_conceded = _count(profile.goals_conceded / max(0.5, ab.defending), minutes, rng, 0.22)
        clean_sheets = min(
            appearances, max(0, round(appearances * profile.clean_sheet_rate * _jitter(rng, 0.35)))
        )
        penalties_saved = 1 if rng.random() < 0.18 else 0

    return PlayerSeasonStats(
        source_player_id=player_id,
        season_id=SEASON_ID,
        competition_id=competition.competition_id,
        club_id=club.club_id,
        appearances=appearances,
        starts=starts,
        minutes=minutes,
        goals=goals,
        non_penalty_goals=non_penalty_goals,
        assists=assists,
        xg=xg,
        npxg=npxg,
        xa=xa,
        shots=shots,
        shots_on_target=shots_on_target,
        penalties_taken=penalties_taken,
        passes=passes,
        passes_completed=passes_completed,
        progressive_passes=progressive_passes,
        key_passes=key_passes,
        crosses=crosses,
        accurate_crosses=accurate_crosses,
        dribbles=dribbles,
        successful_dribbles=successful_dribbles,
        tackles=tackles,
        successful_tackles=successful_tackles,
        interceptions=interceptions,
        blocks=blocks,
        clearances=clearances,
        duels=duels,
        duels_won=duels_won,
        aerial_duels=aerial_duels,
        aerial_duels_won=aerial_duels_won,
        fouls_committed=fouls_committed,
        fouls_drawn=fouls_drawn,
        dispossessed=dispossessed,
        dribbled_past=dribbled_past,
        saves=saves,
        inside_box_saves=inside_box_saves,
        goals_conceded=goals_conceded,
        clean_sheets=clean_sheets,
        penalties_saved=penalties_saved,
    )


@lru_cache(maxsize=4)
def build_dataset(
    seed: int = 20260827, competitions: int = 4, clubs_per_competition: int = 18
) -> MockDataset:
    """Generate (and cache) a demo universe.

    Deterministic for a given seed, and cached because regenerating ~1,700
    players on every request would be wasteful for data that never changes.
    """
    return _generate_dataset(seed, competitions, clubs_per_competition)


class MockPerformanceProvider(PerformanceDataProvider):
    """Provider backed by fabricated data. Performs no network access.

    `unavailable_metrics` deliberately withholds metrics so the rest of the
    application can be tested against a provider that cannot supply everything
    - the situation a real provider is likely to present. Withheld metrics are
    absent from `info.available_metrics` AND set to None on every record, so a
    caller cannot accidentally read a value it was told did not exist.
    """

    def __init__(
        self,
        *,
        seed: int = 20260827,
        competitions: int = 4,
        clubs_per_competition: int = 18,
        unavailable_metrics: frozenset[CanonicalMetric] | None = None,
    ) -> None:
        self._dataset = build_dataset(seed, competitions, clubs_per_competition)
        self._unavailable = unavailable_metrics or frozenset()
        self._stats_index = self._dataset.stats_by_player()

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(
            name="MockPerformanceProvider",
            is_mock=True,
            # Nothing here has been validated against a real source, because
            # there is no real source. This must never read True.
            validated=False,
            available_metrics=frozenset(CanonicalMetric) - self._unavailable,
            notes=DEMO_DATA_WARNING,
        )

    def _redact(self, stats: PlayerSeasonStats) -> PlayerSeasonStats:
        """Blank any metric this provider declares it cannot supply."""
        if not self._unavailable:
            return stats
        return stats.model_copy(update={m.value: None for m in self._unavailable})

    def get_competitions(self) -> list[Competition]:
        return list(self._dataset.competitions)

    def get_seasons(self, competition_id: str) -> list[Season]:
        self._require_competition(competition_id)
        return list(self._dataset.seasons)

    def get_clubs(self, competition_id: str, season_id: str) -> list[Club]:
        self._require_competition(competition_id)
        self._require_season(season_id)
        return [c for c in self._dataset.clubs if c.competition_id == competition_id]

    def get_players(self, competition_id: str, season_id: str) -> list[PlayerIdentity]:
        self._require_competition(competition_id)
        self._require_season(season_id)
        return [p for p in self._dataset.players if p.competition_id == competition_id]

    def get_player_stats(self, source_player_id: str, season_id: str) -> PlayerSeasonStats | None:
        record = self._stats_index.get((source_player_id, season_id))
        return None if record is None else self._redact(record)

    def get_competition_stats(self, competition_id: str, season_id: str) -> list[PlayerSeasonStats]:
        self._require_competition(competition_id)
        self._require_season(season_id)
        return [
            self._redact(s)
            for s in self._dataset.stats
            if s.competition_id == competition_id and s.season_id == season_id
        ]

    def _require_competition(self, competition_id: str) -> None:
        if not any(c.competition_id == competition_id for c in self._dataset.competitions):
            raise UnknownEntityError(f"Unknown competition: {competition_id}")

    def _require_season(self, season_id: str) -> None:
        if not any(s.season_id == season_id for s in self._dataset.seasons):
            raise UnknownEntityError(f"Unknown season: {season_id}")
