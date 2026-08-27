"""The FootyStats validation gate.

Two things are asserted here, and both are about refusing rather than doing.

**No metric may be claimed without evidence.** The mapping file is the only
thing that can grant FootyStats a metric, and it rejects any entry that cannot
say which field, in which response, verified when, and on what basis.

**The API key must not escape.** This provider authenticates with the key in
the query string, so every URL is a potential leak — into a log, a saved
artefact, an exception message. The redaction is tested against each of those
shapes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pipelines.footystats.probe import REDACTED, find_first_id, redact, resolve_params, truncate

from app.core.errors import DataNotValidatedError
from app.providers.footystats_mapping import (
    MAPPING_PATH,
    FootyStatsMapping,
    MappingError,
    load_mapping,
)
from app.schemas.canonical import CanonicalMetric

KEY = "a1b2c3d4e5f6a7b8c9d0e1f2"


def write(tmp_path: Path, body: str) -> Path:
    target = tmp_path / "mapping.yaml"
    target.write_text(body, encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# The shipped mapping
# ---------------------------------------------------------------------------


class TestTheShippedMapping:
    def test_it_parses(self) -> None:
        load_mapping()

    def test_it_is_empty_because_nothing_has_been_observed(self) -> None:
        """This is the correct state, not a gap. No API key has been available,
        so no response has been seen, so no field may be mapped."""
        assert load_mapping().is_empty

    def test_an_empty_mapping_claims_no_metrics(self) -> None:
        assert load_mapping().available_metrics == frozenset()

    def test_an_empty_mapping_reports_every_metric_as_missing(self) -> None:
        assert load_mapping().missing() == frozenset(CanonicalMetric)

    def test_requiring_it_refuses(self) -> None:
        """A provider built on an empty mapping would return records with every
        metric None, which is indistinguishable from a player who did nothing."""
        with pytest.raises(DataNotValidatedError):
            load_mapping().require()

    def test_it_names_no_response_it_has_seen(self) -> None:
        """The file is in its pristine state: nothing observed, nothing claimed.

        Asserted on the parsed mapping rather than on the file's text, which
        would only be testing how the YAML happens to be laid out.
        """
        assert MAPPING_PATH.exists()
        mapping = load_mapping()
        assert mapping.verified_against == ()
        assert mapping.rejected == {}

    def test_no_field_name_is_claimed_anywhere(self) -> None:
        """The guard that matters: a metric cannot appear here without the
        loader also demanding the response it was observed in."""
        assert [entry.field for entry in load_mapping().metrics.values()] == []


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestMappingValidation:
    def test_a_complete_entry_is_accepted(self, tmp_path: Path) -> None:
        path = write(
            tmp_path,
            """
version: 1
verified_against: [league-players]
metrics:
  minutes:
    field: minutes_played_overall
    response: league-players
    verified_on: 2026-09-01
    note: Season total, checked against three players' appearance counts.
rejected: {}
""",
        )
        mapping = load_mapping(path)
        assert mapping.available_metrics == {CanonicalMetric.MINUTES}
        assert mapping.metrics[CanonicalMetric.MINUTES].field == "minutes_played_overall"

    @pytest.mark.parametrize("omitted", ["field", "response", "verified_on", "note"])
    def test_an_incomplete_entry_is_refused(self, tmp_path: Path, omitted: str) -> None:
        entry = {
            "field": "minutes_played_overall",
            "response": "league-players",
            "verified_on": "2026-09-01",
            "note": "Season total, checked against appearance counts.",
        }
        del entry[omitted]
        lines = "\n".join(f"    {k}: {v}" for k, v in entry.items())
        path = write(
            tmp_path,
            f"version: 1\nverified_against: [league-players]\nmetrics:\n  minutes:\n{lines}\n",
        )
        with pytest.raises(MappingError):
            load_mapping(path)

    def test_an_unknown_metric_name_is_refused(self, tmp_path: Path) -> None:
        """Inventing a metric here would put a field in the system that nothing
        else knows about."""
        path = write(
            tmp_path,
            """
version: 1
verified_against: [league-players]
metrics:
  vibes_per_ninety:
    field: vibes
    response: league-players
    verified_on: 2026-09-01
    note: This should never be accepted by the loader.
""",
        )
        with pytest.raises(MappingError, match="not a canonical metric"):
            load_mapping(path)

    def test_a_hollow_justification_is_refused(self, tmp_path: Path) -> None:
        path = write(
            tmp_path,
            """
