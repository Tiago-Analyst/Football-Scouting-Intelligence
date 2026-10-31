"""Documentation that describes a state the project has left.

Prose rots silently. There is no type error for a methodology page saying the
provider is not connected thirty lines above a table of the fields it supplies,
and both statements were true once, which is exactly why nobody notices.

These are the specific claims that were found stale and the specific decisions
that must not be quietly re-derived. They are cheap, they run in CI, and they
fail the moment a document starts describing a different project.
"""

from __future__ import annotations

import pathlib
import re

import pytest

DOCS = pathlib.Path(__file__).resolve().parents[2] / "docs"
README = pathlib.Path(__file__).resolve().parents[2] / "README.md"

#: Documents that describe the system as it is. `architecture.md` is excluded
#: deliberately: it is a chronological record whose whole purpose is to say
#: what was true when each decision was taken, and it declares itself as such.
CURRENT_DOCS = (
    "methodology.md",
    "footystats_provider_status.md",
    "config_availability.md",
    "data_publication_lifecycle.md",
)


def read(name: str) -> str:
    path = DOCS / name
    if not path.exists():
        pytest.skip(f"{name} has not been generated here")
    return path.read_text(encoding="utf-8")


class TestNothingClaimsFootyStatsIsUnconnected:
    @pytest.mark.parametrize("name", CURRENT_DOCS)
    def test_the_current_documents_do_not_say_it(self, name: str) -> None:
        """A real key has been used and real responses validated.

        `methodology.md` carried "FootyStats API — Not connected. No key, no
        field verified." in its data-sources table, and "No FootyStats field is
        mapped." beneath it, while the generated provider status listed 36
        mapped metrics.
        """
        text = read(name).lower()
        for claim in (
            "not connected",
            "no key, no field",
            "no footystats field is mapped",
            "until an api key exists",
            "no footystats metric is currently available",
        ):
            assert claim not in text, f"{name} still says {claim!r}"

    def test_the_readme_does_not_say_it(self) -> None:
        text = README.read_text(encoding="utf-8").lower()
        for claim in ("not connected", "awaits a footystats key", "no real key"):
            assert claim not in text, claim

    def test_the_methodology_names_the_provider_as_live(self) -> None:
        text = read("methodology.md")
        assert "Connected and live" in text


class TestTheMinutesDecisionIsRecordedWhereItWillBeRead:
    def test_the_specification_carries_the_override(self) -> None:
        """The rule that already came back once.

        The 450-minute floor was removed and then re-derived by accident,
        because the specification still asked for it and nothing said
        otherwise. A future reader - or agent - meets the override first.
        """
        text = (DOCS / "specification.md").read_text(encoding="utf-8")
        assert "PRODUCT DECISION OVERRIDE" in text

        # Near the top, not buried. The spec is long.
        position = text.index("PRODUCT DECISION OVERRIDE")
        assert position < 2000, "the override is too far down to be read first"

    def test_it_states_the_four_bands(self) -> None:
        text = (DOCS / "specification.md").read_text(encoding="utf-8")
        override = text[: text.index("You are building")]
        for band in ("Very Low Sample", "Low Sample", "Developing Sample", "Established Sample"):
            assert band in override, band

    def test_it_says_minutes_do_not_determine_eligibility(self) -> None:
        text = (DOCS / "specification.md").read_text(encoding="utf-8")
        override = text[: text.index("You are building")]
        assert "no longer apply" in override
        assert "informational sample-size labels" in override

    def test_the_superseded_sections_are_marked_in_place(self) -> None:
        """Someone reading section 7 directly must see it too."""
        text = (DOCS / "specification.md").read_text(encoding="utf-8")
        section = text[text.index("# 7. MINIMUM SAMPLE RULES") :][:600]
        assert "SUPERSEDED" in section

    def test_the_methodology_agrees(self) -> None:
        # Whitespace-normalised: these sentences are line-wrapped in the file,
        # and a test that breaks on re-wrapping is a test nobody trusts.
        text = " ".join(read("methodology.md").split())
        assert "Minutes do not determine eligibility" in text
        assert "All players with valid statistical data are included" in text


