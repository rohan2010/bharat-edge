# BharatEdge-Eval

**Does shrinking a small language model to fit a budget phone hurt Hindi, Hinglish and other Indic users more than English users? And can a cheap fix recover what they lose?**

Most people will meet AI through a compressed model. To fit a 4 GB phone, a model has to be quantized to 4 bits or fewer. Quantization is normally calibrated on English text and checked with English metrics. Published work shows that non-Latin scripts lose the most, that automatic scores hide much of the loss, and that safety can degrade while perplexity looks fine. No study has measured all of this together for Indic and code-mixed (Hinglish) input on models small enough for low-end phones. BharatEdge-Eval does that, then tests whether multilingual calibration recovers the loss at zero inference cost.

The full write-up, literature review and protocol are in [`docs/BharatEdge-Eval Project Write-up and Literature Review.md`](docs/BharatEdge-Eval%20Project%20Write-up%20and%20Literature%20Review.md).

## What we measure

| | |
| --- | --- |
| **Models** (all under 2B) | Gemma 3 1B IT, Qwen3 1.7B, Llama 3.2 1B Instruct, plus Qwen3 0.6B as a size check |
| **Builds** | BF16 (reference), Q8_0, Q6_K, Q4_K_M, Q3_K_M, plus the most-downloaded community Q4 = 24 configurations. 8 recalibrated builds are added for H4 |
| **Languages** | English (control), Hindi (Devanagari), romanized Hinglish, Bengali (held out until the analysis code is frozen) |
| **Tasks** | Belebele reading comprehension (log-likelihood, no judge), short generation (judged), harmful requests and over-refusal (judged), and a comprehension probe on every safety item |
| **Runtime** | llama.cpp + GGUF only, on an Apple-silicon Mac (Metal), plus a feasibility run on a 4 GB Android phone |

The main metric is the relative loss at precision *q* versus BF16, Δ = (S_BF16 − S_q) / S_BF16, and the gap to English, G = Δ_language − Δ_English.

### Hypotheses

1. **H1, gap amplification.** At 4-bit, Hindi and Hinglish lose more than 1.5× what English loses, in at least 2 of 3 model families.
2. **H2, hidden safety loss.** Refusal of direct harmful prompts stays flat while judged harm in open-ended Hindi or Hinglish answers rises by more than 5 points. Items the model didn't understand are excluded.
3. **H3, value drift.** The distribution of Value Imprint categories in answers shifts more in Hindi than in English.
4. **H4, calibration fix.** Adding Hindi, Hinglish and safety text to llama.cpp's importance-matrix calibration recovers at least a third of the H1 gap.

### Gates

- **Gate 1 (week 1):** gap amplification above 1.5 for at least one language at 4-bit on at least two models. If not, the project stops.
- **Gate 2 (week 2):** an LLM judge agrees with a native speaker on at least 80% of 200 Hindi and Hinglish items. If not, judged results are reported as exploratory only.
- **Gate 3 (week 4):** multilingual calibration recovers a measurable share of the loss. If not, the measurement is published as a negative result.

## Status

| Milestone | State |
| --- | --- |
| 1. Setup: llama.cpp, environment, 4 BF16 models answering English and Hindi | **Done** (2026-10-15) |
| 2. Quantize all builds, freeze task data | Not started |
| 3–9. Harness, pilot, judges, full grid, calibration fix, phone, release | Not started |

Details, hashes and answers are in [`docs/setup-log.md`](docs/setup-log.md). Dataset sources and licences are in [`docs/data-availability.md`](docs/data-availability.md).

## Setup

