import hashlib
import io
import json
import subprocess

import pytest

from bee import provenance


@pytest.fixture
def fake_llama_repo(tmp_path):
    repo = tmp_path / "llama.cpp"
    repo.mkdir()
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "README").write_text("x")
    subprocess.run([*git, "add", "README"], check=True)
    subprocess.run([*git, "commit", "-qm", "init"], check=True)
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    return repo, head


@pytest.fixture
def fake_gguf(tmp_path):
    p = tmp_path / "model-Q4_K_M.gguf"
    data = b"GGUF" + bytes(range(256)) * 50_000  # > one read chunk
    p.write_bytes(data)
    return p, hashlib.sha256(data).hexdigest()


def test_sha256_file(fake_gguf):
    path, digest = fake_gguf
    assert provenance.sha256_file(path) == digest


def test_config_hash_is_order_independent_and_sensitive():
    a = {"model": "gemma-3-1b-it", "precision": "Q4_K_M", "decoding": {"temperature": 0, "seed": 0}}
    b = {"decoding": {"seed": 0, "temperature": 0}, "precision": "Q4_K_M", "model": "gemma-3-1b-it"}
    assert provenance.config_hash(a) == provenance.config_hash(b)
    assert len(provenance.config_hash(a)) == 64
    c = {**a, "precision": "Q3_K_M"}
    assert provenance.config_hash(a) != provenance.config_hash(c)


def test_llama_cpp_commit(fake_llama_repo, tmp_path):
    repo, head = fake_llama_repo
    assert provenance.llama_cpp_commit(repo) == head
    with pytest.raises(FileNotFoundError):
        provenance.llama_cpp_commit(tmp_path / "missing")


def test_build_and_roundtrip_header(fake_llama_repo, fake_gguf, tmp_path):
    repo, head = fake_llama_repo
    gguf, digest = fake_gguf
    cfg = {"model": "qwen3-1.7b", "precision": "Q4_K_M", "task": "belebele", "language": "hi"}
    header = provenance.build_run_header(
        gguf_path=gguf, config=cfg, seed=7, llama_cpp_dir=repo, extra={"run_id": "r1"}
    )
    assert header["record"] == "header"
    assert header["llama_cpp_commit"] == head
    assert header["gguf_sha256"] == digest
    assert header["gguf_file"] == "model-Q4_K_M.gguf"
    assert header["config_hash"] == provenance.config_hash(cfg)
    assert header["seed"] == 7
    assert header["run_id"] == "r1"

    out = tmp_path / "run.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        provenance.write_run_header(f, header)
        f.write(json.dumps({"record": "item", "id": 0}) + "\n")
    assert provenance.read_run_header(out) == header


def test_precomputed_hash_and_extra_collision(fake_llama_repo, fake_gguf):
    repo, _ = fake_llama_repo
    gguf, _ = fake_gguf
    h = provenance.build_run_header(
        gguf_path=gguf, config={}, seed=0, llama_cpp_dir=repo, gguf_sha256="abc"
    )
    assert h["gguf_sha256"] == "abc"
    with pytest.raises(ValueError):
        provenance.build_run_header(
            gguf_path=gguf, config={}, seed=0, llama_cpp_dir=repo, extra={"seed": 1}
        )


def test_header_must_be_first_line_and_valid(tmp_path):
    buf = io.StringIO()
    buf.write("something\n")
    with pytest.raises(ValueError):
        provenance.write_run_header(buf, {"record": "header"})
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({"record": "header", "seed": 0}) + "\n")
    with pytest.raises(ValueError):
        provenance.read_run_header(bad)
