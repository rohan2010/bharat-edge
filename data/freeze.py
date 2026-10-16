"""Freeze the task item sets from the pinned raw data (run data/fetch.py first).

    uv run python data/freeze.py             # freeze what is ready, create translation worksheets
    uv run python data/freeze.py --check     # verify frozen files against the manifests

Outputs:
  data/frozen/<task>/<lang>.jsonl    frozen items in fixed order (gitignored: some sources must
                                     not be re-published, and safety items are harmful prompts)
  data/manifests/<task>.json         version, source hashes, selection rule, item ids
                                     and the sha256 of each frozen file
  data/work/translate_<task>.csv     worksheets for the native-speaker translations (gitignored;
                                     never overwritten once created)

A language that needs translation is frozen only when its worksheet column is complete. Once a
(task, language) is frozen, re-freezing must reproduce the same file hash, or the task's
`version` in configs/tasks.yaml has to be bumped first (CLAUDE.md rule 1).
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from bee.provenance import sha256_file

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw"
FROZEN = ROOT / "data/frozen"
MANIFESTS = ROOT / "data/manifests"
WORK = ROOT / "data/work"
TASKS = ROOT / "configs/tasks.yaml"

BELEBELE_FILES = {"en": "eng_Latn", "hi": "hin_Deva", "hi-Latn": "hin_Latn"}
XSTEST_PER_TYPE = 15  # 10 safe types x 15 = 150
XSTEST_SEED = 0
WORKSHEET_LANGS = ("hi", "hi-Latn")
XQUAD_N = 200
XQUAD_MAX_WORDS = 250  # keeps the romanization workload and prompt length down
XQUAD_SEED = 0
PROBE_SEED = 0
PROBE_SHEET = WORK / "probe_summaries.csv"


def source_hashes(*refs: str) -> dict[str, str]:
    recorded = json.loads((MANIFESTS / "sources.json").read_text())
    return {ref: recorded[ref]["sha256"] for ref in refs}


def task_version(task: str) -> int:
    return yaml.safe_load(TASKS.read_text())["tasks"][task]["version"]


def write_jsonl(path: Path, items: list[dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    return sha256_file(path)


def ids_hash(ids: list[str]) -> str:
    return hashlib.sha256("\n".join(ids).encode()).hexdigest()


# --- script checks for translated text -------------------------------------------------------


def script_share(text: str, script: str) -> float | None:
    """Share of letters in ``text`` in ``script`` ("DEVANAGARI" or "LATIN"); None if no letters."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return None
    return sum(unicodedata.name(c, "").startswith(script) for c in letters) / len(letters)


def devanagari_word_share(text: str) -> float:
    """Share of words (with letters) written in Devanagari.

    Counted per word, not per letter: Devanagari vowel signs are not letters to Python, and
    English terms kept in Hindi ("Python process को kill कैसे करूँ") are long in letters.
    """
    words = [w for w in text.split() if any(c.isalpha() for c in w)]
    if not words:
        return 1.0
    deva = sum(any(unicodedata.name(c, "").startswith("DEVANAGARI") for c in w) for w in words)
    return deva / len(words)


def check_translation(lang: str, text: str) -> str | None:
    """Return a problem description, or None if ``text`` looks like ``lang``."""
    if not text.strip():
        return "empty"
    deva, latin = script_share(text, "DEVANAGARI"), script_share(text, "LATIN")
    if deva is None:  # numbers or punctuation only, e.g. an answer like "308"
        return None
    if lang == "hi" and devanagari_word_share(text) < 0.5:
        return "hi should be mostly Devanagari"
    if lang == "hi-Latn" and latin < 0.95:
        return "hi-Latn should be romanized (Latin script only)"
    return None


# --- sources ---------------------------------------------------------------------------------


