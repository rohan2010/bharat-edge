import math
from pathlib import Path

import pytest

from bee import store
from bee.quantize import (
    BIN_DIR,
    MAX_PPL_RATIO,
    SANITY_DIR,
    SANITY_LANGS,
    build_name,
    check_sanity,
    parse_ppl,
    read_source,
    record_path,
)


def test_build_name_and_record_path():
    name = build_name("qwen3-0.6b", "Q4_K_M")
    assert name == "qwen3-0.6b-Q4_K_M.gguf"
    assert record_path(Path("m") / name).name == "qwen3-0.6b-Q4_K_M.gguf.json"


def test_parse_ppl():
    log = "perplexity: calculating...\n0.00.68 I Final estimate: PPL = 24.7081 +/- 6.28442\n"
    assert parse_ppl(log) == pytest.approx(24.7081)
    assert math.isnan(parse_ppl("Final estimate: PPL = nan +/- nan"))
    with pytest.raises(RuntimeError):
        parse_ppl("segfault")


def test_check_sanity():
    ref = {"en": 20.0, "hi": 4.0}
    out = check_sanity({"en": 30.0, "hi": 6.0}, ref)
    assert out["ratio"] == {"en": 1.5, "hi": 1.5}
    with pytest.raises(ValueError):
        check_sanity({"en": 20.0 * MAX_PPL_RATIO * 1.01, "hi": 4.0}, ref)
    with pytest.raises(ValueError):
        check_sanity({"en": float("nan"), "hi": 4.0}, ref)


def test_read_source(tmp_path):
    (tmp_path / "SOURCE.txt").write_text("hf_repo: Qwen/Qwen3-0.6B\nsha256: abc\nbytes: 12\n")
    assert read_source(tmp_path) == {"hf_repo": "Qwen/Qwen3-0.6B", "sha256": "abc", "bytes": "12"}


def test_sanity_texts_exist():
    for lang in SANITY_LANGS:
        assert len((SANITY_DIR / f"{lang}.txt").read_text(encoding="utf-8").split()) > 250


def test_push_refuses_changed_file(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "MODELS_DIR", tmp_path)
    (tmp_path / "m").mkdir()
    (tmp_path / "m" / "m-Q8_0.gguf").write_bytes(b"gguf")
    with pytest.raises(ValueError, match="build record"):
        store.push_files("m", ["m-Q8_0.gguf"], owner="o", expected_sha256={"m-Q8_0.gguf": "0"})


@pytest.mark.skipif(not (BIN_DIR / "llama-quantize").exists(), reason="llama.cpp not built")
def test_llama_cpp_binaries_present():
    assert (BIN_DIR / "llama-perplexity").exists()
