# BharatEdge-Eval: data availability and licences (week-1 check)

Checked 2026-10-15 against the "Experimental protocol" data table and the "Datasets unavailable or licence-restricted" risk row. Sources: Hugging Face Hub metadata (`huggingface_hub` API and the datasets-server `/size`, `/statistics` and `/first-rows` endpoints, used anonymously), the GitHub API, arXiv pages and dataset cards. Full datasets were **not** downloaded. The only exception: a few IndicGenBench test JSONs, each under 4 MB, were fetched one at a time to count items and deleted straight away, because that repo has its dataset viewer turned off.

Language columns: **EN** = English, **HI** = Hindi (Devanagari), **HI-Latn** = romanized Hindi / Hinglish, **BN** = Bengali, **TA** = Tamil.
"Verified" means I checked it myself against the Hub or repo. "Paper" means it comes from the paper and I did not check it independently.

---

## 1. Reading comprehension: Belebele (target: 900 per language)

| Field | Finding |
| --- | --- |
| Source | HF `facebook/belebele`; GitHub `facebookresearch/belebele`; arXiv 2308.16884 |
| Licence | CC-BY-SA 4.0 for the eval data. The separate *training* set is mostly CC-BY-NC, and we do not use it |
| Gated | No |
| Configs / split | One config per language, with a single `test` split |
| EN | `eng_Latn`: 900 (verified) |
| HI | `hin_Deva`: 900 (verified) |
| HI-Latn | `hin_Latn`: 900 (verified). The card labels it "Hindi (Romanized)". This is transliterated standard Hindi, **not** natural code-mixed Hinglish. I did not verify whether the transliteration was done by humans or by a tool |
| BN | `ben_Beng`: 900; there is also `ben_Latn`: 900 (verified) |
| TA | `tam_Taml`: 900 (verified). There is **no** `tam_Latn` |
| Covers 900/lang? | **Yes, for every language**, fully parallel (same passages and questions) |

## 2. Short generation (target: 200 per language)

### 2a. IndicGenBench (Google; arXiv 2404.16816)

Four separate HF repos. None is gated, and the dataset viewer is disabled on all four. Each file wraps its items in `{"canary": ..., "examples": [...]}`. The canary string is a contamination marker, so raw items should not be re-published.

| Subset (HF ID) | Licence | Splits | EN | HI | BN | TA | 200/lang? |
| --- | --- | --- | --- | --- | --- | --- | --- |
| XQuAD-In `google/IndicGenBench_xquad_in` | CC-BY-SA 4.0 | train/dev/test | 1190 | 1190 | 1190 | 1190 | **Yes** (test counts verified; parallel across languages) |
| XorQA-In `google/IndicGenBench_xorqa_in` | MIT | train/dev/test | 539 | 539 | 539 | 538 | **Yes** (verified). The answers are in English plus a human-translated answer |
| Flores-In `google/IndicGenBench_flores_in` | CC-BY-SA 4.0 | dev/test (no train) | n/a (en is the source/target side) | 1012 en↔hi | 1012 en↔bn | 1012 en↔ta | **Yes** (verified) |
| CrossSum-In `google/IndicGenBench_crosssum_in` | **CC-BY-NC-SA 4.0** | train/dev/test | 500 | **481** | **155** | **315** | Hindi and Tamil: yes. **Bengali: no** (only 155 test items; dev would be needed to reach 200). The paper's "500 per language" is wrong for these languages |

No language has a romanized or Hinglish variant in IndicGenBench.

### 2b. Hinglish candidates

| Resource | Source | Licence | Gated | Released? | HI-Latn items | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Indi-RomCoM | arXiv 2606.30790 (Das, Parmar, Ramnath, Verma; 29 Jun 2026) | none stated | n/a | **No public data found.** No HF dataset, no GitHub link and no release statement in the paper HTML | Paper: 100 items per task × 3 code-mixing levels (25/50/75%), for each of HI, BN, GU, TA | 7 tasks: word analogy, question decomposition, GSM8K, paraphrase, sentiment, NLI, toxicity. Mostly classification/reasoning; only question decomposition and GSM8K are generative. **Cannot be used as of today** |
| CodeMixBench (Yang & Chai, EMNLP 2025) | HF `CodeMixBench/CodeMixBench`; GitHub `Jeromeyluck/CodeMixBench` | Apache-2.0 on the Hub card. The upstream corpora it re-packages may carry their own licences, which I did not check | No | Yes | `mt_hineng_eng` test: **942** (romanized Hinglish → English, with references; verified). Also `gsm8k_hineng` 1016, `truthfulqa_hineng` 757, `mmlu_hineng` 1024, `sa_hineng` 1261, `lid_hineng` 744, `ner_hineng` 314, `pos_hineng` 160 | Only `mt_hineng_eng` is real romanized Hinglish. The synthesized gsm8k/mmlu/truthfulqa sets are **Devanagari-mixed** Hindi-English, not romanized. Also has `mmlu_beneng` 1114, `mmlu_tameng` 1047, `mt_beneng_eng` 2000, `sa_beneng` 1000, `sa_tameng` 3049 |
| CodeMixBench (Sheokand & Sawant, arXiv 2505.05063) | HF `ColdSlim/CodeMixBench` | Apache-2.0 | No | Yes | `hindi-eng` config, splits `cmd0.6` / `cmd0.9`: 1140 each | This is BigCodeBench **code generation** with LLM-translated docstrings. Unsuitable for short NL generation, so don't confuse the two "CodeMixBench"s |

