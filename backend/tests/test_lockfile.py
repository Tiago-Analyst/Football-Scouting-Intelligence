"""The production image installs from `requirements.lock`, with hashes.

CI recompiles the lock and fails on any difference; these checks are the cheap,
offline half: the file is well formed, every pin carries a hash, the direct
dependencies and the `certifi` floor are in it, and the Dockerfile really does
refuse anything unhashed.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
LOCK = (BACKEND / "requirements.lock").read_text(encoding="utf-8")
PINS = {
    m.group(1).lower().replace("_", "-"): m.group(2)
    for m in re.finditer(r"^([A-Za-z0-9_.-]+)==(\S+) [\\]$", LOCK, re.MULTILINE)
}


def test_every_pin_carries_at_least_one_hash() -> None:
    blocks = re.split(r"(?m)^(?=[A-Za-z0-9_.-]+==)", LOCK)
    entries = [b for b in blocks if re.match(r"[A-Za-z0-9_.-]+==", b)]
    assert len(entries) == len(PINS) > 20
    for entry in entries:
        assert re.search(r"--hash=sha256:[0-9a-f]{64}", entry), entry.splitlines()[0]


def test_nothing_is_pinned_loosely_or_from_a_url() -> None:
    for line in LOCK.splitlines():
        assert not line.startswith(("-e ", "git+", "http://", "https://")), line


def test_every_direct_dependency_is_locked() -> None:
    project = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    for requirement in project["dependencies"]:
        name = re.split(r"[\[<>=!~ ;]", requirement, maxsplit=1)[0].lower().replace("_", "-")
        assert name in PINS, f"{name} is in pyproject.toml but not in requirements.lock"


def test_certifi_is_at_or_above_the_floor_in_pyproject() -> None:
    floor = tuple(int(p) for p in ["2026", "10", "19"])
    locked = tuple(int(p) for p in PINS["certifi"].split("."))
    assert locked >= floor
    assert "certifi>=2026.10.19" in (BACKEND / "pyproject.toml").read_text(encoding="utf-8")


def test_the_image_installs_only_what_the_lock_names() -> None:
    dockerfile = (BACKEND / "Dockerfile").read_text(encoding="utf-8")
    assert "pip install --require-hashes --no-deps -r requirements.lock" in dockerfile
    assert "COPY backend/requirements.lock" in dockerfile
    assert "pip install ." not in dockerfile