class TestTheDenominatorWordingIsNotOversimplified:
    """ "Every per-90 uses recorded minutes" was true of the detailed feed and
    false of goals, assists and goals conceded."""

    @pytest.mark.parametrize("name", CURRENT_DOCS)
    def test_no_document_claims_one_denominator_for_everything(self, name: str) -> None:
        text = read(name).lower()
        for claim in (
            "every per-90 metric uses recorded minutes",
            "every per-90 in this product therefore divides by the recorded",
            "rates divide by `recorded_minutes`, not `minutes`",
        ):
            assert claim not in text, f"{name}: {claim!r}"

    def test_the_methodology_explains_the_families(self) -> None:
        text = read("methodology.md")
        assert "Which minutes a per-90 divides by" in text
        assert "footystats_denominator_validation" in text

    def test_the_source_modules_do_not_claim_it_either(self) -> None:
        root = pathlib.Path(__file__).resolve().parents[1] / "app"
        offenders = []
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8").lower()
            if "every per-90 in this product therefore divides by the recorded" in text:
                offenders.append(path.name)
        assert offenders == [], offenders


class TestTheLifecycleIsDocumented:
    def test_it_exists_and_answers_the_question(self) -> None:
        text = read("data_publication_lifecycle.md")
        assert "visible" in text.lower()
        for stage in ("PROMOTE", "IDENTITY RESOLUTION", "ANALYTICS RELOAD"):
            assert stage in text, stage

    def test_it_documents_the_atomic_promotion(self) -> None:
        """This asserted the opposite until the staging schema was built.

        It required the document to admit that atomic promotion was not done.
        It is now, so the assertion is inverted rather than deleted: what a
        reader needs from this page is the truth about when data becomes
        visible, and that truth changed.
        """
        text = read("data_publication_lifecycle.md")
        lowered = text.lower()
        assert "atomic promotion" in lowered
        assert "analytics_staging" in text
        assert "not done, deliberately" not in lowered, (
            "the document still describes atomic promotion as future work"
        )

    def test_it_names_the_cost_as_well_as_the_benefit(self) -> None:
        """Two schemas have to stay identical, and a page that only described
        the guarantee would be selling it."""
        text = read("data_publication_lifecycle.md")
        assert "The cost of this design" in text
        assert "structurally identical" in text

    def test_it_documents_the_rollback(self) -> None:
        text = read("data_publication_lifecycle.md")
        assert "--rollback" in text


class TestTheHistoryCleanupIsRecorded:
    def test_it_documents_what_was_done_rather_than_proposing_it(self) -> None:
        text = (DOCS / "git_history_cleanup.md").read_text(encoding="utf-8")
        assert "already been done" in text.lower()
        assert "git filter-repo" in text
        # The consequence people forget.
        assert "not erasure" in text.lower()


class TestGeneratedDocumentsSayTheyAreGenerated:
    @pytest.mark.parametrize(
        "name",
        ("footystats_provider_status.md", "config_availability.md"),
    )
    def test_they_warn_against_hand_editing(self, name: str) -> None:
        head = read(name)[:800].lower()
        assert "generated" in head
        assert re.search(r"do not edit", head), name


class TestTheReadmeCarriesNoFigureThatAPromotionChanges:
    """A README is not re-read when a generation is published.

    It said 8,701 player-seasons across 44 competitions, which was corrected to
    5,383 across 43 on 29 October. On 31 October a promotion made that wrong
    again - 14,677 - so the corrected figure was accurate for two days and
    misleading by nearly a factor of three thereafter.

    The problem is not the arithmetic. It is that a generation publishes as one
    universe, so every such figure moves at once, at a moment nobody is editing
    documentation. `GET /health` reports what is being served and carries the
    timestamp it was built at; `docs/current_state.md` holds a dated snapshot
    and says what makes it wrong. Neither needs a hand.

    Deliberately narrow: two shapes, in one file. It does not object to numbers
    in the README - `96 CHECK constraints` and `~28,460 requests` describe the
    system's structure and cost, and a promotion does not touch either.
    """

    #: A count of data served, in the two shapes a promotion moves. The comma
    #: group is optional so `43 competitions` is caught as well as `5,383`.
    DRIFTING = re.compile(r"\d[\d,]*\s+(player-seasons?|competitions?)", re.IGNORECASE)

    def test_no_player_season_or_competition_count(self) -> None:
        # The whole match, not the group, so a failure names the figure as the
        # README writes it rather than just the noun after it.
        found = [m.group(0) for m in self.DRIFTING.finditer(README.read_text(encoding="utf-8"))]
        assert found == [], (
            f"README.md states a count a promotion will change: {found}. "
            "Point at GET /health or docs/current_state.md instead."
        )
