# Setup log (Milestone 1)

2026-10-15 · Apple M4, 16 GB, macOS (Darwin 25.5.0)

## llama.cpp

- Tag `v0.6.0`, commit `d81235049384534c167caea52b85a694f6103d14`, in `third_party/llama.cpp`.
- Built by `scripts/build_llamacpp.sh`: `-DGGML_METAL=ON -DCMAKE_BUILD_TYPE=Release`, shared libs, embedded Metal library.
- Binaries used: `llama-cli`, `llama-completion`, `llama-quantize`, `llama-imatrix` (in `build/bin`).
- Conversion venv: `third_party/llama.cpp/.venv` (CPU torch 2.11) for `convert_hf_to_gguf.py`.

## Python environment

- uv-managed CPython **3.11.14** (`.python-version`, `python-preference = "only-managed"`).
- llama-cpp-python 0.3.36, built from source with Metal; its bundled llama.cpp is commit `0c1e570` (2026-10-01), which differs from the one above. Run headers record both.

**Pitfall found:** the python.org Python 3.11.9 is linked against the macOS 12.1 SDK. Metal then compiles shaders below language version 3.1, and llama.cpp's `kernels/common.h` drops `GGML_METAL_HAS_BF16`. Every BF16 GPU kernel goes missing, and BF16 GGUFs abort with `kernel not found ... kernel_mul_mv_bf16_f32_4`. The llama.cpp command-line tools are unaffected. The fix is a uv-managed Python (SDK 15.5).

## Models (BF16 GGUF)

Made with `scripts/fetch_model.sh <repo> <short>`, which downloads, converts with `--outtype bf16`, records the sha256 and deletes the safetensors. Provenance is in `models/<short>/SOURCE.txt`.

| Model | HF revision | Size | sha256 |
| --- | --- | --- | --- |
| Qwen/Qwen3-0.6B | `c1899de2` | 1.51 GB | `f2a9913c3c3cdcd434df40da881411ca4908ba8929632ecd6cfe5ed8a9f375ff` |
| Qwen/Qwen3-1.7B | `70d244cc` | 4.07 GB | `4ebae09b2cb9350f1af2eee5457c16b071f5eec302946d4bc5f96de75b01b358` |
| google/gemma-3-1b-it | `dcc83ea8` | 2.01 GB | `87437b8f8f512cf83a7a6f0287e71698973904094c8aa97e38dab1c3f55a4738` |
| meta-llama/Llama-3.2-1B-Instruct | `92131767` | 2.47 GB | `70e662f4681e55e12a6330e24121b8e9b5d87c0f15e0607c11e7d3cb9129c71a` |

## Acceptance check

Greedy (temp 0), full Metal offload, Qwen3 thinking off (`-rea off` on the CLI, `/no_think` in Python). Same answers from `llama-cli` and llama-cpp-python.

| Model | English: "What is the capital of France? Answer in one sentence." | Hindi: "भारत की राजधानी क्या है? एक वाक्य में उत्तर दें।" | Decode speed (CLI) |
| --- | --- | --- | --- |
| qwen3-0.6b | The capital of France is Paris. | भारत की राजधानी बिहार राज्य की राजमारी है। (**wrong**: says the capital is in Bihar) | ~74 tok/s |
| qwen3-1.7b | The capital of France is Paris. | भारत की राजधानी नई दिल्ली है। | ~28 tok/s |
| gemma-3-1b-it | The capital of France is Paris. | भारत की राजधानी नई दिल्ली है। | (Python only) |
| llama-3.2-1b-instruct | The capital of France is Paris. | भारत की राजधानी नई दिल्ली है। | (Python only) |

Python also checked: load time is 0.2 s (0.6B) and 2.9 s (1.7B), and top-k log-probs work (" Paris" −0.42 / −0.64).

## Result

**Milestone 1 passed (2026-10-15).** All 4 BF16 models answer the English and Hindi prompts, and all sha256 hashes verify.

## Disk

About 15 GB free after all four models (the user freed space before the Llama download). Gemma was fetched with `MIN_FREE_GB=3` while space was short. The 24 quantized builds need roughly 15–20 GB more, so move `models/` to the T7 Shield SSD (exFAT, 763 GB free) before Milestone 2; see README. Swap was using ~3.9 GB (5 GB of swap files) after CLI runs with the default 40k context. Always pass `-c 2048`. Milestone 2 needs roughly 15–20 GB more for the quantized builds.
