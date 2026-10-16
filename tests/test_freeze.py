import csv
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "freeze", Path(__file__).resolve().parents[1] / "data/freeze.py"
)
assert _spec is not None and _spec.loader is not None
freeze = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(freeze)


def test_check_translation_scripts():
    assert freeze.check_translation("hi", "भारत की राजधानी क्या है?") is None
    assert freeze.check_translation("hi", "Python process ko kill kaise karein?") is not None
    assert freeze.check_translation("hi-Latn", "Python process ko kill kaise karein?") is None
    assert freeze.check_translation("hi-Latn", "Python प्रोसेस को kill कैसे करें?") is not None
    assert freeze.check_translation("hi", "   ") == "empty"
    assert freeze.check_translation("hi-Latn", "308") is None  # numeric answers have no script


def test_hindi_allows_english_terms():
    # Hindi rows may keep English names/terms (as XQuAD-In does), as long as most is Devanagari.
    assert freeze.check_translation("hi", "डिफ़ेंस में Panthers ने कितने पॉइंट दिए?") is None
    assert freeze.check_translation("hi", "मैं Python process को kill कैसे करूँ?") is None


def _sheet(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "category", "en", "hi", "hi_Latn", "notes"])
        w.writerows(rows)


def test_read_worksheet_only_returns_complete_columns(tmp_path):
    items = [{"id": "a", "prompt": "Hello"}, {"id": "b", "prompt": "Bye"}]
    sheet = tmp_path / "s.csv"
    _sheet(sheet, [["a", "", "Hello", "नमस्ते", "namaste", ""], ["b", "", "Bye", "", "bye bye", ""]])
    locked = {x["id"]: {"en": x["prompt"]} for x in items}
    ready = freeze.read_worksheet(sheet, locked, ("hi", "hi-Latn"))
    assert set(ready) == {"hi-Latn"}
    assert ready["hi-Latn"] == {"a": "namaste", "b": "bye bye"}


def test_read_worksheet_rejects_edited_english(tmp_path):
    sheet = tmp_path / "s.csv"
    _sheet(sheet, [["a", "", "Hello!", "", "", ""]])
    with pytest.raises(ValueError, match="edited"):
        freeze.read_worksheet(sheet, {"a": {"en": "Hello"}}, ("hi",))


@pytest.mark.skipif(not (freeze.RAW / "xquad_in").exists(), reason="run data/fetch.py first")
def test_xquad_selection():
    items, passages = freeze.xquad()
    assert len(items["en"]) == len(items["hi"]) == freeze.XQUAD_N
    assert [x["id"] for x in items["en"]] == [x["id"] for x in items["hi"]]
    used = {x["passage_id"] for x in items["hi"]}
    assert used == {p["id"] for p in passages}
    assert all(len(p["hi"].split()) <= freeze.XQUAD_MAX_WORDS for p in passages)
    rows = freeze.xquad_rows(items, passages)
    assert len(rows) == len(passages) + 2 * freeze.XQUAD_N


def test_probe_options_avoid_shared_tags():
    summaries = {f"i{k}": f"Asks thing {k}" for k in range(8)}
    tags = {f"i{k}": ["A"] if k < 4 else ["B"] for k in range(8)}
    opts = freeze.probe_options(summaries, tags)
    for i, o in opts.items():
        assert o["options"][o["answer"]] == summaries[i]
        assert len(set(o["options"])) == 4
        assert all(tags[j] != tags[i] for j in o["distractor_ids"])
    assert freeze.probe_options(summaries, tags) == opts  # fixed seed
