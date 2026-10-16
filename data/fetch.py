"""Download the pinned upstream task data into data/raw/ and record file hashes.

    uv run python data/fetch.py            # download (skips files whose hash already matches)
    uv run python data/fetch.py --check    # verify local files against the recorded hashes

Sources and revisions: configs/data_sources.yaml. Hashes: data/manifests/sources.json
(gitignored until publication; backed up by data/backup.py).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml
from huggingface_hub import hf_hub_download

from bee.provenance import sha256_file

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "configs/data_sources.yaml"
RAW = ROOT / "data/raw"
MANIFEST = ROOT / "data/manifests/sources.json"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Download pinned task data into data/raw/.")
    p.add_argument("--check", action="store_true", help="verify only; download nothing")
    args = p.parse_args(argv)
    sources = yaml.safe_load(SOURCES.read_text())["sources"]
    recorded = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    manifest, failed = {}, False
    for key, src in sources.items():
        for name in src["files"]:
            ref = f"{key}/{name}"
            local = RAW / key / name
            want = recorded.get(ref, {})
            if want.get("revision") != src["revision"]:
                want = {}
            if args.check:
                ok = local.exists() and want and sha256_file(local) == want["sha256"]
                print(f"{'ok  ' if ok else 'FAIL'} {ref}")
                failed |= not ok
                continue
            if not (local.exists() and want and sha256_file(local) == want["sha256"]):
                hf_hub_download(
                    src["repo"],
                    name,
                    repo_type="dataset",
                    revision=src["revision"],
                    local_dir=RAW / key,
                )
            sha = sha256_file(local)
            if want and sha != want["sha256"]:
                sys.exit(f"{ref}: sha256 {sha} != recorded {want['sha256']}")
            manifest[ref] = {
                "repo": src["repo"],
                "revision": src["revision"],
                "sha256": sha,
                "bytes": local.stat().st_size,
            }
            print(f"{ref}  {sha[:12]}")
    if not args.check:
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