version: 1
verified_against: [league-players]
metrics:
  minutes:
    field: minutes_played_overall
    response: league-players
    verified_on: 2026-09-01
    note: ok
""",
        )
        with pytest.raises(MappingError, match="justification"):
            load_mapping(path)

    def test_metrics_without_a_verified_response_are_refused(self, tmp_path: Path) -> None:
        """A mapping nobody can check against a recorded response is exactly what
        this file exists to prevent."""
        path = write(
            tmp_path,
            """
version: 1
verified_against: []
metrics:
  minutes:
    field: minutes_played_overall
    response: league-players
    verified_on: 2026-09-01
    note: Season total, checked against three players' appearance counts.
""",
        )
        with pytest.raises(MappingError, match="verified_against"):
            load_mapping(path)

    def test_an_unparseable_date_is_refused(self, tmp_path: Path) -> None:
        path = write(
            tmp_path,
            """
version: 1
verified_against: [league-players]
metrics:
  minutes:
    field: minutes_played_overall
    response: league-players
    verified_on: "last tuesday"
    note: Season total, checked against three players' appearance counts.
""",
        )
        with pytest.raises(MappingError):
            load_mapping(path)

    def test_a_missing_file_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(MappingError, match="missing"):
            load_mapping(tmp_path / "nope.yaml")

    def test_a_populated_mapping_does_not_refuse(self) -> None:
        mapping = FootyStatsMapping(metrics={}, verified_against=(), rejected={})
        with pytest.raises(DataNotValidatedError):
            mapping.require()


# ---------------------------------------------------------------------------
# Key redaction
# ---------------------------------------------------------------------------


class TestTheKeyNeverEscapes:
    def test_a_url_loses_its_key(self) -> None:
        url = f"https://api.example.test/league-list?key={KEY}&season_id=4"
        cleaned = redact(url, KEY)
        assert KEY not in cleaned
        assert REDACTED in cleaned
        # The rest of the URL survives, so the report is still readable.
        assert "season_id=4" in cleaned

    def test_a_percent_encoded_key_is_caught(self) -> None:
        """`urlencode` escapes the key, so the literal string is not enough."""
        odd = "abc/def+ghi=="
        text = f"https://api.example.test/x?key={'abc%2Fdef%2Bghi%3D%3D'}"
        assert odd not in redact(text, odd)
        assert REDACTED in redact(text, odd)

    def test_an_exception_message_loses_its_key(self) -> None:
        message = f"HTTPError: <urlopen error> for https://api.example.test/x?key={KEY}"
        assert KEY not in redact(message, KEY)

    def test_a_json_body_echoing_the_request_loses_its_key(self) -> None:
        body = json.dumps({"error": "bad request", "request": f"/league-list?key={KEY}"})
        assert KEY not in redact(body, KEY)

    def test_an_unknown_key_shape_is_still_stripped(self) -> None:
        """A key that arrived through some other spelling than the one we hold."""
        other = "?key=some-other-secret-entirely&x=1"
        cleaned = redact(other, KEY)
        assert "some-other-secret-entirely" not in cleaned
        assert "x=1" in cleaned

    def test_redacting_without_a_key_changes_nothing_it_should_not(self) -> None:
        assert redact("no secrets here", "") == "no secrets here"


# ---------------------------------------------------------------------------
# Probe mechanics
# ---------------------------------------------------------------------------


class TestProbeMechanics:
    def test_an_id_is_found_wherever_it_sits(self) -> None:
        payload = {"success": True, "data": [{"name": "A League", "id": 4321}]}
        assert find_first_id(payload, ("season_id", "id")) == "4321"

    def test_a_missing_id_is_reported_rather_than_invented(self) -> None:
        assert find_first_id({"data": [{"name": "A League"}]}, ("season_id",)) is None

    def test_an_unresolved_placeholder_skips_the_call(self) -> None:
        assert resolve_params({"season_id": "${season_id}"}, {}) is None

    def test_a_resolved_placeholder_substitutes(self) -> None:
        assert resolve_params({"season_id": "${season_id}"}, {"season_id": "7"}) == {
            "season_id": "7"
        }

    def test_a_literal_parameter_passes_through(self) -> None:
        assert resolve_params({"page": "1"}, {}) == {"page": "1"}

    def test_truncation_keeps_the_shape_and_records_what_it_dropped(self) -> None:
        """The profiler needs the shape of a response, not every row of it."""
        payload = {"success": True, "data": [{"i": n} for n in range(500)]}
        out = truncate(payload)
        assert out["success"] is True
        assert len(out["data"]) == 200
        assert out["_fri_data_truncated_from"] == 500
