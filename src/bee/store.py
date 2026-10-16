"""Off-machine storage for GGUF builds in private Hugging Face model repos.

Disk on the Mac is too small to keep all 24 builds at once, so builds are quantized one model at a
time, pushed here, deleted locally, and pulled back (by pinned commit, hash-checked) when a later
milestone needs them. One private repo per model: ``<owner>/bharatedge-<model_key>-gguf``.

The ledger ``configs/model_store.json`` (gitignored until publication; backed up by
data/backup.py) maps every stored file to its repo,
HF commit and SHA-256, so a pull always returns exactly the bytes that were pushed.

    uv run python -m bee.store create                      # create the private repos (write token)
    uv run python -m bee.store push qwen3-1.7b qwen3-1.7b-Q4_K_M.gguf [...]
    uv run python -m bee.store pull qwen3-1.7b qwen3-1.7b-Q4_K_M.gguf
    uv run python -m bee.store status
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import yaml

from bee.provenance import sha256_file

MODELS_CONFIG = Path("configs/models.yaml")
LEDGER = Path("configs/model_store.json")
MODELS_DIR = Path("models")

# HF licence tags per family (metadata only; the repos are private).
_LICENSES = {"gemma3": "gemma", "llama3": "llama3.2", "qwen3": "apache-2.0"}


def repo_id(owner: str, model_key: str) -> str:
    return f"{owner}/bharatedge-{model_key}-gguf"


def load_models(path: Path = MODELS_CONFIG) -> dict[str, dict[str, Any]]:
    return yaml.safe_load(path.read_text())["models"]


def load_ledger(path: Path = LEDGER) -> dict[str, Any]:
    if not path.exists():
        return {"schema": 1, "models": {}}
    return json.loads(path.read_text())


def save_ledger(ledger: dict[str, Any], path: Path = LEDGER) -> None:
    path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n")


def record_push(
    ledger: dict[str, Any], model_key: str, repo: str, revision: str, files: dict[str, dict]
) -> None:
    """Add pushed files ({name: {sha256, bytes}}) to the ledger at ``revision``."""
    entry = ledger["models"].setdefault(model_key, {"repo": repo, "files": {}})
    entry["repo"] = repo
    for name, meta in files.items():
        entry["files"][name] = {**meta, "revision": revision}


def verify(path: Path, expected_sha256: str) -> None:
    actual = sha256_file(path)
    if actual != expected_sha256:
        raise ValueError(f"{path}: sha256 {actual} != recorded {expected_sha256}")


def model_card(model_key: str, model: dict[str, Any]) -> str:
    license_tag = _LICENSES.get(model["family"], "other")
    return f"""---
license: {license_tag}
base_model: {model["hf_repo"]}
tags: [gguf, bharatedge-eval]
---

# bharatedge-{model_key}-gguf (private storage)

