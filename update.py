#!/usr/bin/env python3
"""Refresh hashes.json and package-lock.json from npm's latest @deepseek-ai/dsh."""

import argparse
import json
import re
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

PACKAGE = "@deepseek-ai/dsh"
REGISTRY_URL = "https://registry.npmjs.org/@deepseek-ai%2fdsh"
FAKE_HASH = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
MAX_LAG = timedelta(hours=48)
ROOT = Path(__file__).resolve().parent
HASHES = ROOT / "hashes.json"
LOCK = ROOT / "package-lock.json"


def tarball_url(version: str) -> str:
    return f"https://registry.npmjs.org/@deepseek-ai/dsh/-/dsh-{version}.tgz"


def select_version(metadata: dict, packaged: str) -> str | None:
    """The npm `latest` version when it differs from the packaged one, else None."""
    latest = metadata["dist-tags"]["latest"]
    return None if latest == packaged else latest


def freshness_error(metadata: dict, packaged: str, now: datetime) -> str | None:
    """An error when npm's `latest` has gone unpackaged for longer than MAX_LAG."""
    latest = select_version(metadata, packaged)
    if latest is None:
        return None
    published = datetime.fromisoformat(metadata["time"][latest].replace("Z", "+00:00"))
    age = now - published
    if age <= MAX_LAG:
        return None
    hours = int(age.total_seconds() // 3600)
    return f"npm latest {latest} has been unpackaged for {hours}h (packaged: {packaged}, limit: 48h)"


def fetch_metadata() -> dict:
    request = urllib.request.Request(REGISTRY_URL, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, text=True, **kwargs)


def prefetch_source(version: str) -> str:
    out = run(["nix", "store", "prefetch-file", "--json", tarball_url(version)], capture_output=True)
    return json.loads(out.stdout)["hash"]


def generate_lock(version: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tgz = Path(tmp) / "dsh.tgz"
        urllib.request.urlretrieve(tarball_url(version), tgz)
        with tarfile.open(tgz) as archive:
            archive.extractall(tmp, filter="data")
        package_dir = Path(tmp) / "package"
        manifest = json.loads((package_dir / "package.json").read_text())
        manifest.pop("devDependencies", None)
        (package_dir / "package.json").write_text(json.dumps(manifest, indent=2) + "\n")
        run(
            ["npm", "install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--no-fund"],
            cwd=package_dir,
        )
        LOCK.write_text((package_dir / "package-lock.json").read_text())


def npm_deps_hash() -> str:
    build = subprocess.run(
        ["nix", "build", "--no-link", "-L", f"{ROOT}#dsh.npmDeps"],
        text=True,
        capture_output=True,
    )
    match = re.search(r"got:\s+(sha256-[A-Za-z0-9+/=]+)", build.stderr)
    if match is None:
        sys.stderr.write(build.stderr)
        raise SystemExit("could not determine npmDepsHash from the fixed-output mismatch")
    return match.group(1)


def write_hashes(data: dict) -> None:
    HASHES.write_text(json.dumps(data, indent=2) + "\n")


def update(metadata: dict) -> int:
    current = json.loads(HASHES.read_text())
    latest = select_version(metadata, current["version"])
    if latest is None:
        print(f"no change ({current['version']})")
        return 0
    generate_lock(latest)
    data = {"version": latest, "sourceHash": prefetch_source(latest), "npmDepsHash": FAKE_HASH}
    write_hashes(data)
    data["npmDepsHash"] = npm_deps_hash()
    write_hashes(data)
    print(f"updated {current['version']} -> {latest}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-freshness", action="store_true", help="fail when npm latest is unpackaged for over 48h")
    args = parser.parse_args()
    metadata = fetch_metadata()
    if args.check_freshness:
        packaged = json.loads(HASHES.read_text())["version"]
        error = freshness_error(metadata, packaged, datetime.now(timezone.utc))
        if error:
            print(error, file=sys.stderr)
            return 1
        print(f"fresh (packaged {packaged}, npm latest {metadata['dist-tags']['latest']})")
        return 0
    return update(metadata)


if __name__ == "__main__":
    raise SystemExit(main())
