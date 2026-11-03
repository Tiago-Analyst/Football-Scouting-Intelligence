"""Whether two provider records name the same club.

WHY THIS LIVES IN `app` AND NOT IN THE PIPELINE THAT WROTE IT

It was written for identity resolution, which matches a performance record
against a market record and needs to know whether "Man Utd FC" and
"Manchester United" are one club. The API needs the same question answered
for a different reason: a profile shows the club that played the season
beside the club the player is at now, and on the served data 67% of those
pairs are ONE club under two providers' spellings -

    Once Caldas SA            / Once Caldas
    Gangwon FC                / Gangwon Football Club
    CD Popular Junior FC SA   / Junior FC

Printed as two labelled rows, those read as a transfer that did not happen,
which is the same class of defect as the one the two contexts were split to
remove.

`pipelines` imports from `app` and never the other way round, so the shared
answer belongs here. `pipelines.identity_resolution.matcher` re-exports every
name below, and its tests - which pin Manchester United against Manchester
City, Sporting CP against Sporting Braga, and Real Madrid against Real
Sociedad - go on importing them from there unchanged.
"""

from __future__ import annotations

from app.schemas.market import normalize_name

#: Words that carry no club identity at all: corporate and structural forms.
#:
#: These are dropped before comparison. Note what is *not* here - `united`,
#: `city`, `real`, `sporting`. Those are common, but they are exactly what
#: separates Manchester United from Manchester City, and dropping them made the
#: two identical.
GENERIC_CLUB_TOKENS = frozenset(
    {
        "fc",
        "cf",
        "sc",
        "ac",
        "afc",
        "cd",
        "ud",
        "sd",
        "cs",
        "as",
        "us",
        "ss",
        "sv",
        "tsv",
        "vfb",
        "vfl",
        "fsv",
        "bsc",
        "fk",
        "sk",
        "nk",
        "hk",
        "ik",
        "kv",
        "rc",
        "rcd",
        "sl",
        "cp",
        "ca",
        "aa",
        "ec",
        "se",
        "club",
        "clube",
        "futbol",
        "futebol",
        "football",
        "fussball",
        "calcio",
        "association",
        "associacao",
        "asociacion",
        # Joining words survive normalisation and mean nothing
        "de",
        "da",
        "do",
        "del",
        "della",
        "di",
        "du",
        "des",
        "der",
        "den",
        "el",
        "la",
        "le",
        "les",
        "los",
        "and",
        "the",
        "of",
        "e",
        "y",
    }
)


#: Words that identify a football culture rather than a club.
#:
#: Kept as tokens - they do distinguish clubs from each other - but not trusted
#: on their own. Half of Portugal is `sporting`, half of Spain is `real`, and
#: England is full of `united` and `city`, so a single one of these shared
#: between two names says almost nothing.
CULTURE_GENERIC_TOKENS = frozenset(
    {
        "sporting",
        "sport",
        "sports",
        "sportif",
        "sportiva",
        "real",
        "royal",
        "athletic",
        "atletico",
        "athletico",
        "atletic",
        "deportivo",
        "deportiva",
        "racing",
        "olympique",
        "olympiakos",
        "borussia",
        "dynamo",
        "dinamo",
        "spartak",
        "lokomotiv",
        "united",
        "city",
        "town",
        "county",
        "rovers",
        "wanderers",
        "albion",
        "union",
        "unione",
        "rapid",
        "slavia",
        "sparta",
    }
)

#: Short forms that are the same club written differently. Expanded before
#: comparison, so `Man Utd FC` and `Manchester United` reach the same tokens
#: rather than being read as two clubs sharing nothing.
CLUB_TOKEN_ALIASES = {
    "man": "manchester",
    "utd": "united",
    "wolves": "wolverhampton",
    "spurs": "tottenham",
    "psg": "paris",
    "inter": "internazionale",
    "gladbach": "monchengladbach",
    "st": "saint",
    "ste": "saint",
    "atl": "atletico",
    "dep": "deportivo",
}


def club_tokens(name: str) -> frozenset[str]:
    """The parts of a club name that could identify a club.

    Aliases expanded, structural words dropped, anything under three characters
    ignored. Culture-generic words stay - they do distinguish clubs - but
    `_same_club` will not trust one on its own.
    """
    normalised = normalize_name(name)
    expanded = [CLUB_TOKEN_ALIASES.get(token, token) for token in normalised.split()]
    return frozenset(t for t in expanded if t not in GENERIC_CLUB_TOKENS and len(t) > 2)


def same_club(left: str | None, right: str | None) -> bool | None:
    """Whether both sides agree on the club.

    Three answers, and the third is the one that was missing. `None` means the
    evidence does not settle it, and a missing club must not read as a
    disagreement or every player without club data is penalised for it.

    WHAT WAS WRONG
    --------------

    This returned true on *any* shared token. The comment above it said "a
    shared distinctive token"; the code checked nothing of the sort:

        Manchester United / Manchester City   shared "manchester"  -> same club
        Sporting CP       / Sporting Braga    shared "sporting"    -> same club
        Real Madrid       / Real Sociedad     shared "real"        -> same club

    Each then contributed to a confidence score, so a coincidence of city, or
    of a word half a league shares, counted as evidence that two records
    described one person.

    THE RULES NOW, AND WHAT EACH IS FOR
    -----------------------------------

    Identical distinctive tokens agree. `Manchester United` and `Man Utd FC`
    reach the same set once aliases are expanded.

    One set properly containing the other agrees, provided the smaller side
    carries something more than a culture-generic word. `SL Benfica` inside
    `Sport Lisboa e Benfica` is the same club written shorter. `Sporting CP`
    inside `Sporting Braga` is not, and the difference is that `benfica`
    identifies a club while `sporting` identifies a country's habits.

    Overlapping without containment settles nothing. Manchester United and
    Manchester City share the city and differ on everything separating them;
    answering `None` lets name, date of birth and nationality decide rather
    than putting a thumb on the scale.

    Disjoint distinctive tokens are a real disagreement, and say so.
    """
    if not left or not right:
        return None

    a, b = normalize_name(left), normalize_name(right)
    if not a or not b:
        return None
    if a == b:
        return True

    left_tokens, right_tokens = club_tokens(a), club_tokens(b)
    if not left_tokens or not right_tokens:
        # One side is nothing but structural words. No distinctive part to
        # compare, so nothing is claimed either way.
        return None

    if left_tokens == right_tokens:
        return True

    if not left_tokens & right_tokens:
        return False

    smaller, larger = sorted((left_tokens, right_tokens), key=len)
    if smaller < larger and smaller - CULTURE_GENERIC_TOKENS:
        return True

    return None
