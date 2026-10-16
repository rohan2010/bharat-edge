# data/

Scripts only. Nothing under `data/raw/`, `data/frozen/`, `data/work/` or `data/manifests/` is committed (all gitignored until publication); `data/backup.py push` backs up frozen items, worksheets, manifests, the model ledger and the research docs to a private HF dataset repo.

```bash
uv run python data/fetch.py      # download pinned sources (configs/data_sources.yaml) to data/raw/
uv run python data/freeze.py     # freeze item sets to data/frozen/, update data/manifests/
uv run python data/freeze.py --check
```

- `manifests/sources.json`: sha256 of every downloaded source file at its pinned HF revision.
- `manifests/<task>.json`: task version, selection rule, item ids and the sha256 of each frozen `data/frozen/<task>/<lang>.jsonl`.
- `TRANSLATING.md`: how to fill the native-speaker worksheets in `data/work/`.

Frozen item sets are versioned by `version` in `configs/tasks.yaml` (CLAUDE.md rule 1).