You need macOS on Apple silicon, Xcode command-line tools, Homebrew, and [uv](https://docs.astral.sh/uv/). Plan for about 40 GB of free disk; an external SSD for `models/` works well (see below).

### 1. Python environment

```bash
uv python install 3.11.14                 # use uv's Python, NOT the python.org installer (see note)
CMAKE_ARGS="-DGGML_METAL=on" uv sync      # llama-cpp-python compiles from source with Metal
uv run python -c "import llama_cpp; print(llama_cpp.__version__, llama_cpp.llama_supports_gpu_offload())"   # → 0.3.36 True
```

**Note on Python.** The python.org Python 3.11 installer is built against the macOS 12.1 SDK. Under it, Metal compiles GPU shaders at a language version below 3.1. llama.cpp then disables every BF16 kernel, and BF16 models crash with `kernel not found ... bf16`. `pyproject.toml` therefore sets `python-preference = "only-managed"`.

If you prefer pip, a pinned [`requirements.txt`](requirements.txt) is exported from `uv.lock`. Use it with a uv-managed or Homebrew Python 3.11:

```bash
CMAKE_ARGS="-DGGML_METAL=on" pip install -r requirements.txt && pip install -e . pytest ruff
```

If llama-cpp-python was ever built without Metal, rebuild it with `CMAKE_ARGS="-DGGML_METAL=on" uv sync --reinstall-package llama-cpp-python`.

### 2. llama.cpp (quantization tools)

```bash
brew install cmake
scripts/build_llamacpp.sh      # clones into third_party/llama.cpp at a pinned commit, builds with Metal
```

This also creates `third_party/llama.cpp/.venv`, which is only for the HF → GGUF conversion script.

### 3. Models

Gemma and Llama are gated. Accept their licences on Hugging Face first, then log in:

- https://huggingface.co/google/gemma-3-1b-it: click "Acknowledge license"; access is instant.
- https://huggingface.co/meta-llama/Llama-3.2-1B-Instruct: fill in the form; Meta approves it manually.
- `hf auth login` with a **Read** token. A fine-grained token must have "read access to public gated repos" enabled.

```bash
scripts/fetch_model.sh Qwen/Qwen3-0.6B                  qwen3-0.6b
scripts/fetch_model.sh Qwen/Qwen3-1.7B                  qwen3-1.7b
scripts/fetch_model.sh google/gemma-3-1b-it             gemma-3-1b-it
scripts/fetch_model.sh meta-llama/Llama-3.2-1B-Instruct llama-3.2-1b-instruct
```

Each call downloads the weights and converts them to `models/<name>/<name>-BF16.gguf`. It then writes the sha256 and a `SOURCE.txt` (HF revision, llama.cpp commit) and deletes the downloaded weights. It aborts if free disk would fall below `MIN_FREE_GB` (default 6).

**Keeping models on an external SSD.** Only `models/` needs to move; code, configs and results stay in the repo. Format the drive as APFS and use an NVMe drive over USB-C or Thunderbolt. Then:

```bash
mkdir -p /Volumes/<SSD>/bharatedge/models
mv models/* /Volumes/<SSD>/bharatedge/models/ && rmdir models
ln -s /Volumes/<SSD>/bharatedge/models models
```

llama.cpp reads each model into memory once per run, so the SSD adds only a few seconds of load time. Every run checks the file hash, so a missing or changed model fails loudly rather than silently.

### 4. Check it works

```bash
uv run ruff check .
uv run pytest
third_party/llama.cpp/build/bin/llama-cli -m models/qwen3-1.7b/qwen3-1.7b-BF16.gguf \
  -st -rea off -c 2048 -n 64 --temp 0 -ngl 99 -p "भारत की राजधानी क्या है? एक वाक्य में उत्तर दें।"
```

Always pass a context size such as `-c 2048` to the llama.cpp tools. The default is about 40k tokens, which allocates a 4.5 GB cache and pushes the Mac into swap.

## Repository layout

```text
configs/    models.yaml, precisions.yaml, tasks.yaml, grid.yaml (full, smoke, stability, recalibrated)
data/       download scripts only; raw data is never committed
docs/       write-up, setup log, data availability
scripts/    build_llamacpp.sh, fetch_model.sh
src/bee/    quantize, runner, tasks/, judges/, values, stats, report, provenance
phone/      Termux build notes and timing script
results/    one JSONL per run (gitignored, summaries included, until publication)
tests/      unit tests and the smoke grid
models/     GGUF files (gitignored; may be a symlink to an SSD)
third_party/llama.cpp   pinned llama.cpp build (gitignored)
```

## Ground rules

- Every run records the llama.cpp commit, GGUF sha256, config hash and seed in its JSONL header (`bee.provenance`).
- Run the smoke grid (1 model, 2 precisions, 20 items per task) before any full run.
- Task item sets and prompt templates are frozen after Milestone 2; any change needs a new version number.
- Harmful model outputs are never printed, committed or released. Only aggregate scores are published, and harmful prompts only through gated access.
- Surprising results are re-run before anything is written about them.

Rules for coding agents are in [`CLAUDE.md`](CLAUDE.md).