def belebele() -> dict[str, list[dict[str, Any]]]:
    """All 900 items per language, in English file order.

    The upstream files are not in the same row order (hin_Deva differs from eng_Latn), so rows
    are aligned on (link, question_number), and the gold answer must agree across languages.
    """

    def key(r: dict[str, Any]) -> tuple[str, str]:
        return r["link"], r["question_number"]

    rows = {
        lang: [json.loads(line) for line in open(RAW / f"belebele/data/{code}.jsonl")]
        for lang, code in BELEBELE_FILES.items()
    }
    order = [key(r) for r in rows["en"]]
    out = {}
    for lang, lang_rows in rows.items():
        by_key = {key(r): r for r in lang_rows}
        if len(by_key) != len(lang_rows) or set(by_key) != set(order):
            raise ValueError(f"Belebele {lang}: items do not match English (link, question)")
        out[lang] = [
            {
                "id": f"belebele-{i:03d}",
                "link": r["link"],
                "question_number": r["question_number"],
                "passage": r["flores_passage"],
                "question": r["question"],
                "options": [r[f"mc_answer{k}"] for k in range(1, 5)],
                "answer": int(r["correct_answer_num"]) - 1,
            }
            for i, r in enumerate(by_key[k] for k in order)
        ]
    answers = {lang: [x["answer"] for x in v] for lang, v in out.items()}
    if any(a != answers["en"] for a in answers.values()):
        raise ValueError("Belebele: gold answers differ across languages after alignment")
    return out


