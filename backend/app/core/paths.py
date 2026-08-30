"""Where the repository root is, found rather than counted.

Eight modules each computed this as `Path(__file__).resolve().parents[3]`,
which encodes how deep the source tree happens to be. That is true of a
checkout and false of a container: with the application copied to `/app/app`,
the same expression walks one level too far and lands on `/`, so every
configuration file - roles, intelligence scores, similarity features, the
provider mapping - is looked for in `/config` and none of them are found.

Nothing announces that. The path is well-formed, the file is simply absent, and
the failure arrives as a missing role definition rather than as "the image is
laid out differently than the code assumed".

So the root is located by looking for something that marks it, and every module
imports the answer from here.
"""

from __future__ import annotations

import os
from pathlib import Path

#: What makes a directory the root: the configuration the application reads.
#:
#: `pyproject.toml` would be the conventional marker and the wrong one here -
#: there is one inside `backend/` too, so the search would stop a level short
#: and find no `config/` at all.
MARKER = "config"

#: Escape hatch for a layout this cannot infer. Set it and the search is
#: skipped entirely.
ENV_VAR = "FRI_ROOT"


def find_repo_root(start: Path | None = None) -> Path:
    """The nearest ancestor containing the configuration directory.

    Falls back to the historical `parents[3]` when no marker is found, so a
    tree without `config/` behaves as it did rather than raising during an
    import - a test fixture, say, or a partial checkout.
    """
    override = os.environ.get(ENV_VAR)
    if override:
        return Path(override).resolve()

    here = (start or Path(__file__)).resolve()
    for candidate in here.parents:
        if (candidate / MARKER).is_dir():
            return candidate

    return here.parents[3] if len(here.parents) > 3 else here.parent


REPO_ROOT = find_repo_root()

#: The configuration directory itself, which is what every caller actually
#: wanted from the root.
CONFIG_DIR = REPO_ROOT / MARKER