**Covers 200/lang?** EN, HI, BN and TA: yes, through XQuAD-In, Flores-In or XorQA-In. HI-Latn: yes in count (CodeMixBench `mt_hineng_eng`, 942), but the task is different (Hinglish→English MT), so the Hinglish column is **not task-matched** with the other three.

## 3. Harmful requests (target: 300 per language)

| Resource | Source | Licence | Gated | EN | HI | HI-Latn | BN | TA | 300/lang? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| IndicSafeEval | arXiv 2609.03781 (Mondal et al., Findings of EMNLP 2026); GitHub `MonSaikat/IndicSafeEval` | Paper CC-BY 4.0; **no licence file in the repo** | n/a | ? | Paper: yes | no | Paper: yes | **no** | **Blocked.** Paper: 7,200 persuasion-framed jailbreak prompts (10 categories × 6 persuasion strategies) across HI/BN/MR/PA, about 1,800 per language. **The data is not released.** The README describes `dataset/prompts.csv`, but the repo tree (checked through the GitHub API, last push 2026-09-04) holds only `Codes/Inference.py` and `README.md`, and nothing is on HF. **No Tamil.** These are persuasive *jailbreaks*, not plain harmful requests, so they are not like-for-like with MultiJail |
| MultiJail | HF `DAMO-NLP-SG/MultiJail`; GitHub `DAMO-NLP-SG/multilingual-safety-for-LLMs`; arXiv 2310.06474 | MIT | No | 315 | **no** | no | **315** (human-translated) | **no** | Yes for EN and BN (315 ≥ 300, parallel; a single CSV split `train`, with columns `en, zh, it, vi, ar, ko, th, bn, sw, jv`). No HI or TA |
| IndicSafe (alternative, not in the protocol) | HF `ppattnay/IndicSafe`; arXiv 2603.17915 | **CC-BY-NC 4.0** (data); code licensed separately | No | English source column | 500 | no | 500 | 500 | Split `benchmark`, 500 rows per language across 12 languages. Each language includes about 125 harmless-control and 45 tricky/ambiguous prompts, which leaves **about 330 harmful** per language (computed from category totals ÷ 12). **Yes** for HI/BN/TA, and parallel to an English source. Its control and ambiguous items could also help the over-refusal task |
| IndicGuard dataset (alternative) | HF `l3cube-pune/IndicGuard` | CC-BY-4.0 | No | yes | yes | no | yes | yes | Paper: 1,964 test items per language (prompt and response, safe and unsafe), translated with Google Translate from Nemotron-Safety-Guard-v3. Big enough, but **using it while also using IndicGuard as the judge is circular** (the judge was trained on its train split). Not recommended as the prompt source |

## 4. Over-refusal: XSTest (target: 150 per language)

| Field | Finding |
| --- | --- |
| Source | HF `Paul/XSTest` (author upload, `xstest_prompts.csv`, split `train`); GitHub `paul-rottger/xstest`; NAACL 2024. Mirrors: `walledai/XSTest` (gated "auto", meaning click-through), `natolambert/xstest-v2-copy` |
| Licence | CC-BY-4.0 |
| Gated | No (author repo) |
| Items | 450 = **250 safe** prompts (10 types × 25) + 200 unsafe contrasts (verified 450 rows) |
| Languages | **English only.** I found no Hindi, Bengali, Tamil or Hinglish version on HF (searched "xstest", "over-refusal", "or-bench"; only ko/pt/it/ru community translations exist) |
| Covers 150/lang? | EN: yes (250 safe ≥ 150). HI/HI-Latn/BN/TA: **only if we translate and native-check them, as the protocol plans** |

## 5. Comprehension probe

These are derived from the safety items ("one paraphrase question per safety item"), so there is no external dataset. Item counts follow whichever harmful-request source we pick.

## 6. Judge: IndicGuard (arXiv 2606.22841, L3Cube Pune)

