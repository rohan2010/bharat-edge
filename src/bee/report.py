"""Tables and plots from DuckDB.

Loads run JSONL files from ``results/`` into DuckDB, computes per-cell scores with ``bee.stats``
(relative loss, gap, bootstrap CIs, permutation tests with Holm correction) and writes aggregate
tables and Matplotlib figures to ``results/summaries/``. Never emits raw harmful outputs.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb
    import pandas as pd


def load_results(results_dir: Path = Path("results")) -> duckdb.DuckDBPyConnection:
    """Load all run JSONL files into a DuckDB connection/table."""
    raise NotImplementedError


def loss_table(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Per (model, precision, language, task) relative loss and gap with 95% CIs."""
    raise NotImplementedError


def plot_loss_chart(con: duckdb.DuckDBPyConnection, out_path: Path) -> Path:
    """The Gate 1 loss chart: relative loss by precision, one line per language."""
    raise NotImplementedError