GGUF builds of [{model["hf_repo"]}](https://huggingface.co/{model["hf_repo"]}) used by the
BharatEdge-Eval study. This is a private working store, not a release: files are pinned by
commit and SHA-256 in `configs/model_store.json` of the study repo, and every build's
llama.cpp commit is recorded there. Use is governed by the base model's licence.
"""


def _api():
    from huggingface_hub import HfApi

    return HfApi()


def cmd_create(args: argparse.Namespace) -> None:
    api = _api()
    owner = args.owner or api.whoami()["name"]
    for key, model in load_models().items():
        if args.models and key not in args.models:
            continue
        repo = repo_id(owner, key)
        api.create_repo(repo, repo_type="model", private=True, exist_ok=True)
        api.upload_file(
            path_or_fileobj=model_card(key, model).encode(),
            path_in_repo="README.md",
            repo_id=repo,
            commit_message="Model card",
        )
        print(f"ready: https://huggingface.co/{repo} (private)")


def push_files(
    model_key: str,
    names: list[str],
    owner: str | None = None,
    expected_sha256: dict[str, str] | None = None,
) -> str:
    """Push ``models/<model_key>/<name>`` files in one commit, record them, return the HF commit.

    Every file is hashed here, at push time; ``expected_sha256`` (e.g. from a build record) is
    compared against that hash, so a file that changed on disk after it was built is refused.
    """
    from huggingface_hub import CommitOperationAdd

    model_dir = MODELS_DIR / model_key
    files, ops = {}, []
    for name in names:
        path = model_dir / name
        sha = sha256_file(path)
        expected = (expected_sha256 or {}).get(name)
        if expected and sha != expected:
            raise ValueError(f"{path}: sha256 {sha} != build record {expected}")
        files[name] = {"sha256": sha, "bytes": path.stat().st_size}
        ops.append(CommitOperationAdd(path_in_repo=name, path_or_fileobj=str(path)))
    source = model_dir / "SOURCE.txt"
    if source.exists():
        ops.append(CommitOperationAdd(path_in_repo="SOURCE.txt", path_or_fileobj=str(source)))
    api = _api()
    owner = owner or api.whoami()["name"]
    repo = repo_id(owner, model_key)
    total = sum(f["bytes"] for f in files.values())
    start = time.monotonic()
    commit = api.create_commit(
        repo, operations=ops, commit_message=f"Add {', '.join(names)}", repo_type="model"
    )
    secs = time.monotonic() - start
    ledger = load_ledger()
    record_push(ledger, model_key, repo, commit.oid, files)
    save_ledger(ledger)
    for name, meta in files.items():
        print(f"pushed {name} -> {repo}@{commit.oid[:8]} sha256 {meta['sha256'][:12]}")
    print(f"  {total / 1e9:.2f} GB in {secs:.0f} s ({total / 1e6 / max(secs, 1e-9):.1f} MB/s)")
    return commit.oid


def cmd_push(args: argparse.Namespace) -> None:
    push_files(args.model, args.files, owner=args.owner)
    print(f"ledger updated: {LEDGER} (back it up: data/backup.py push)")


def cmd_pull(args: argparse.Namespace) -> None:
    from huggingface_hub import hf_hub_download

    entry = load_ledger()["models"].get(args.model)
    if not entry:
        sys.exit(f"{args.model}: nothing in {LEDGER}")
    out_dir = MODELS_DIR / args.model
    for name in args.files:
        meta = entry["files"].get(name)
        if not meta:
            sys.exit(f"{args.model}/{name}: not in {LEDGER}")
        dest = out_dir / name
        if dest.exists():
            verify(dest, meta["sha256"])
            print(f"present {dest} (sha256 ok)")
            continue
        path = Path(
            hf_hub_download(entry["repo"], name, revision=meta["revision"], local_dir=out_dir)
        )
        try:
            verify(path, meta["sha256"])
        except ValueError:
            path.unlink(missing_ok=True)
            raise
        print(f"pulled {path} (sha256 ok)")


def cmd_status(_args: argparse.Namespace) -> None:
    ledger = load_ledger()
    if not ledger["models"]:
        print(f"{LEDGER}: no files stored yet")
    for key, entry in sorted(ledger["models"].items()):
        print(f"{key}  {entry['repo']}")
        for name, meta in sorted(entry["files"].items()):
            local = "local" if (MODELS_DIR / key / name).exists() else "remote"
            gb = meta["bytes"] / 1e9
            print(f"  {name:45s} {gb:5.2f} GB  @{meta['revision'][:8]}  {local}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="bee.store", description="Store GGUF builds in private HF repos."
    )
    p.add_argument("--owner", help="HF user or org (default: the logged-in user)")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create", help="create one private repo per model")
    c.add_argument("models", nargs="*", help="model keys (default: all in models.yaml)")
    for name, fn in (("push", cmd_push), ("pull", cmd_pull)):
        s = sub.add_parser(name)
        s.add_argument("model")
        s.add_argument("files", nargs="+")
        s.set_defaults(fn=fn)
    c.set_defaults(fn=cmd_create)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
