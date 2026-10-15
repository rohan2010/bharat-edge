"""Sanity checks on configs/*.yaml, including the smoke grid required before any full run."""

from pathlib import Path

import yaml

CONFIGS = Path(__file__).resolve().parents[1] / "configs"


def _load(name):
    return yaml.safe_load((CONFIGS / name).read_text(encoding="utf-8"))


def test_grid_references_known_entries():
    models = _load("models.yaml")["models"]
    precisions = _load("precisions.yaml")["precisions"]
    tasks = _load("tasks.yaml")
    grid = _load("grid.yaml")["grids"]
    langs = set(tasks["languages"])
    for g in grid.values():
        assert set(g["models"]) <= set(models)
        assert set(g["precisions"]) <= set(precisions)
        assert set(g["tasks"]) <= set(tasks["tasks"])
        assert set(g["languages"]) <= langs


def test_full_grid_is_4_models_by_6_builds():
    grid = _load("grid.yaml")["grids"]["full"]
    assert len(grid["models"]) * len(grid["precisions"]) == 24


def test_smoke_grid_shape():
    smoke = _load("grid.yaml")["grids"]["smoke"]
    assert len(smoke["models"]) == 1
    assert len(smoke["precisions"]) == 2
    assert smoke["items_per_task"] == 20


def test_decoding_is_greedy():
    dec = _load("grid.yaml")["decoding"]
    assert dec["temperature"] == 0.0 and dec["top_k"] == 1
