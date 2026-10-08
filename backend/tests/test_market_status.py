"""What System Status says about market data, and what it is asking.

Two different questions had been collapsed into one:

  - can an ingestion snapshot be opened on this machine's disk?
  - is market data available and valid for the product?

Production answered the first and published it as the second. Every profile
served a market value, a valuation history and a transfer list; Opportunities
screened on market value and contract length; Data Quality listed Transfermarkt
as a serving source with rows and passing checks - and System Status said
"Market data: unavailable" and told the reader to run a download command.

Nothing was broken. The page was reporting an ingestion precondition that is
false on the serving host by design, because the API is not what does the
downloading.
"""

from __future__ import annotations

import pytest

from app.api.v1 import health
from app.services.quality_service import MarketServing
from tests.conftest import build_settings

SERVING = MarketServing(
    players_with_value=4210,
    players_with_contract=2680,
    valuations=51204,
    transfers=18333,
)
NOTHING = MarketServing(
    players_with_value=0,
    players_with_contract=0,
    valuations=0,
    transfers=0,
)


class TestItReportsWhatIsServed:
    def test_served_market_data_is_available_even_with_no_snapshot_on_disk(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The production case that was being reported backwards."""
        monkeypatch.setattr(health, "market_serving", lambda _session: SERVING)
        monkeypatch.setattr(health, "get_session_factory", _factory())
        # The snapshot is absent, as it is on the serving host.
        monkeypatch.setattr(health, "build_market_provider", _raises())

        status = health._market_source(build_settings(app_mode="production"))

        assert status.provider != "unavailable"
        assert status.validated is True
        assert status.is_mock is False
        assert "51204" in status.notes
        assert "18333" in status.notes

    def test_it_does_not_tell_a_reader_to_run_a_download(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An operator instruction is not an answer to "is this data valid?"."""
        monkeypatch.setattr(health, "market_serving", lambda _session: SERVING)
        monkeypatch.setattr(health, "get_session_factory", _factory())
        monkeypatch.setattr(health, "build_market_provider", _raises())

        status = health._market_source(build_settings(app_mode="production"))

        assert "pipelines.transfermarkt.download" not in (status.notes or "")

    def test_nothing_served_and_nothing_to_load_is_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The genuine failure must still be reported as one."""
        monkeypatch.setattr(health, "market_serving", lambda _session: NOTHING)
        monkeypatch.setattr(health, "get_session_factory", _factory())
        monkeypatch.setattr(health, "build_market_provider", _raises())

        status = health._market_source(build_settings(app_mode="production"))

        assert status.provider == "unavailable"
        assert status.validated is False
        # Both halves of the truth: nothing serving, and nothing to load.
        assert "No market data is being served" in (status.notes or "")

    def test_a_readable_snapshot_does_not_disguise_an_empty_database(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The inverse of the original defect, and just as misleading.

        The snapshot has to be patched in, not left to the machine. An earlier
        version of this test only passed where a Transfermarkt download
        happened to sit on disk - green on a developer's laptop, red on CI,
        and testing the filesystem rather than the code either way.
        """
        monkeypatch.setattr(health, "market_serving", lambda _session: NOTHING)
        monkeypatch.setattr(health, "get_session_factory", _factory())
        monkeypatch.setattr(health, "build_market_provider", _readable_snapshot())

        status = health._market_source(build_settings(app_mode="production"))

        assert "no market rows are being served" in (status.notes or "")


class TestWhenTheDatabaseCannotAnswer:
    def test_an_unreachable_database_falls_back_to_the_provider(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Unknown is not the same as empty, and must not be reported as it."""

        def unreachable() -> object:
            raise OSError("connection refused")

        monkeypatch.setattr(health, "get_session_factory", unreachable)
        monkeypatch.setattr(health, "build_market_provider", _raises())

        status = health._market_source(build_settings(app_mode="production"))

        assert status.provider == "unavailable"
        # Not the "nothing is being served" sentence: nothing was established.
        assert "No market data is being served" not in (status.notes or "")

    def test_it_does_not_claim_an_empty_database_it_never_read(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A readable snapshot and an unknown database is not an empty one.

        The snapshot is patched in for the same reason as above: left to the
        machine, this test takes a different branch depending on whether a
        download happens to sit on disk.
        """

        def unreachable() -> object:
            raise OSError("connection refused")

        monkeypatch.setattr(health, "get_session_factory", unreachable)
        monkeypatch.setattr(health, "build_market_provider", _readable_snapshot())

        status = health._market_source(build_settings(app_mode="production"))

        assert "no market rows are being served" not in (status.notes or "")


class TestDemoIsUnchanged:
    def test_demo_still_reports_the_mock_provider(self) -> None:
        """Fabricated rows are not evidence of market data."""
        status = health._market_source(build_settings(app_mode="demo"))

        assert status.is_mock is True
        assert status.validated is False

    def test_demo_does_not_count_rows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Counting invented rows would make demo claim a real source."""

        def fail(_session: object) -> MarketServing:
            raise AssertionError("demo must not consult the serving tables")

        monkeypatch.setattr(health, "market_serving", fail)
        health._market_source(build_settings(app_mode="demo"))


class TestTheCountsDescribeThePages:
    def test_availability_follows_any_market_figure_the_site_shows(self) -> None:
        """A valuation history alone is still market data being served."""
        assert MarketServing(0, 0, 12, 0).available is True
        assert MarketServing(0, 0, 0, 12).available is True
        assert MarketServing(12, 0, 0, 0).available is True
        assert NOTHING.available is False

    def test_a_contract_expiry_alone_is_not_market_data(self) -> None:
        """Contract dates come with the identity set; they are not a market."""
        assert MarketServing(0, 900, 0, 0).available is False


def _factory() -> object:
    """A session factory whose session is never used by the patched counter."""

    class _Session:
        def __enter__(self) -> object:
            return object()

        def __exit__(self, *_args: object) -> bool:
            return False

    # `get_session_factory()()` - a factory that makes the session.
    return lambda: lambda: _Session()


def _readable_snapshot() -> object:
    """A market provider that builds, as it does where the dataset is on disk.

    Only the ingestion side is healthy here; the serving database is empty.
    That combination is what the test above is about, and leaving it to
    whether a download happens to exist locally is how the test came to pass
    on one machine and fail on another.
    """
    from app.schemas.market import MarketProviderInfo

    class _Provider:
        @property
        def info(self) -> MarketProviderInfo:
            return MarketProviderInfo(
                name="TransfermarktDatasetProvider",
                is_mock=False,
                validated=True,
                licence="CC0",
                notes="Snapshot readable.",
            )

    return lambda _settings: _Provider()


def _raises() -> object:
    """A market provider that cannot be built, as on the serving host."""
    from app.core.errors import ProviderNotConfiguredError

    def build(_settings: object) -> object:
        raise ProviderNotConfiguredError(
            "Transfermarkt snapshot unavailable: Transfermarkt snapshot is "
            "incomplete; missing tables: players, clubs. Run: python -m "
            "pipelines.transfermarkt.download"
        )

    return build
