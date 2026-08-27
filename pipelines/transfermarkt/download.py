"""Fetch the Transfermarkt dataset snapshot.

Source: https://github.com/dcaribou/transfermarkt-datasets (CC0-1.0), published
as a single archive on the project's public object store. The Transfermarkt
website itself is never scraped.

Run from the repository root:
    python -m pipelines.transfermarkt.download

The archive lands in `data/raw/transfermarkt/` (git-ignored) alongside a
manifest recording the URL, retrieval time, byte count and SHA-256. Section 4
of the spec requires raw snapshots be kept so a transformation can be
reproduced later; without the checksum, "which snapshot produced this table?"
is unanswerable.

Downloads resume: a 218 MB transfer that dies at 90% should not start over.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DATASET_BASE = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data/"
ARCHIVE_NAME = "transfermarkt-datasets.zip"
SOURCE_REPO = "https://github.com/dcaribou/transfermarkt-datasets"
LICENCE = "CC0-1.0"

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw" / "transfermarkt"

CHUNK = 1 << 20  # 1 MiB


def _checked_request(url: str, **kwargs: Any) -> urllib.request.Request:
    """Build a request, refusing anything that is not HTTPS.

    urlopen honours file:// and other schemes. Everything here is fetched over
    the network and then used as input to transformations, so a non-HTTPS URL
    is rejected rather than trusted.
    """
    if not url.lower().startswith("https://"):
        raise ValueError(f"refusing non-HTTPS URL: {url}")
    return urllib.request.Request(url, **kwargs)  # noqa: S310 - https enforced above


def _ssl_context() -> ssl.SSLContext:
    """A verifying TLS context that also honours the OS trust store.

    Python verifies against its own bundled CA set. On a machine running
    TLS-inspecting software (corporate proxies, some antivirus products) the
    presented certificate is signed by a locally-installed root that the OS
    trusts but Python's bundle does not, and every request fails with
    CERTIFICATE_VERIFY_FAILED.

    truststore delegates to the OS trust store, which keeps verification fully
    enabled. Verification is never disabled here - an unverified download of an
    archive we then execute transformations over is not an acceptable trade.
    """
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


def _human(num_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(num_bytes) < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} TB"


def _remote_size(url: str, context: ssl.SSLContext) -> int | None:
    request = _checked_request(url, method="HEAD", headers={"User-Agent": "fri-pipeline"})
    try:
        with urllib.request.urlopen(request, context=context, timeout=60) as response:  # noqa: S310 - scheme checked above
            length = response.headers.get("Content-Length")
            return int(length) if length else None
    except Exception:
        return None


def download(url: str, destination: Path, *, force: bool = False) -> Path:
    """Stream `url` to `destination`, resuming a partial transfer if present."""
    context = _ssl_context()
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")

    total = _remote_size(url, context)

    if destination.exists() and not force:
        actual = destination.stat().st_size
        if total is None or actual == total:
            print(f"already present: {destination.name} ({_human(actual)})")
            return destination
        print(f"size mismatch ({_human(actual)} vs {_human(total)}); re-downloading")
        destination.unlink()

    offset = partial.stat().st_size if partial.exists() and not force else 0
    if force and partial.exists():
        partial.unlink()
        offset = 0

    headers = {"User-Agent": "fri-pipeline"}
    if offset:
        headers["Range"] = f"bytes={offset}-"
        print(f"resuming from {_human(offset)}")

    request = _checked_request(url, headers=headers)
    with urllib.request.urlopen(request, context=context, timeout=120) as response:  # noqa: S310 - scheme checked above
        # A server that ignores Range replies 200 and restarts the body; writing
        # that onto an existing partial would silently corrupt the file.
        if offset and response.status != 206:
            print("server ignored resume request; starting over")
            offset = 0

        mode = "ab" if offset else "wb"
        written = offset
        with partial.open(mode) as handle:
            while chunk := response.read(CHUNK):
                handle.write(chunk)
                written += len(chunk)
                if total:
                    pct = written / total * 100
                    print(
                        f"\r  {_human(written)} / {_human(total)}  ({pct:5.1f}%)",
                        end="",
                        flush=True,
                    )
                else:
                    print(f"\r  {_human(written)}", end="", flush=True)
    print()

    if total is not None and written != total:
        partial.unlink(missing_ok=True)
        raise OSError(f"incomplete download: got {written} bytes, expected {total}")

    partial.replace(destination)
    return destination


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(path: Path, url: str) -> dict[str, object]:
    """Record what was fetched, when, and its checksum."""
    manifest = {
        "source_repository": SOURCE_REPO,
        "licence": LICENCE,
        "url": url,
        "file": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
        "retrieved_at": datetime.now(UTC).isoformat(),
        "note": (
            "Raw provider snapshot. Not redistributed and not committed to the "
            "repository. Retained so transformations are reproducible."
        ),
    }
    manifest_path = path.with_name(f"{path.stem}.manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download the Transfermarkt dataset snapshot.")
    parser.add_argument("--force", action="store_true", help="re-download even if present")
    parser.add_argument("--out", type=Path, default=RAW_DIR, help="destination directory")
    args = parser.parse_args(argv)

    url = DATASET_BASE + ARCHIVE_NAME
    destination = args.out / ARCHIVE_NAME

    print(f"source : {SOURCE_REPO}  ({LICENCE})")
    print(f"url    : {url}")
    print(f"target : {destination}")

    path = download(url, destination, force=args.force)
    manifest = write_manifest(path, url)

    print(f"\nsize   : {_human(manifest['size_bytes'])}")  # type: ignore[arg-type]
    print(f"sha256 : {manifest['sha256']}")
    print(f"manifest: {path.with_name(f'{path.stem}.manifest.json').name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
