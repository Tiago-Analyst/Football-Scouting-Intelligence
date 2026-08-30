"""When a contract runs out, and what "expiring soon" means.

This arithmetic existed in four places, written out longhand each time, and
carried the same defect in all four: it asked whether an expiry was *at most*
N months away and never whether it was in the future at all.

A contract that ended in June 2024 is -31 months away, and -31 is comfortably
under any threshold, so 900 loaded players with lapsed contracts passed a
filter for "expiring within 18 months" - and were offered as market
opportunities with "Contract expires Jun 2024" printed underneath as a reason
to sign them.
"""

from __future__ import annotations

from datetime import date


def reference_date() -> date:
    """The date every age and contract window is measured from.

    Today, not a fixed point. This was pinned to 1 January 2027 so the demo
    universe produced stable ages, and against real data it showed 1,541 of
    5,456 players - 28% - at an age they had not reached yet.

    A test that needs a stable answer should pass its own date rather than
    freeze everyone's birthday.
    """
    return date.today()


def months_until(expires: date, *, today: date | None = None) -> int:
    """Whole months from `today` to `expires`, negative once it has passed.

    Calendar months rather than days: contracts run to the end of a month, and
    "eighteen months left" is how the question is asked.
    """
    reference = today or reference_date()
    return (expires.year - reference.year) * 12 + (expires.month - reference.month)


def expires_within(expires: date | None, months: int, *, today: date | None = None) -> bool:
    """Whether a contract runs out inside the next `months`.

    An expiry already in the past is **not** within the window. A player whose
    recorded contract lapsed is not a player with a contract about to lapse:
    either they re-signed and the dataset has not caught up, or they left the
    club entirely. Either way the record says nothing useful about their
    current situation, and presenting it as a signing opportunity claims
    knowledge nobody has.

    A player with no recorded expiry does not pass either - the filter asks a
    question their data cannot answer.
    """
    if expires is None:
        return False
    reference = today or reference_date()
    if expires < reference:
        # Compared as dates, not as months. Month granularity is right for "how
        # far ahead", and wrong for "has it passed": a contract that ended on
        # the 15th is nought months away on the 30th, and would slip back in.
        return False
    return months_until(expires, today=reference) <= months


def has_lapsed(expires: date | None, *, today: date | None = None) -> bool:
    """Whether the recorded contract ran out before now.

    Worth naming rather than folding into `expires_within`: a lapsed record is
    a fact about the dataset's freshness, not about the player.
    """
    return expires is not None and expires < (today or reference_date())
