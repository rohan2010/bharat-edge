#!/usr/bin/env bash
# Download a Hugging Face model, convert it to a BF16 GGUF, hash it, and delete
# the safetensors. Idempotent: if the GGUF and its .sha256 already exist and
# match, nothing is downloaded.
#
# Usage: scripts/fetch_model.sh <hf_repo> <short_name> [revision]
#   e.g. scripts/fetch_model.sh Qwen/Qwen3-0.6B qwen3-0.6b
#
# Output:  models/<short_name>/<short_name>-BF16.gguf
#          models/<short_name>/<short_name>-BF16.gguf.sha256
#          models/<short_name>/SOURCE.txt   (repo, HF revision, llama.cpp commit, sha256)
#
# Env:     MIN_FREE_GB  (default 6)  abort if free disk would drop below this
#          KEEP_STAGING=1             keep downloaded safetensors (debug only)
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <hf_repo> <short_name> [revision]" >&2
  exit 2
fi
REPO="$1"; SHORT="$2"; REV_IN="${3:-main}"
MIN_FREE_GB="${MIN_FREE_GB:-6}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LLAMA_DIR="$ROOT/third_party/llama.cpp"
PY="$LLAMA_DIR/.venv/bin/python"
OUT_DIR="$ROOT/models/$SHORT"
GGUF="$OUT_DIR/$SHORT-BF16.gguf"
SHA_FILE="$GGUF.sha256"
STAGE="$ROOT/models/.staging/$SHORT"

[[ -x "$PY" ]] || { echo "ERROR: conversion venv missing; run scripts/build_llamacpp.sh first" >&2; exit 1; }
command -v hf >/dev/null || { echo "ERROR: 'hf' CLI not found (pip install -U huggingface_hub)" >&2; exit 1; }

free_kb() { df -Pk "$ROOT" | awk 'NR==2 {print $4}'; }
gb() { awk -v k="$1" 'BEGIN { printf "%.1f", k/1048576 }'; }

# ---- Idempotency ----------------------------------------------------------
if [[ -f "$GGUF" && -f "$SHA_FILE" ]]; then
  echo "[$SHORT] $GGUF exists; verifying sha256..."
  if (cd "$OUT_DIR" && shasum -a 256 -c "$(basename "$SHA_FILE")" >/dev/null); then
    echo "[$SHORT] OK, nothing to do: $(cut -d' ' -f1 "$SHA_FILE")"
    exit 0
  fi
  echo "[$SHORT] sha256 mismatch; re-creating" >&2
  rm -f "$GGUF" "$SHA_FILE"
fi

# Keep every HF byte inside the staging dir (no ~/.cache copies); the auth
# token is still read from the default HF_HOME, so gated repos work after
# `hf auth login`.
export HF_HUB_CACHE="$STAGE/.hf-cache"
export HF_XET_CACHE="$STAGE/.xet-cache"
export HF_XET_CHUNK_CACHE_SIZE_BYTES=0
export HF_HUB_DISABLE_TELEMETRY=1

INCLUDE=(--include "*.safetensors" "*.safetensors.index.json" "config.json" "generation_config.json"
         "tokenizer.json" "tokenizer_config.json" "tokenizer.model" "special_tokens_map.json"
         "vocab.json" "merges.txt" "added_tokens.json" "chat_template.jinja" "chat_template.json")
EXCLUDE=(--exclude "original/*")

# ---- Resolve revision + size, check access and disk -----------------------
INFO="$("$PY" -I - "$REPO" "$REV_IN" <<'PYEOF'
import sys
from huggingface_hub import HfApi
from huggingface_hub.utils import GatedRepoError, RepositoryNotFoundError, HfHubHTTPError
repo, rev = sys.argv[1], sys.argv[2]
try:
    info = HfApi().model_info(repo, revision=rev, files_metadata=True)
except GatedRepoError:
    print("GATED"); sys.exit(0)
except RepositoryNotFoundError:
    print("NOTFOUND"); sys.exit(0)
except HfHubHTTPError as e:
    print("HTTPERR", str(e).splitlines()[0]); sys.exit(0)
size = sum((s.size or 0) for s in info.siblings if s.rfilename.endswith(".safetensors")
           and not s.rfilename.startswith("original/"))
print(info.sha, size, "gated" if info.gated else "open")
PYEOF
)"
case "$INFO" in
  GATED*|NOTFOUND*|HTTPERR*)
    echo "ERROR: cannot access $REPO ($INFO)." >&2
    echo "  For gated models: run 'hf auth login' and accept the licence at https://huggingface.co/$REPO" >&2
    exit 1;;
esac
read -r REV ST_BYTES GATED <<<"$INFO"
[[ "$ST_BYTES" -gt 0 ]] || { echo "ERROR: no safetensors found in $REPO@$REV" >&2; exit 1; }

NEED_KB=$(( ST_BYTES * 2 / 1024 + 262144 ))       # safetensors + BF16 GGUF + 256 MB slack
FREE_KB=$(free_kb)
echo "[$SHORT] $REPO @ $REV ($GATED); safetensors $(gb $((ST_BYTES/1024))) GB; peak need ~$(gb $NEED_KB) GB; free $(gb $FREE_KB) GB"
if (( FREE_KB - NEED_KB < MIN_FREE_GB * 1048576 )); then
  echo "ERROR: free disk would drop below ${MIN_FREE_GB} GB (free $(gb $FREE_KB) GB, need $(gb $NEED_KB) GB). Aborting." >&2
  exit 1
fi

cleanup() {
  if [[ "${KEEP_STAGING:-0}" != "1" && -d "$STAGE" ]]; then
    rm -rf "$STAGE"
    rmdir "$ROOT/models/.staging" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# ---- Download -------------------------------------------------------------
mkdir -p "$STAGE/src" "$OUT_DIR"
hf download "$REPO" --revision "$REV" --local-dir "$STAGE/src" "${INCLUDE[@]}" "${EXCLUDE[@]}"

# ---- Convert --------------------------------------------------------------
echo "[$SHORT] free before convert: $(gb "$(free_kb)") GB"
TMP_GGUF="$GGUF.partial"
"$PY" "$LLAMA_DIR/convert_hf_to_gguf.py" "$STAGE/src" --outtype bf16 --outfile "$TMP_GGUF"
mv "$TMP_GGUF" "$GGUF"

# ---- Hash + provenance ----------------------------------------------------
(cd "$OUT_DIR" && shasum -a 256 "$(basename "$GGUF")" > "$(basename "$SHA_FILE")")
SHA="$(cut -d' ' -f1 "$SHA_FILE")"
cat > "$OUT_DIR/SOURCE.txt" <<EOF
hf_repo: $REPO
hf_revision: $REV
gguf: $(basename "$GGUF")
outtype: bf16
sha256: $SHA
bytes: $(stat -f %z "$GGUF")
llama_cpp_commit: $(git -C "$LLAMA_DIR" rev-parse HEAD)
created_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF

cleanup
echo "[$SHORT] done: $GGUF"
echo "[$SHORT] sha256 $SHA  size $(du -h "$GGUF" | cut -f1)  free now $(gb "$(free_kb)") GB"
