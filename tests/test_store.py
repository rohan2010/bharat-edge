import pytest

from bee.provenance import sha256_file
from bee.store import load_models, model_card, record_push, repo_id, verify


def test_repo_id():
    assert repo_id("rohan2010", "qwen3-1.7b") == "rohan2010/bharatedge-qwen3-1.7b-gguf"


def test_record_push_pins_revision_per_file():
    ledger = {"schema": 1, "models": {}}
    record_push(ledger, "m", "o/r", "aaa", {"m-Q8_0.gguf": {"sha256": "x", "bytes": 1}})
    record_push(ledger, "m", "o/r", "bbb", {"m-Q4_K_M.gguf": {"sha256": "y", "bytes": 2}})
    files = ledger["models"]["m"]["files"]
    assert files["m-Q8_0.gguf"]["revision"] == "aaa"
    assert files["m-Q4_K_M.gguf"]["revision"] == "bbb"


def test_verify(tmp_path):
    f = tmp_path / "x.gguf"
    f.write_bytes(b"gguf")
    verify(f, sha256_file(f))
    with pytest.raises(ValueError):
        verify(f, "0" * 64)


def test_model_cards_for_all_models():
    for key, model in load_models().items():
        card = model_card(key, model)
        assert f"base_model: {model['hf_repo']}" in card
        assert "license: other" not in card
