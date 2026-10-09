#!/usr/bin/env python3
"""Refresh hashes.json and package-lock.json from npm latest or an exact approved version."""

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
SEMVER = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
)
ROOT = Path(__file__).resolve().parent
HASHES = ROOT / "hashes.json"
LOCK = ROOT / "package-lock.json"


def tarball_url(version: str) -> str:
    return f"https://registry.npmjs.org/@deepseek-ai/dsh/-/dsh-{version}.tgz"


def semver_key(version: str) -> tuple:
    """Standard SemVer precedence, ignoring build metadata."""
    match = SEMVER.fullmatch(version)
    if match is None:
        raise ValueError(f"invalid SemVer version: {version!r}")
    major, minor, patch, prerelease, _build = match.groups()
    identifiers = []
    if prerelease is not None:
        for identifier in prerelease.split("."):
            if identifier.isdigit():
                if len(identifier) > 1 and identifier.startswith("0"):
                    raise ValueError(f"invalid SemVer version: {version!r}")
                identifiers.append((0, int(identifier)))
            else:
                identifiers.append((1, identifier))
    return (int(major), int(minor), int(patch), prerelease is None, tuple(identifiers))


def validate_version(metadata: dict, version: str) -> None:
    """Require a literal version and an exact matching npm registry manifest."""
    semver_key(version)
    release = metadata.get("versions", {}).get(version)
    if not isinstance(release, dict):
        raise ValueError(f"npm has no published version {version!r}")
    if release.get("name") != PACKAGE or release.get("version") != version:
        raise ValueError(f"npm metadata does not match {PACKAGE}@{version}")


def select_version(metadata: dict, packaged: str, version: str | None = None) -> str | None:
    """Select an exact override, or npm latest only when newer than packaged."""
    if version is not None:
        validate_version(metadata, version)
        return None if version == packaged else version
    latest = metadata["dist-tags"]["latest"]
    return latest if semver_key(latest) > semver_key(packaged) else None


def freshness_error(metadata: dict, packaged: str, now: datetime) -> str | None:
    """An error when a newer npm `latest` is unpackaged for longer than MAX_LAG."""
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
        if manifest.get("name") != PACKAGE or manifest.get("version") != version:
            raise ValueError(f"npm tarball manifest does not match {PACKAGE}@{version}")
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


def update(metadata: dict, version: str | None = None) -> int:
    current = json.loads(HASHES.read_text())
    latest = select_version(metadata, current["version"], version)
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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--version", help="package this exact published version (including prereleases)")
    mode.add_argument("--check-freshness", action="store_true", help="fail when newer npm latest is unpackaged for over 48h")
    args = parser.parse_args()
    metadata = fetch_metadata()
    try:
        return check_or_update(metadata, args)
    except ValueError as error:
        parser.error(str(error))


def check_or_update(metadata: dict, args: argparse.Namespace) -> int:
    if args.check_freshness:
        packaged = json.loads(HASHES.read_text())["version"]
        error = freshness_error(metadata, packaged, datetime.now(timezone.utc))
        if error:
            print(error, file=sys.stderr)
            return 1
        print(f"fresh (packaged {packaged}, npm latest {metadata['dist-tags']['latest']})")
        return 0
    return update(metadata, args.version)


if __name__ == "__main__":
    raise SystemExit(main())
