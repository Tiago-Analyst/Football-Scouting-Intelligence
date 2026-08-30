"""Finding the repository root, in a layout the code did not grow up in.

Eight modules each resolved it as `Path(__file__).resolve().parents[3]`, which
encodes how deep the source tree happens to be. True of a checkout, false of a
container: with the application copied to `/app/app`, that expression walks one
level too far and lands on `/`, so every configuration file is looked for in
`/config` and none is found.

The failure would have been silent in the worst way - a well-formed path to a
file that simply is not there, surfacing as "no roles are configured" rather
than as a layout mismatch.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.paths import ENV_VAR, MARKER, find_repo_root


def build_tree(root: Path, depth: str, *, with_config: bool) -> Path:
    """Create a source tree and return the module file inside it."""
    module = root / depth / "app" / "analytics" / "roles.py"
    module.parent.mkdir(parents=True, exist_ok=True)
    module.write_text("", encoding="utf-8")
    if with_config:
        (root / MARKER).mkdir(exist_ok=True)
    return module


class TestFindingTheRoot:
    def test_a_checkout_resolves_to_the_repository(self, tmp_path: Path) -> None:
        """`repo/backend/app/analytics/roles.py`, with `repo/config/`."""
        module = build_tree(tmp_path, "backend", with_config=True)
        assert find_repo_root(module) == tmp_path

    def test_the_container_layout_resolves_too(self, tmp_path: Path) -> None:
        """The case that broke. One level shallower - `/app/app/analytics` -
        where counting three parents overshoots the top."""
        module = tmp_path / "app" / "analytics" / "roles.py"
        module.parent.mkdir(parents=True)
        module.write_text("", encoding="utf-8")
        (tmp_path / MARKER).mkdir()

        assert find_repo_root(module) == tmp_path
        assert module.resolve().parents[3] != tmp_path, (
            "this layout is exactly the one parents[3] gets wrong"
        )

    def test_it_stops_at_the_nearest_marker(self, tmp_path: Path) -> None:
        """A `config/` further up must not win over a nearer one."""
        (tmp_path / MARKER).mkdir()
        inner = tmp_path / "nested"
        module = build_tree(inner, "backend", with_config=True)
        assert find_repo_root(module) == inner

    def test_an_override_skips_the_search(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An escape hatch for a layout this cannot infer."""
        module = build_tree(tmp_path, "backend", with_config=True)
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.setenv(ENV_VAR, str(elsewhere))

        assert find_repo_root(module) == elsewhere

    def test_no_marker_falls_back_rather_than_raising(self, tmp_path: Path) -> None:
        """A tree with no `config/` - a partial checkout, a test fixture -
        should behave as it did before rather than fail at import time."""
        module = build_tree(tmp_path, "backend", with_config=False)
        assert find_repo_root(module) == tmp_path


class TestTheRealTree:
    def test_the_configuration_is_where_the_code_looks_for_it(self) -> None:
        """The end the whole thing exists for: the files actually resolve."""
        from app.core.paths import CONFIG_DIR

        assert CONFIG_DIR.is_dir()
        for name in (
            "player_roles.yaml",
            "intelligence_scores.yaml",
            "similarity_features.yaml",
            "footystats_mapping.yaml",
        ):
            assert (CONFIG_DIR / name).is_file(), name

    def test_every_module_agrees_on_the_root(self) -> None:
        """They used to each compute it, and a container made them disagree
        with reality in unison."""
        from app.analytics import intelligence, roles, similarity
        from app.core import config, paths
        from app.providers import footystats_mapping

        roots = {
            intelligence.REPO_ROOT,
            roles.REPO_ROOT,
            similarity.REPO_ROOT,
            config.REPO_ROOT,
            footystats_mapping.REPO_ROOT,
            paths.REPO_ROOT,
        }
        assert len(roots) == 1
