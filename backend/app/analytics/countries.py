"""The one thing two provider vocabularies can be compared by.

WHY THIS EXISTS

A player's performance comes from the performance provider and their current
club from the market provider, and the two name competitions in vocabularies
that do not meet: the same league is `footystats:17097`, "Netherlands
Eredivisie", and `transfermarkt:NL1`, "eredivisie". Nothing maps between them
and this product has never needed a mapping - until a profile had to say
whether the club it shows and the competition it shows are in the same place.

Both carry a country, and the countries very nearly agree: of the thirty-odd
each side knows, all but three are the same string. A country is a real answer
to a smaller question than "the same league", and the smaller question is the
one worth answering, because it is the one a reader can see for themselves.

WHAT IT CANNOT DO, STATED RATHER THAN DISCOVERED

It cannot tell a first division from a second, so a player who dropped a
division at home looks like no change at all. It cannot tell a domestic league
from a cup in the same country. It knows nothing about continental
competitions, whose "country" is a continent on one side and absent on the
other.

Every one of those is a MISSED difference, never an invented one, which is the
direction this should fail in: a note that appears wrongly teaches a reader to
ignore notes, and a note that fails to appear leaves the page exactly as
honest as it was before there were notes.
"""

from __future__ import annotations

#: The three countries the two providers spell differently.
#:
#: Written out rather than solved with a country library, because there are
#: three of them and a dependency that normalises two hundred would still have
#: to be checked against these. Both spellings map to one key, so neither
#: provider's is privileged as "the right one".
#:
#: A fourth disagreement would arrive silently as a wrongly-shown note, so the
#: data-quality report counts the market source's countries that find no
#: counterpart in the performance source's. This table is where the answer
#: goes once that count moves.
_ALIASES: dict[str, str] = {
    "korea, south": "south korea",
    "south korea": "south korea",
    "united states": "usa",
    "usa": "usa",
    "turkiye": "turkey",
    "türkiye": "turkey",
    "turkey": "turkey",
}


#: Values in the country column that are not countries.
#:
#: The performance provider files its continental competitions under the
#: continent - "Europe UEFA Champions League", country "Europe" - and the
#: market provider leaves the same competitions' country null. A continent
#: compared against a country differs every time, so without this a player at
#: a Russian club who played in the Europa League read as having moved abroad.
#: That was six of the first twelve notes this produced.
#:
#: Treated as UNKNOWN rather than as a country, because a continental
#: competition genuinely has no one country and the comparison is unavailable
#: rather than negative.
_NOT_A_COUNTRY: frozenset[str] = frozenset(
    {"europe", "south america", "north america", "asia", "africa", "oceania", "world"}
)


def normalise_country(name: str | None) -> str | None:
    """A country as a comparison key, or None when there is nothing to compare.

    None for absent and for blank alike: a competition with no country - the
    continental ones, on the market side - supports no comparison, and saying
    so is different from saying the countries differ.
    """
    if name is None:
        return None
    folded = " ".join(name.split()).casefold()
    if not folded:
        return None
    resolved = _ALIASES.get(folded, folded)
    if resolved in _NOT_A_COUNTRY:
        return None
    return resolved


def in_the_same_country(left: str | None, right: str | None) -> bool | None:
    """Whether two competitions are in the same country.

    `None` means UNKNOWN, and callers must not read it as `False`. One of the
    two did not say where it is, and "we cannot tell" is the answer; treating
    it as a difference is how a note ends up on a profile that has nothing
    unusual about it.
    """
    a, b = normalise_country(left), normalise_country(right)
    if a is None or b is None:
        return None
    return a == b
