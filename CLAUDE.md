# BharatEdge-Eval

Does GGUF quantization of sub-2B models hurt Indic languages more than English?
Models: Gemma 3 1B it, Qwen3 1.7B, Llama 3.2 1B Instruct (+ Qwen3 0.6B size check).
Builds: BF16 (reference), Q8_0, Q6_K, Q4_K_M, Q3_K_M, community Q4 = 24 configs, + 8 imatrix-recalibrated (H4).
Languages: en (control), hi (Devanagari), hi-Latn (Hinglish). Held-out Bengali/Tamil dropped for now (2026-10-16).
Tasks: Belebele MC (log-likelihood), short generation, harmful requests, over-refusal, comprehension probe.
Primary metric: relative loss Δ = (S_BF16 − S_q)/S_BF16 and gap G = Δ_L − Δ_en (ratio only if Δ_en > 1 pt).
Greedy decoding, fixed item order. Mac (M4, Metal) via llama.cpp; one 4 GB Android phone via Termux.
Full write-up: `docs/BharatEdge-Eval Project Write-up and Literature Review.md`.

## Rules (non-negotiable)

1. Never change a task's item set or prompt template after Milestone 2 without a new version number (`version` in `configs/tasks.yaml`).
2. Every run records the llama.cpp commit, GGUF file hash, config hash and seed in its JSONL header (use `bee.provenance.build_run_header`).
3. Run the smoke grid (1 model, 2 precisions, 20 items per task; `grids.smoke`) before any full run.
4. Never print or commit harmful model outputs; store them only in the gitignored `results/` folder.
5. If a result looks surprising, re-run that cell before writing anything about it.

## Milestones (stop at each acceptance check)

1. Setup — llama.cpp with Metal, env, 4 models. Done: each BF16 model answers one English and one Hindi prompt from the CLI.
2. Quantize + freeze data — 24 GGUF builds; task data downloaded and versioned. Done: file hashes recorded and smoke grid passes.
3. MC harness — Belebele log-likelihood. Done: BF16 English accuracy per model within 3 pts of published figures, or gap explained.
4. Pilot + Gate 1 — full Belebele grid. Done: loss chart exists, Gate 1 decided.
5. Judges + Gate 2 — generation, safety, over-refusal, probe; two judges; 200 native-labelled items. Done: agreement reported (≥80% to pass), Gate 2 decided.
6. Full grid + value drift — all 24 configs, all tasks, Value Imprint KL. Done: every cell has a result with a CI.
7. Calibration fix + Gate 3 — multilingual/safety imatrix, re-quantize 8 builds, re-run. Done: H4 decided.
8. Phone feasibility — Termux on the 4 GB phone. Done: feasibility table complete.
9. Write-up + release. Done: someone else can reproduce one table from the README alone.

## Stack

Do: llama.cpp (`llama-quantize`, `llama-imatrix`) from `third_party/llama.cpp` at a recorded commit; llama-cpp-python (Metal build) for inference/log-probs; `huggingface_hub`; Python 3.11 + uv with `uv.lock`; YAML configs, one JSONL per run, DuckDB for analysis; NumPy/SciPy/pandas/Matplotlib (stats in `bee.stats`: 1,000-sample bootstrap 95% CI, paired permutation tests, Holm across languages); IndicGuard + local 8–12B 4-bit judge + free-tier API second opinion; PyTorch MPS only for the Value Imprint classifier; pytest + ruff + smoke grid; Kaggle only for large judge batches.

Don't: MLX or any second quantization format; PyTorch MPS for LLM inference; vLLM/TensorRT-LLM/bitsandbytes/AWQ/GPTQ/QAT; Docker for inference; Android emulators for speed/memory; W&B/MLflow; LangChain/LangGraph; paid frontier models as main judge (spot checks only); PEFT/TRL or any fine-tuning; models ≥3B.

## Commands

```bash
CMAKE_ARGS="-DGGML_METAL=on" uv sync      # llama-cpp-python must be built with Metal
uv run pytest
uv run ruff check .
uv run ruff format src tests
```

Layout: `src/bee/` (package), `configs/`, `tests/`, `data/` (scripts only; `data/raw/` gitignored), `phone/`, `results/` (gitignored, summaries too, until publication). Unpublished research docs, `configs/model_store.json` and `data/manifests/` are gitignored too; `uv run python data/backup.py push` backs them up to the private HF dataset repo, `third_party/` and `models/` gitignored. Python must be uv-managed 3.11.14 (python.org builds disable Metal BF16 kernels). llama.cpp CLI defaults to a 40k context (4.5 GB KV); always pass `-c 2048` or similar. Disk is tight (~20 GB free): don't install torch until the Value Imprint milestone; delete intermediate GGUFs you no longer need.