def multijail_en() -> list[dict[str, Any]]:
    with open(RAW / "multijail/MultiJail.csv", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    items = [
        {"id": f"mj-{int(r['id']):03d}", "tags": ast.literal_eval(r["tags"]), "prompt": r["en"]}
        for r in rows
    ]
    return sorted(items, key=lambda x: x["id"])


def xstest_en() -> list[dict[str, Any]]:
    """150 of the 250 safe prompts: 15 per type, drawn with a fixed seed, in XSTest order."""
    with open(RAW / "xstest/xstest_prompts.csv", encoding="utf-8", newline="") as f:
        safe = [r for r in csv.DictReader(f) if r["label"] == "safe"]
    rng = np.random.default_rng(XSTEST_SEED)
    chosen: set[str] = set()
    for t in sorted({r["type"] for r in safe}):
        ids = [r["id"] for r in safe if r["type"] == t]
        chosen.update(rng.choice(ids, size=XSTEST_PER_TYPE, replace=False).tolist())
    return [
        {"id": f"xstest-{int(r['id']):03d}", "type": r["type"], "prompt": r["prompt"]}
        for r in safe
        if r["id"] in chosen
    ]


def xquad() -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    """200 questions from whole XQuAD-In passages, for en and hi; plus the passage list.

    Passages of at most XQUAD_MAX_WORDS Hindi words are shuffled with a fixed seed and taken
    whole until there are XQUAD_N questions; the last passage is cut to make exactly XQUAD_N.
    Questions keep their file order. Statistics must resample passages (clusters), not questions.
    """
    ex = {
        lang: json.load(open(RAW / f"xquad_in/xquad_{lang}_test.json"))["examples"]
        for lang in ("en", "hi")
    }
    if [e["id"] for e in ex["en"]] != [e["id"] for e in ex["hi"]]:
        raise ValueError("XQuAD-In en and hi are not in the same order")
    passage_of: dict[str, str] = {}
    passages: dict[str, dict[str, str]] = {}  # passage id -> {"en": ctx, "hi": ctx}
    seen: dict[str, str] = {}
    for e_en, e_hi in zip(ex["en"], ex["hi"], strict=True):
        if e_hi["context"] not in seen:
            pid = f"xq-p{len(seen):03d}"
            seen[e_hi["context"]] = pid
            passages[pid] = {"en": e_en["context"], "hi": e_hi["context"]}
        passage_of[e_hi["id"]] = seen[e_hi["context"]]
    eligible = [pid for pid, c in passages.items() if len(c["hi"].split()) <= XQUAD_MAX_WORDS]
    rng = np.random.default_rng(XQUAD_SEED)
    chosen, n = [], 0
    for pid in rng.permutation(eligible).tolist():
        if n >= XQUAD_N:
            break
        chosen.append(pid)
        n += sum(p == pid for p in passage_of.values())
    keep: list[str] = [e["id"] for e in ex["hi"] if passage_of[e["id"]] in chosen]
    last = [q for q in keep if passage_of[q] == chosen[-1]]
    drop = set(last[len(last) - (len(keep) - XQUAD_N) :]) if len(keep) > XQUAD_N else set()
    keep_set = set(keep) - drop
    out = {}
    for lang in ("en", "hi"):
        out[lang] = [
            {
                "id": f"xquad-{e['id']}",
                "passage_id": passage_of[e["id"]],
                "context": e["context"],
                "question": e["question"],
                "answers": [a["text"] for a in e["answers"]],
            }
            for e in ex[lang]
            if e["id"] in keep_set
        ]
    order = sorted(chosen)
    return out, [{"id": pid, **passages[pid]} for pid in order]


def xquad_rows(items: dict[str, list[dict[str, Any]]], passages: list[dict[str, Any]]):
    """Worksheet rows: each passage, then each question and its answer (hi prefilled)."""
    rows = [{"id": p["id"], "category": "passage", "en": p["en"], "hi": p["hi"]} for p in passages]
    for e_en, e_hi in zip(items["en"], items["hi"], strict=True):
        for kind, en, hi in (
            ("question", e_en["question"], e_hi["question"]),
            ("answer", e_en["answers"][0], e_hi["answers"][0]),
        ):
            rows.append({"id": f"{e_en['id']}/{kind[0]}", "category": kind, "en": en, "hi": hi})
    return rows


def xquad_hinglish(items_hi: list[dict[str, Any]], texts: dict[str, str]) -> list[dict[str, Any]]:
    return [
        {
            **x,
            "context": texts[x["passage_id"]],
            "question": texts[f"{x['id']}/q"],
            "answers": [texts[f"{x['id']}/a"]],
        }
        for x in items_hi
    ]


def probe_options(summaries: dict[str, str], tags: dict[str, list[str]]) -> dict[str, Any]:
    """Fixed 4-way options per safety item: its summary plus 3 from items sharing no tag.

    Drawn once with default_rng(PROBE_SEED), in item order, so every language gets the same
    options in the same order; only the prompt changes.
    """
    rng = np.random.default_rng(PROBE_SEED)
    ids = list(summaries)
    out = {}
    for i in ids:
        pool = [j for j in ids if not set(tags[j]) & set(tags[i]) and summaries[j] != summaries[i]]
        distractors = rng.choice(pool, size=3, replace=False).tolist()
        answer = int(rng.integers(4))
        options = [summaries[j] for j in distractors]
        options.insert(answer, summaries[i])
        out[i] = {"options": options, "answer": answer, "distractor_ids": distractors}
    return out


def read_probe_summaries(en_items: list[dict[str, Any]]) -> dict[str, str] | None:
    """Checked summaries {safety id: summary}, or None until every row is marked checked."""
    if not PROBE_SHEET.exists():
        return None
    with open(PROBE_SHEET, encoding="utf-8-sig", newline="") as f:
        rows = {r["id"]: r for r in csv.DictReader(f)}
    if sorted(rows) != sorted(x["id"] for x in en_items):
        raise ValueError(f"{PROBE_SHEET.name}: ids differ from the frozen safety items")
    for x in en_items:
        if rows[x["id"]]["en"] != x["prompt"]:
            raise ValueError(f"{PROBE_SHEET.name}: English text of {x['id']} was edited")
    missing = [i for i, r in rows.items() if not r["summary"].strip()]
    if missing:
        raise ValueError(f"{PROBE_SHEET.name}: empty summary for {missing[:5]}")
    checked = sum(r["checked"].strip().lower() in {"y", "yes"} for r in rows.values())
    if checked < len(rows):
        print(f"  {PROBE_SHEET.name}: {checked}/{len(rows)} summaries checked")
        return None
    return {x["id"]: rows[x["id"]]["summary"].strip() for x in en_items}


def probe_items(
    safety: dict[str, list[dict[str, Any]]], options: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    return {
        lang: [
            {
                "id": f"probe-{x['id']}",
                "safety_id": x["id"],
                "prompt": x["prompt"],
                "options": options[x["id"]]["options"],
                "answer": options[x["id"]]["answer"],
            }
            for x in items
        ]
        for lang, items in safety.items()
    }


# --- worksheets ------------------------------------------------------------------------------


def ensure_worksheet(task: str, rows: list[dict[str, str]]) -> Path:
    """Create the worksheet once. Never overwrite it: it holds the native speaker's work."""
    path = WORK / f"translate_{task}.csv"
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:  # BOM so Excel/Numbers read UTF-8
        w = csv.writer(f)
        w.writerow(["id", "category", "en", "hi", "hi_Latn", "notes"])
        for r in rows:
            w.writerow([r["id"], r["category"], r["en"], r.get("hi", ""), "", ""])
    print(f"created worksheet {path.relative_to(ROOT)} ({len(rows)} rows)")
    return path


def read_worksheet(
    path: Path, locked: dict[str, dict[str, str]], langs: tuple[str, ...]
) -> dict[str, dict[str, str]]:
    """Return {lang: {id: text}} for each of ``langs`` whose column is complete and valid.

    ``locked`` maps each expected row id to the source columns that must be unchanged.
    """
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = {r["id"]: r for r in csv.DictReader(f)}
    expected = list(locked)
    if sorted(rows) != sorted(expected):
        raise ValueError(f"{path.name}: row ids differ from the frozen source items")
    for i, cols in locked.items():
        for col, text in cols.items():
            if rows[i][col] != text:
                raise ValueError(f"{path.name}: source column {col!r} of {i} was edited")
    ready = {}
    for lang in langs:
        col = lang.replace("-", "_")
        problems = {i: check_translation(lang, rows[i][col]) for i in expected}
        problems = {i: p for i, p in problems.items() if p}
        if not problems:
            ready[lang] = {i: rows[i][col].strip() for i in expected}
        else:
            filled = len(expected) - sum(p == "empty" for p in problems.values())
            bad = {i: p for i, p in problems.items() if p != "empty"}
            print(f"  {path.name} {lang}: {filled}/{len(expected)} filled", end="")
            print(f"; problems: {dict(list(bad.items())[:5])}" if bad else "")
    return ready


# --- freezing --------------------------------------------------------------------------------


def freeze(
    task: str,
    per_lang: dict[str, list[dict[str, Any]]],
    sources: dict[str, str],
    selection: str,
    check_only: bool,
) -> bool:
    manifest_path = MANIFESTS / f"{task}.json"
    old = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"languages": {}}
    version = task_version(task)
    manifest = {"task": task, "version": version, "sources": sources, "selection": selection}
    langs, ok = {}, True
    lost = set(old["languages"]) - set(per_lang)
    if lost and not check_only:
        sys.exit(
            f"{task}: {sorted(lost)} were frozen but are no longer complete; fix the worksheet"
        )
    for lang, items in per_lang.items():
        path = FROZEN / task / f"{lang}.jsonl"
        ids = [x["id"] for x in items]
        prev = old["languages"].get(lang)
        if check_only:
            good = prev and path.exists() and sha256_file(path) == prev["file_sha256"]
            print(f"{'ok  ' if good else 'FAIL'} {task}/{lang}")
            ok &= bool(good)
            continue
        sha = write_jsonl(path, items)
        if prev and old.get("version") == version and sha != prev["file_sha256"]:
            sys.exit(
                f"{task}/{lang}: frozen file changed ({prev['file_sha256'][:12]} -> {sha[:12]}) "
                f"without a version bump in {TASKS.name}"
            )
        langs[lang] = {"n": len(items), "ids_sha256": ids_hash(ids), "file_sha256": sha}
        print(f"frozen {task}/{lang}: {len(items)} items, sha256 {sha[:12]}")
    if not check_only:
        manifest["languages"] = langs
        manifest["ids"] = [x["id"] for x in next(iter(per_lang.values()))]
        MANIFESTS.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return ok


def frozen_langs(task: str) -> dict[str, list[dict[str, Any]]]:
    """Languages already frozen for ``task`` (for --check, which only needs the names)."""
    path = MANIFESTS / f"{task}.json"
    langs = json.loads(path.read_text())["languages"] if path.exists() else {}
    return {lang: [] for lang in langs}


def translated(items: list[dict[str, Any]], texts: dict[str, str]) -> list[dict[str, Any]]:
    return [{**x, "prompt": texts[x["id"]]} for x in items]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Freeze task item sets.")
    p.add_argument("--check", action="store_true", help="verify frozen files only")
    args = p.parse_args(argv)
    ok = True
    frozen_per_task: dict[str, dict[str, list[dict[str, Any]]]] = {}

    ok &= freeze(
        "belebele",
        belebele(),
        source_hashes(*(f"belebele/data/{c}.jsonl" for c in BELEBELE_FILES.values())),
        "all 900 test items per language, in file order (parallel across languages)",
        args.check,
    )

    for task, en_items, category, src, rule in (
        (
            "safety",
            multijail_en(),
            lambda x: "; ".join(x["tags"]),
            "multijail/MultiJail.csv",
            "all 315 MultiJail prompts, ordered by id; hi and hi-Latn translated from en by a "
            "native speaker (data/work/translate_safety.csv)",
        ),
        (
            "overrefusal",
            xstest_en(),
            lambda x: x["type"],
            "xstest/xstest_prompts.csv",
            f"{XSTEST_PER_TYPE} per safe type (10 types) drawn with numpy default_rng("
            f"{XSTEST_SEED}), in XSTest order; hi and hi-Latn translated by a native speaker "
            "(data/work/translate_overrefusal.csv)",
        ),
    ):
        per_lang = {"en": en_items}
        if not args.check:
            rows = [{"id": x["id"], "category": category(x), "en": x["prompt"]} for x in en_items]
            sheet = ensure_worksheet(task, rows)
            locked = {x["id"]: {"en": x["prompt"]} for x in en_items}
            for lang, texts in read_worksheet(sheet, locked, WORKSHEET_LANGS).items():
                per_lang[lang] = translated(en_items, texts)
        else:
            per_lang = frozen_langs(task)
        ok &= freeze(task, per_lang, source_hashes(src), rule, args.check)
        frozen_per_task[task] = per_lang

    items, passages = xquad()
    if not args.check:
        rows = xquad_rows(items, passages)
        sheet = ensure_worksheet("generation", rows)
        locked = {r["id"]: {"en": r["en"], "hi": r["hi"]} for r in rows}
        for _lang, texts in read_worksheet(sheet, locked, ("hi-Latn",)).items():
            items["hi-Latn"] = xquad_hinglish(items["hi"], texts)
    else:
        items = frozen_langs("generation")
    ok &= freeze(
        "generation",
        items,
        source_hashes("xquad_in/xquad_en_test.json", "xquad_in/xquad_hi_test.json"),
        f"XQuAD-In test: passages of <= {XQUAD_MAX_WORDS} Hindi words, shuffled with numpy "
        f"default_rng({XQUAD_SEED}), taken whole until {XQUAD_N} questions (last passage cut); "
        "hi-Latn romanized from hi by a native speaker (data/work/translate_generation.csv). "
        "Questions are clustered by passage_id: resample passages for CIs.",
        args.check,
    )
    safety = frozen_per_task["safety"]
    if args.check:
        ok &= freeze("probe", frozen_langs("probe"), {}, "", check_only=True)
    elif (summaries := read_probe_summaries(safety["en"])) is not None:
        tags = {x["id"]: x["tags"] for x in safety["en"]}
        ok &= freeze(
            "probe",
            probe_items(safety, probe_options(summaries, tags)),
            {
                **source_hashes("multijail/MultiJail.csv"),
                "probe_summaries.csv": sha256_file(PROBE_SHEET),
            },
            "one item per safety item, in every language the safety task has frozen: the prompt "
            "plus 4 English one-line summaries, i.e. its own (native-checked, "
            "data/work/probe_summaries.csv) and 3 from items sharing no MultiJail tag, drawn "
            f"with numpy default_rng({PROBE_SEED})",
            check_only=False,
        )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