| Field | Finding |
| --- | --- |
| Weights | HF `l3cube-pune/IndicGuard` (created 2026-06-21, about 427 downloads in the last 30 days). The weights **exist** |
| Form | A **LoRA adapter** (r=16, about 119 MB `adapter_model.safetensors`), not full weights. Base: `unsloth/gemma-3-4b-it-unsloth-bnb-4bit` (ungated mirror; Gemma licence). bitsandbytes 4-bit loading needs CUDA. On Mac or CPU, apply the adapter to `google/gemma-3-4b-it`, which is **gated** (accept the Gemma terms) |
| Licence | The adapter card says Apache-2.0, but the **Gemma Terms of Use still apply** through the base model. Training data is CC-BY-4.0 (`l3cube-pune/IndicGuard`) |
| Gated | Adapter: no. Official Gemma base: yes (manual) |
| Output | JSON: `User Safety` / `Response Safety` ∈ {safe, unsafe}, plus a list of categories from a 23-class AEGIS-2.0-style taxonomy. Classifies both prompts and responses |
| Languages | Paper and dataset: HI, BN, GU, MR, PA, TA, TE, KN, ML, UR + EN. The model card lists Odia in place of Urdu, an inconsistency. **BN and TA both covered.** **Romanized Hindi / Hinglish is not trained on or evaluated**, so its Hinglish verdicts need the second judge plus the human check |

## 7. Community Q4 GGUF builds (for the "community Q4" column)

HF `downloads` = last 30 days; "all-time" = `downloadsAllTime`. Snapshot taken 2026-10-15. None of these repos is gated. The base checkpoints `google/gemma-3-1b-it` and `meta-llama/Llama-3.2-1B-Instruct` are **gated (manual)**, under the Gemma terms and the Llama 3.2 Community License; the Qwen3 bases are Apache-2.0 and ungated. The official `Qwen/Qwen3-{0.6B,1.7B}-GGUF` repos contain **only Q8_0**, so they cannot supply a Q4.

| Base model | Most downloaded all-time (Q4 file present) | Most downloaded last 30 days | Other high-download Q4 repos |
| --- | --- | --- | --- |
| google/gemma-3-1b-it | `MaziyarPanahi/gemma-3-1b-it-GGUF`: 3.47M all-time / 108k 30d | `ggml-org/gemma-3-1b-it-GGUF`: 214k 30d / 966k all-time | `unsloth/gemma-3-1b-it-GGUF` (836k / 49k), `lmstudio-community/gemma-3-1b-it-GGUF` (325k / 76k) |
| Qwen/Qwen3-1.7B | `MaziyarPanahi/Qwen3-1.7B-GGUF`: 3.52M / 189k | `unsloth/Qwen3-1.7B-GGUF`: 203k / 919k | `ggml-org/Qwen3-1.7B-GGUF` (231k / 103k), `bartowski/Qwen_Qwen3-1.7B-GGUF` (36k 30d) |
| meta-llama/Llama-3.2-1B-Instruct | `MaziyarPanahi/Llama-3.2-1B-Instruct-GGUF`: 12.2M / 117k | `bartowski/Llama-3.2-1B-Instruct-GGUF`: 155k / 2.90M | `unsloth/...-GGUF` (2.99M / 39k), `hugging-quants/Llama-3.2-1B-Instruct-Q4_K_M-GGUF` (1.01M / 49k) |
| Qwen/Qwen3-0.6B | `MaziyarPanahi/Qwen3-0.6B-GGUF`: 3.48M / 202k | `MaziyarPanahi/Qwen3-0.6B-GGUF` (`Qwen/Qwen3-0.6B-GGUF` has 309k 30d, but it is Q8_0 only) | `unsloth/Qwen3-0.6B-GGUF` (1.23M / 145k), `bartowski/Qwen_Qwen3-0.6B-GGUF` (361k / 86k) |

Recommended pin: one uploader for all four models (MaziyarPanahi, the all-time leader for every model), file `*.Q4_K_M.gguf`. Record the LFS sha256 now:

| Repo | File | Size (bytes) | sha256 |
| --- | --- | --- | --- |
| MaziyarPanahi/gemma-3-1b-it-GGUF | gemma-3-1b-it.Q4_K_M.gguf | 806,058,272 | e4304281685198621755dac1851c040ff86b071e997cc214bfb9e8aca7f8dec2 |
| MaziyarPanahi/Qwen3-1.7B-GGUF | Qwen3-1.7B.Q4_K_M.gguf | 1,282,439,296 | ea2aa5f1cce3c8df81ae5fd292a6ed265b8393cc89534dc21fc5327cc974116a |
| MaziyarPanahi/Llama-3.2-1B-Instruct-GGUF | Llama-3.2-1B-Instruct.Q4_K_M.gguf | 807,694,432 | e4650dd6b45ef456066b11e4927f775eef4dd1e0e8473c3c0f27dd19ee13cc4e |
| MaziyarPanahi/Qwen3-0.6B-GGUF | Qwen3-0.6B.Q4_K_M.gguf | 484,220,032 | dc4503da5d7cc7254055a86cd90e1a8c9d16c6ac71eb3a32b34bf48a1f4e0999 |

