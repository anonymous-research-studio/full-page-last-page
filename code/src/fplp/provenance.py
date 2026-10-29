"""Code and environment versions stored with every episode, so each result can be traced to the
code, SDKs and interpreter that produced it; and `fplp stamp`, which records the same versions and the
SHA-256 of each input beside a generated table or figure.

Usage: uv run fplp stamp results/tables/main_hypotheses.provenance.json data/processed/main.csv
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from fplp import __version__

_REPO = Path(__file__).resolve().parents[2]
# What can change an episode: the code, the configs and the locked dependencies. Analysis outputs,
# docs and the manuscript are left out, so writing results/ after the pilot does not mark the main
# study's episodes as dirty.
BEHAVIOR_PATHS = ("src", "configs", "pyproject.toml", "uv.lock")


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(_REPO), *args], capture_output=True, text=True, timeout=10, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip()


def _version(package: str) -> str | None:
    try:
        return version(package)
    except PackageNotFoundError:
        return None


def provenance() -> dict:
    """Taken once when a run starts, which is when the code is loaded. `git_dirty` is true when a
    tracked or untracked (not ignored) file under BEHAVIOR_PATHS differs from the commit; None outside
    a git checkout."""
    status = _git("status", "--porcelain", "--", *BEHAVIOR_PATHS)
    return {
        "harness_version": __version__,
        "git_sha": _git("rev-parse", "HEAD"),
        "git_dirty": None if status is None else bool(status),
        "python": platform.python_version(),
        "openai_sdk": _version("openai"),
        "anthropic_sdk": _version("anthropic"),
    }


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stamp(inputs: list[str | Path]) -> dict:
    """What produced a generated output: the code version (as for episodes), when, and the SHA-256 of each
    input file, so every number in the paper can be traced to one commit and one copy of the data."""
    return {**provenance(), "created_at": datetime.now(UTC).isoformat(), "inputs": {str(p): sha256(p) for p in inputs}}


def write_stamp(out: str | Path, inputs: list[str | Path]) -> dict:
    """Write the stamp as JSON and warn when the code cannot be traced to a clean commit."""
    record = stamp(inputs)
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n")
    commit = (record["git_sha"] or "unknown")[:7]
    print(f"wrote {path} (commit {commit}{', with uncommitted changes' if record['git_dirty'] else ''})")
    if record["git_dirty"] or not record["git_sha"]:
        print("WARNING: this output cannot be traced to a clean commit; commit the code and regenerate it")
    return record


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out", help="JSON file to write, e.g. results/tables/main_hypotheses.provenance.json")
    parser.add_argument("inputs", nargs="+", help="the files the output was computed from")
    args = parser.parse_args(argv)
    write_stamp(args.out, args.inputs)
