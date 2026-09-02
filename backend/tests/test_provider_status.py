"""The generated provider status must agree with the mapping it comes from.

This exists because the repository once carried a README announcing "35 of 39
metrics mapped" three paragraphs above "it is empty today, and the provider
therefore offers nothing". Both were written truthfully, months apart. Only the
first was revisited.

Hand-maintained provider documentation drifts silently, and the drift is
expensive here: a reader deciding whether to trust a number needs to know what
established it. So the document is generated, and this test is what stops the
generated file and its source diverging.
"""

from __future__ import annotations

import yaml
from pipelines.footystats.status import (
    ARITHMETIC_MARKER,
    MAPPING,
    OUTPUT,
    build_rows,
    main,
    render,
)


def mapping() -> dict:
    return yaml.safe_load(MAPPING.read_text(encoding="utf-8"))


class TestTheDocumentTracksTheMapping:
    def test_the_written_file_is_current(self) -> None:
        """`--check` is the same comparison CI makes."""
        assert main(["--check"]) == 0, (
            "docs/footystats_provider_status.md is stale. "
            "Run: python -m pipelines.footystats.status"
        )

    def test_every_mapped_metric_appears(self) -> None:
        data = mapping()
        rendered = OUTPUT.read_text(encoding="utf-8")
        for metric in data["metrics"]:
            assert f"`{metric}`" in rendered, metric
        for metric in data.get("derived") or {}:
            assert f"`{metric}`" in rendered, metric

    def test_what_the_provider_lacks_is_stated_too(self) -> None:
        """An absence recorded in the mapping must be visible in the document.

        The failure mode this guards against is a document that lists what
        works and quietly omits what does not - which reads as completeness.
        """
        rendered = OUTPUT.read_text(encoding="utf-8")
        for entry in mapping().get("absent") or []:
            assert f"`{entry['metric']}`" in rendered, entry["metric"]
        assert "UNAVAILABLE" in rendered


class TestTheStatuses:
    def test_verified_means_an_arithmetic_check_was_recorded(self) -> None:
        """VERIFIED is not a synonym for "mapped".

        It means the identity total / recorded_minutes * 90 reproduced the
        provider's own per-90 field. Anything mapped without that check is
        AVAILABLE, and the difference is the whole point of the column.
        """
        data = mapping()
        rows = {r.metric: r for r in build_rows(data)}

        for metric, entry in data["metrics"].items():
            note = entry.get("note") or ""
            expected = "VERIFIED" if ARITHMETIC_MARKER in note else "AVAILABLE"
            assert rows[metric].status == expected, metric

    def test_a_mapped_metric_is_never_reported_unavailable(self) -> None:
        data = mapping()
        rows = build_rows(data)
        mapped = set(data["metrics"]) | set(data.get("derived") or {})
        for row in rows:
            if row.status == "UNAVAILABLE":
                assert row.metric not in mapped, (
                    f"{row.metric} is both mapped and reported unavailable"
                )

    def test_rates_declare_recorded_minutes_as_their_denominator(self) -> None:
        """The distinction the whole provider integration turns on.

        `minutes` is time on the pitch; `recorded_minutes` is the time the
        detailed counts actually describe. Dividing by the wrong one understates
        every rate, and the document has to say which is used.
        """
        rows = {r.metric: r for r in build_rows(mapping())}
        assert rows["tackles"].denominator == "`recorded_minutes`"
        assert rows["minutes"].denominator == "not a rate"
        assert rows["recorded_minutes"].denominator == "not a rate"

    def test_the_counts_in_the_header_match_the_rows(self) -> None:
        data = mapping()
        rows = build_rows(data)
        rendered = render(data, rows)
        for status in ("VERIFIED", "AVAILABLE", "DERIVABLE", "UNAVAILABLE"):
            n = sum(1 for r in rows if r.status == status)
            assert f"| {n} |" in rendered, f"{status} count {n} missing from the summary"


class TestTheClaimsMatchReality:
    def test_no_document_still_says_a_key_is_awaited(self) -> None:
        """A real key has been used. Documentation saying otherwise is wrong.

        Scoped to the files that describe the current state; the specification
        is a verbatim record of the original brief and is not edited.
        """
        from pipelines.footystats.status import REPO_ROOT

        stale = ["no real key yet", "nothing to observe yet", "It is empty today"]
        checked = [
            REPO_ROOT / "README.md",
            REPO_ROOT / ".env.example",
            REPO_ROOT / "docs" / "footystats_provider_status.md",
        ]
        for path in checked:
            text = path.read_text(encoding="utf-8")
            for phrase in stale:
                assert phrase not in text, f"{path.name} still claims: {phrase}"