Alternatives, if you want the 30-day leaders: `ggml-org/gemma-3-1b-it-GGUF` gemma-3-1b-it-Q4_K_M.gguf (sha256 8ccc5cd1…b75a135), `unsloth/Qwen3-1.7B-GGUF` Qwen3-1.7B-Q4_K_M.gguf (b139949c…fa181897; 1.107 GB, smaller than the MaziyarPanahi build because the tensor-type mix differs), `bartowski/Llama-3.2-1B-Instruct-GGUF` Llama-3.2-1B-Instruct-Q4_K_M.gguf (6f85a640…611df83). The same nominal "Q4_K_M" differs between uploaders (sizes and hashes), which is why this column matters, and why the exact file must be pinned.

---

## Blockers and recommendations

**Blockers**
1. **IndicSafeEval is not released.** The paper exists (arXiv 2609.03781, Findings of EMNLP 2026), but the GitHub repo holds only an inference script, and the `dataset/prompts.csv` described in the README is missing. It also has no Tamil, and its items are persuasion jailbreaks rather than plain harmful requests. Options: email the authors (Saikat Mondal / Asif Ekbal), or drop it.
2. **Indi-RomCoM is not released.** The paper exists (arXiv 2606.30790), but I found no data link anywhere. Treat it as unavailable.
3. **Hindi harmful requests have no released, human-built source in the protocol's list.** MultiJail has no Hindi.
4. **XSTest is English only.** All four non-English columns need translation plus a native check, which was already planned.
5. **CrossSum-In Bengali has only 155 test items**, below 200. Avoid CrossSum for the grid (it is also CC-BY-NC-SA).

**Licence flags.** CC-BY-NC applies to IndicSafe and CC-BY-NC-SA to CrossSum-In: fine for academic research, but any released derivative must stay non-commercial and share-alike. Belebele and XQuAD-In/Flores-In are CC-BY-SA, so released translations or derivatives must be CC-BY-SA. IndicGuard and two of the four models fall under the Gemma or Llama terms, and their official weights need manual-gate approval; request it in week 1.

**Recommended concrete sets**
- *Reading:* Belebele `eng_Latn`, `hin_Deva`, `hin_Latn`, `ben_Beng`, test, all 900. Note that `hin_Latn` is transliterated Hindi, not Hinglish, and say so in the paper.
- *Short generation:* XQuAD-In test (EN/HI/BN, 1190 each, parallel), sampling the same 200 ids in every language. For the Hinglish column, either (a) use CodeMixBench `mt_hineng_eng` (942 real romanized items, but a different task), or (b) better for comparability, have the native speaker code-mix or romanize the same 200 XQuAD-In Hindi items. (b) keeps the column task-matched.
- *Harmful requests:* MultiJail EN/BN (315, human-translated), plus Hindi and Hinglish translated from the same 315 English prompts and native-checked. That keeps all four languages parallel. Alternatively, IndicSafe gives about 330 harmful items each for HI/BN/TA with English sources (CC-BY-NC). Do not mix IndicSafeEval jailbreaks with MultiJail plain requests across languages.
- *Over-refusal:* sample 150 of the 250 XSTest safe prompts and translate them to HI/HI-Latn/BN.
- *Judge:* IndicGuard adapter on Gemma-3-4B-IT, plus a second judge. Gate 2 matters most for Hinglish, which IndicGuard was never trained on.

**Held-out language: choose Bengali over Tamil.**

| Task | Bengali | Tamil |
| --- | --- | --- |
| Belebele | 900 (plus `ben_Latn` 900) | 900 |
| IndicGenBench XQuAD/XorQA/Flores | 1190 / 539 / 1012 | 1190 / 538 / 1012 |
| IndicGenBench CrossSum | 155 (too few) | 315 |
| Harmful: MultiJail (human) | **315** | none |
| Harmful: IndicSafeEval | yes, but unreleased | not covered |
| Harmful: IndicSafe | about 330 | about 330 |
| Over-refusal | translate | translate |
| IndicGuard judge | covered | covered |
| Indi-RomCoM (if ever released) | covered | covered |

Bengali is the only option with a released, human-translated harmful-request set (MultiJail) parallel to English. It is also in IndicSafeEval, should that ever be released, and it matches or beats Tamil on every other task. Tamil's only edge is CrossSum, which we are not using, and it has a stronger tokenization-tax story; the latter is a scientific argument, not a data one. Swap to Tamil only if IndicSafe becomes the harmful-request source for every language. In that case both languages are equally covered.
