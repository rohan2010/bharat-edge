"""Back up everything that is gitignored but must not be lost, to a private HF dataset repo.

Until publication, git holds only code and configs. This backs up the rest:
  - data/work/       translation worksheets (the native speaker's work)
  - data/frozen/     frozen item sets
  - data/manifests/  item ids, hashes and selection rules of the frozen sets
  - configs/model_store.json   ledger pinning every GGUF build to its HF commit
  - the research write-up and notes in docs/
Push after every translation session and after every run that changes these files.

    uv run python data/backup.py push       # upload (one commit)
    uv run python data/backup.py restore    # download files missing locally; report differences
    uv run python data/backup.py restore --force   # also overwrite local files that differ
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from fnmatch import fnmatch
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download

from bee.provenance import sha256_file

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = [
    "data/work/**",
    "data/frozen/**",
    "data/manifests/**",
    "configs/model_store.json",
    "docs/BharatEdge-Eval Project Write-up and Literature Review.*",
    "docs/setup-log.md",
    "docs/data-availability.md",
]
OLD_LAYOUT = ["work/**", "frozen/**"]  # paths used before 2026-10-16 (relative to data/)
REPO_NAME = "bharatedge-data"


def repo_id(api: HfApi) -> str:
    return f"{api.whoami()['name']}/{REPO_NAME}"


def matches(rel: str) -> bool:
    return any(fnmatch(rel, p) for p in PATTERNS)


def local_files() -> list[Path]:
    files: set[Path] = set()
    for pat in PATTERNS:
        if pat.endswith("/**"):
            files.update(p for p in (ROOT / pat[:-3]).rglob("*") if p.is_file())
        else:
            files.update(p for p in ROOT.glob(pat) if p.is_file())
    return sorted(files)


def push(api: HfApi) -> None:
    """One commit: add/update every local file, remove files left from the old layout."""
    from huggingface_hub import CommitOperationAdd, CommitOperationDelete

    repo = repo_id(api)
    api.create_repo(repo, repo_type="dataset", private=True, exist_ok=True)
    files = local_files()
    ops: list[CommitOperationAdd | CommitOperationDelete] = [
        CommitOperationAdd(path_in_repo=p.relative_to(ROOT).as_posix(), path_or_fileobj=str(p))
        for p in files
    ]
    remote = api.list_repo_files(repo, repo_type="dataset")
    ops += [
        CommitOperationDelete(path_in_repo=f)
        for f in remote
        if any(fnmatch(f, pat) for pat in OLD_LAYOUT)
    ]
    commit = api.create_commit(
        repo, operations=ops, commit_message=f"Backup {len(files)} files", repo_type="dataset"
    )
    print(f"backed up {len(files)} files -> {repo} (private) {commit.oid[:8]}")


def restore(api: HfApi, force: bool) -> int:
    repo = repo_id(api)
    with tempfile.TemporaryDirectory() as tmp:
        snapshot_download(repo, repo_type="dataset", local_dir=tmp, allow_patterns=PATTERNS)
        differ = 0
        for src in sorted(p for p in Path(tmp).rglob("*") if p.is_file()):
            rel = src.relative_to(tmp).as_posix()
            if not matches(rel):
                continue
            dest = ROOT / rel
            if dest.exists() and sha256_file(dest) == sha256_file(src):
                continue
            if dest.exists() and not force:
                print(f"differs (kept local): {rel}")
                differ += 1
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            print(f"restored {rel}")
    if differ:
        print(f"{differ} local files differ from the backup; --force overwrites them")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Back up gitignored research files to private HF.")
    p.add_argument("cmd", choices=["push", "restore"])
    p.add_argument("--force", action="store_true", help="restore: overwrite differing files")
    args = p.parse_args(argv)
    api = HfApi()
    if args.cmd == "push":
        push(api)
        return 0
    return restore(api, args.force)


if __name__ == "__main__":
    sys.exit(main())
