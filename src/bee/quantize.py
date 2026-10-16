"""GGUF conversion, quantization and importance-matrix (imatrix) calibration.

Wraps llama.cpp's ``convert_hf_to_gguf.py``, ``llama-quantize`` and ``llama-imatrix`` from the
pinned checkout in ``third_party/llama.cpp``. Produces the BF16 reference GGUF, the Q8_0, Q6_K,
Q4_K_M and Q3_K_M builds, and (Milestone 7, H4) multilingual/safety-calibrated Q4_K_M and Q3_K_M
builds. Every output file's SHA-256 is recorded.

Every build is quantized straight from the BF16 file (never from another quantized build), so
each precision differs from the reference by its own error only. ``llama-quantize`` output is
byte-identical across thread counts (checked 2026-10-16: qwen3-0.6b Q4_K_M at 10 and 4 threads),
so any build can be re-made from the BF16 file and the llama.cpp commit and checked by hash.

Disk is tight, so ``run`` handles one build at a time: quantize, perplexity sanity check, push to
the private HF store (``bee.store``), delete the local GGUF. Builds already in the ledger are
skipped, so an interrupted run resumes where it stopped.

    uv run python -m bee.quantize run qwen3-0.6b --keep Q4_K_M   # smoke grid needs Q4_K_M
    uv run python -m bee.quantize run qwen3-1.7b --precisions Q8_0 Q6_K
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bee import store
from bee.provenance import DEFAULT_LLAMA_CPP_DIR, llama_cpp_commit, sha256_file

PRECISIONS = ("Q8_0", "Q6_K", "Q4_K_M", "Q3_K_M")
BIN_DIR = DEFAULT_LLAMA_CPP_DIR / "build/bin"
SANITY_DIR = Path("configs/sanity")
SANITY_LANGS = ("en", "hi", "hi-Latn")
# Sanity gate, not a result: a broken build gives perplexity in the thousands or NaN. The worst
# healthy ratio seen was 1.65 (qwen3-0.6b Q3_K_M, hi-Latn), on the smallest model.
MAX_PPL_RATIO = 3.0
_PPL_RE = re.compile(r"Final estimate: PPL = ([0-9.]+|nan|inf)")


def build_name(model_key: str, precision: str) -> str:
    return f"{model_key}-{precision}.gguf"


def record_path(gguf: Path) -> Path:
    return gguf.with_name(gguf.name + ".json")


def read_source(model_dir: Path) -> dict[str, str]:
    """Parse ``models/<key>/SOURCE.txt`` (``key: value`` lines) written by fetch_model.sh."""
    lines = (model_dir / "SOURCE.txt").read_text().splitlines()
    return dict(line.split(": ", 1) for line in lines if ": " in line)


def convert_to_bf16_gguf(hf_model_dir: Path, out_path: Path) -> Path:
    """Convert a Hugging Face checkpoint to a BF16 GGUF file (done by scripts/fetch_model.sh)."""
    raise NotImplementedError


def quantize(
    bf16_gguf: Path,
    precision: str,
    out_path: Path,
    imatrix: Path | None = None,
    *,
    bf16_sha256: str,
    threads: int | None = None,
) -> dict[str, Any]:
    """Quantize a BF16 GGUF to ``precision`` (e.g. "Q4_K_M"), optionally with an imatrix.

    Writes the GGUF and a build record (``<out>.json``) next to it, and returns the record.
    """
    cmd = [str(BIN_DIR / "llama-quantize")]
    if imatrix is not None:
        cmd += ["--imatrix", str(imatrix)]
    cmd += [str(bf16_gguf), str(out_path), precision]
    if threads is not None:
        cmd.append(str(threads))
    start = time.monotonic()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    secs = time.monotonic() - start
    if proc.returncode != 0:
        out_path.unlink(missing_ok=True)
        raise RuntimeError(f"llama-quantize failed ({proc.returncode}):\n{proc.stderr[-2000:]}")
    record = {
        "file": out_path.name,
        "precision": precision,
        "sha256": sha256_file(out_path),
        "bytes": out_path.stat().st_size,
        "source_file": bf16_gguf.name,
        "source_sha256": bf16_sha256,
        "imatrix_file": imatrix.name if imatrix else None,
        "imatrix_sha256": sha256_file(imatrix) if imatrix else None,
        "llama_cpp_commit": llama_cpp_commit(),
        "command": ["llama-quantize", *cmd[1:]],
        "quantize_seconds": round(secs, 2),
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    write_record(out_path, record)
    return record


def write_record(gguf: Path, record: dict[str, Any]) -> None:
    record_path(gguf).write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")


def build_imatrix(bf16_gguf: Path, calibration_text: Path, out_path: Path) -> Path:
    """Compute an importance matrix from a calibration corpus with ``llama-imatrix``."""
    raise NotImplementedError


def parse_ppl(log: str) -> float:
    m = _PPL_RE.search(log)
    if not m:
        raise RuntimeError(f"no perplexity estimate in llama-perplexity output:\n{log[-2000:]}")
    return float(m.group(1))


def perplexity(gguf: Path, text: Path, n_ctx: int = 128) -> float:
    """Perplexity of ``gguf`` on a short fixed text (sanity only; ~1 s with Metal)."""
    cmd = [str(BIN_DIR / "llama-perplexity"), "-m", str(gguf), "-f", str(text)]
    cmd += ["-c", str(n_ctx), "-b", str(n_ctx), "-ngl", "99"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"llama-perplexity failed ({proc.returncode}):\n{proc.stderr[-2000:]}")
    return parse_ppl(proc.stderr + proc.stdout)


def check_sanity(ppl: dict[str, float], reference: dict[str, float]) -> dict[str, Any]:
    """Compare per-language perplexities to BF16; raise if any is non-finite or too high."""
    ratios = {lang: ppl[lang] / reference[lang] for lang in reference}
    bad = {lang: r for lang, r in ratios.items() if not math.isfinite(r) or r > MAX_PPL_RATIO}
    if bad:
        raise ValueError(f"sanity check failed: PPL ratio vs BF16 {bad} (max {MAX_PPL_RATIO})")
    return {"ppl": ppl, "ppl_bf16": reference, "ratio": {k: round(v, 3) for k, v in ratios.items()}}


def sanity_ppl(gguf: Path) -> dict[str, float]:
    return {lang: perplexity(gguf, SANITY_DIR / f"{lang}.txt") for lang in SANITY_LANGS}


def run_model(
    model_key: str,
    precisions: list[str],
    *,
    push: bool = True,
    keep: frozenset[str] = frozenset(),
    threads: int | None = None,
) -> None:
    """Quantize, check, push and delete each build of one model, skipping stored builds."""
    model_dir = store.MODELS_DIR / model_key
    bf16 = model_dir / build_name(model_key, "BF16")
    source = read_source(model_dir)
    print(f"{model_key}: verifying {bf16.name} against SOURCE.txt ...")
    store.verify(bf16, source["sha256"])
    if source["llama_cpp_commit"] != llama_cpp_commit():
        print(f"  note: BF16 converted at llama.cpp {source['llama_cpp_commit'][:8]}")
    stored = store.load_ledger()["models"].get(model_key, {}).get("files", {})
    todo = [p for p in precisions if build_name(model_key, p) not in stored]
    for p in precisions:
        if p not in todo:
            print(f"  {p}: already stored, skipping")
    if not todo:
        return
    reference = sanity_ppl(bf16)
    print(f"  BF16 sanity PPL {reference}")
    for p in todo:
        out = model_dir / build_name(model_key, p)
        record = quantize(bf16, p, out, bf16_sha256=source["sha256"], threads=threads)
        record["sanity"] = check_sanity(sanity_ppl(out), reference)
        write_record(out, record)
        gb = record["bytes"] / 1e9
        print(
            f"  {p}: {gb:.2f} GB in {record['quantize_seconds']} s, "
            f"PPL ratio {record['sanity']['ratio']}"
        )
        if not push:
            continue
        store.push_files(
            model_key,
            [out.name, record_path(out).name],
            expected_sha256={out.name: record["sha256"]},
        )
        if p in keep:
            print(f"  {p}: kept locally")
        else:
            out.unlink()
            print(f"  {p}: deleted locally (record kept: {record_path(out).name})")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="bee.quantize", description="Quantize GGUF builds.")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="quantize -> sanity check -> push -> delete, one model")
    r.add_argument("model")
    r.add_argument("--precisions", nargs="+", default=list(PRECISIONS), choices=PRECISIONS)
    r.add_argument(
        "--keep",
        nargs="*",
        default=[],
        choices=PRECISIONS,
        help="precisions to keep on disk after pushing",
    )
    r.add_argument("--no-push", action="store_true", help="build and check only")
    r.add_argument("--threads", type=int)
    args = p.parse_args(argv)
    run_model(
        args.model,
        args.precisions,
        push=not args.no_push,
        keep=frozenset(args.keep),
        threads=args.threads,
    )


if __name__ == "__main__":
    main()
