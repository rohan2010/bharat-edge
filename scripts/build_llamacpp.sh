#!/usr/bin/env bash
# Reproducible llama.cpp build for BharatEdge-Eval (Apple Silicon, Metal).
#
# Pins llama.cpp to an exact commit, builds with Metal, and creates the
# conversion venv used by convert_hf_to_gguf.py. Idempotent: re-running skips
# the clone, checkout, build and venv steps that are already done.
#
# Usage: scripts/build_llamacpp.sh            # build pinned commit
#        LLAMACPP_FORCE_REBUILD=1 scripts/build_llamacpp.sh
set -euo pipefail

# ---- Pinned version -------------------------------------------------------
LLAMACPP_REPO="https://github.com/ggml-org/llama.cpp"
LLAMACPP_TAG="v0.6.0"                                        # latest stable release (2026-10-05)
LLAMACPP_COMMIT="d81235049384534c167caea52b85a694f6103d14"
CMAKE_FLAGS=(-DGGML_METAL=ON -DCMAKE_BUILD_TYPE=Release)
PYTHON_VERSION="3.11"
# ---------------------------------------------------------------------------

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LLAMA_DIR="$ROOT/third_party/llama.cpp"
BIN_DIR="$LLAMA_DIR/build/bin"
VENV="$LLAMA_DIR/.venv"

need() { command -v "$1" >/dev/null 2>&1 || { echo "ERROR: '$1' not found. $2" >&2; exit 1; }; }
need git ""
need cmake "Install with: brew install cmake"
need uv "Install with: brew install uv"

# 1. Clone + pin
if [[ ! -d "$LLAMA_DIR/.git" ]]; then
  mkdir -p "$ROOT/third_party"
  git clone "$LLAMACPP_REPO" "$LLAMA_DIR"
fi
current="$(git -C "$LLAMA_DIR" rev-parse HEAD)"
if [[ "$current" != "$LLAMACPP_COMMIT" ]]; then
  git -C "$LLAMA_DIR" fetch --tags origin
  git -C "$LLAMA_DIR" checkout --quiet "$LLAMACPP_COMMIT"
fi
echo "llama.cpp at $(git -C "$LLAMA_DIR" rev-parse HEAD) ($(git -C "$LLAMA_DIR" describe --tags))"

# 2. Build (skipped if binaries exist for this commit)
STAMP="$LLAMA_DIR/build/.bee_build_commit"
if [[ "${LLAMACPP_FORCE_REBUILD:-0}" == "1" || ! -f "$STAMP" || "$(cat "$STAMP")" != "$LLAMACPP_COMMIT" \
      || ! -x "$BIN_DIR/llama-quantize" ]]; then
  (cd "$LLAMA_DIR" && cmake -B build "${CMAKE_FLAGS[@]}" && cmake --build build -j "$(sysctl -n hw.ncpu)")
  echo "$LLAMACPP_COMMIT" > "$STAMP"
else
  echo "Build up to date (stamp $STAMP)"
fi

for b in llama-cli llama-completion llama-quantize llama-imatrix llama-perplexity; do
  if [[ -x "$BIN_DIR/$b" ]]; then echo "  found  $b"; else echo "  missing $b"; fi
done
for b in llama-quantize llama-imatrix; do
  [[ -x "$BIN_DIR/$b" ]] || { echo "ERROR: required binary $b missing" >&2; exit 1; }
done

# 3. Conversion venv (CPU-only torch, lean)
if [[ ! -x "$VENV/bin/python" ]] || ! "$VENV/bin/python" -c "import gguf, torch, transformers" 2>/dev/null; then
  uv venv --python "$PYTHON_VERSION" "$VENV"
  # requirements-convert_hf_to_gguf.txt pulls torch from the CPU index on non-Linux;
  # macOS wheels from PyPI are CPU/MPS anyway, so this stays lean.
  uv pip install --python "$VENV/bin/python" \
    --index-strategy unsafe-best-match \
    -r "$LLAMA_DIR/requirements/requirements-convert_hf_to_gguf.txt"
  # Use the gguf-py shipped with this exact commit, not the PyPI release.
  uv pip install --python "$VENV/bin/python" -e "$LLAMA_DIR/gguf-py"
fi
"$VENV/bin/python" -c "import torch, transformers, gguf, sys; print('venv ok: python', sys.version.split()[0], 'torch', torch.__version__, 'transformers', transformers.__version__)"
