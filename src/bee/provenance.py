"""Run provenance: the JSONL header every run must start with.

Rule (CLAUDE.md): every run records the llama.cpp commit, GGUF file hash, config hash and seed
in its JSONL header. ``build_run_header`` assembles that record; ``write_run_header`` writes it
as the first line of a results file.

Note: llama-cpp-python vendors its own copy of llama.cpp, which may differ from the commit in
``third_party/llama.cpp`` used for ``llama-quantize``. Both are recorded.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any, TextIO

HEADER_SCHEMA_VERSION = 1
DEFAULT_LLAMA_CPP_DIR = Path("third_party/llama.cpp")
_CHUNK = 8 * 1024 * 1024


def sha256_file(path: str | Path) -> str:
    """Streaming SHA-256 of a (possibly multi-GB) file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def config_hash(config: Any) -> str:
    """SHA-256 of the canonical JSON form of ``config`` (key order does not matter)."""
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def llama_cpp_commit(repo_dir: str | Path = DEFAULT_LLAMA_CPP_DIR) -> str:
    """Full commit hash of the llama.cpp checkout. Raises if it cannot be determined."""
    repo = Path(repo_dir)
    if not repo.exists():
        raise FileNotFoundError(f"llama.cpp checkout not found: {repo}")
    out = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def _pkg_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def build_run_header(
    *,
    gguf_path: str | Path,
    config: dict[str, Any],
    seed: int,
    llama_cpp_dir: str | Path = DEFAULT_LLAMA_CPP_DIR,
    gguf_sha256: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the header record for one run.

    ``gguf_sha256`` may be passed to skip re-hashing a large file whose hash is already recorded.
    """
    gguf = Path(gguf_path)
    header: dict[str, Any] = {
        "record": "header",
        "schema_version": HEADER_SCHEMA_VERSION,
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "llama_cpp_commit": llama_cpp_commit(llama_cpp_dir),
        "llama_cpp_python_version": _pkg_version("llama-cpp-python"),
        "gguf_file": gguf.name,
        "gguf_sha256": gguf_sha256 or sha256_file(gguf),
        "config_hash": config_hash(config),
        "config": config,
        "seed": int(seed),
        "bee_version": _pkg_version("bharatedge-eval"),
        "python": platform.python_version(),
        "platform": platform.platform(),
    }
    if extra:
        clash = set(extra) & set(header)
        if clash:
            raise ValueError(f"extra keys collide with header fields: {sorted(clash)}")
        header.update(extra)
    return header


def write_run_header(fh: TextIO, header: dict[str, Any]) -> None:
    """Write ``header`` as one JSON line. Must be the first line of a run's JSONL file."""
    if fh.tell() != 0:
        raise ValueError("run header must be the first line of the JSONL file")
    fh.write(json.dumps(header, ensure_ascii=False, sort_keys=True) + "\n")


def read_run_header(path: str | Path) -> dict[str, Any]:
    """Read and validate the header line of a run's JSONL file."""
    with open(path, encoding="utf-8") as f:
        header = json.loads(f.readline())
    required = {"llama_cpp_commit", "gguf_sha256", "config_hash", "seed"}
    missing = required - header.keys()
    if header.get("record") != "header" or missing:
        raise ValueError(f"invalid run header in {path}; missing {sorted(missing)}")
    return header
