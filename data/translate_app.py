"""Local translation workbench for the native-speaker worksheets in data/work/.

    uv run python data/translate_app.py            # opens http://127.0.0.1:8765

Serves data/translate_app.html and reads/writes the worksheet CSVs directly: every edit is saved
to the CSV at once (atomic write), so `data/freeze.py` and `data/backup.py` see it. Listens on
127.0.0.1 only; nothing leaves the machine. On start, each worksheet is copied to
data/work/.history/ so a bad edit can always be undone.

Don't edit a worksheet in Numbers/Excel while this is running: whichever saves last wins.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import shutil
import tempfile
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from typing import Any

DATA = Path(__file__).resolve().parent
HTML = DATA / "translate_app.html"
COLUMNS = {
    "translate": ["id", "category", "en", "hi", "hi_Latn", "notes"],
    "probe": ["id", "category", "en", "summary", "checked", "notes"],
}
# name -> file, column layout, source columns shown read-only, editable fields, required fields
SHEETS: dict[str, dict[str, Any]] = {
    "probe": {
        "file": "probe_summaries.csv",
        "layout": "probe",
        "title": "Probe summaries",
        "source": ["en"],
        "fields": ["summary", "checked", "notes"],
        "required": ["summary", "checked"],
    },
    "safety": {
        "file": "translate_safety.csv",
        "layout": "translate",
        "title": "Safety",
        "source": ["en"],
        "fields": ["hi", "hi_Latn", "notes"],
        "required": ["hi", "hi_Latn"],
    },
    "overrefusal": {
        "file": "translate_overrefusal.csv",
        "layout": "translate",
        "title": "Over-refusal",
        "source": ["en"],
        "fields": ["hi", "hi_Latn", "notes"],
        "required": ["hi", "hi_Latn"],
    },
    "generation": {
        "file": "translate_generation.csv",
        "layout": "translate",
        "title": "Generation",
        "source": ["en", "hi"],
        "fields": ["hi_Latn", "notes"],
        "required": ["hi_Latn"],
    },
}
LANG_OF = {"hi": "hi", "hi_Latn": "hi-Latn"}


def _load_freeze():
    spec = importlib.util.spec_from_file_location("freeze", DATA / "freeze.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_translation = _load_freeze().check_translation


class Workbench:
    def __init__(self, work: Path, frozen: Path):
        self.work, self.frozen, self.lock = work, frozen, Lock()

    def path(self, sheet: str) -> Path:
        return self.work / SHEETS[sheet]["file"]

    def available(self) -> list[str]:
        return [s for s in SHEETS if self.path(s).exists()]

    def snapshot(self) -> None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        hist = self.work / ".history"
        hist.mkdir(exist_ok=True)
        for s in self.available():
            shutil.copy2(self.path(s), hist / f"{self.path(s).stem}-{stamp}.csv")

    def read(self, sheet: str) -> list[dict[str, str]]:
        with open(self.path(sheet), encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    def write(self, sheet: str, rows: list[dict[str, str]]) -> None:
        path = self.path(sheet)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}-", suffix=".csv")
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS[SHEETS[sheet]["layout"]])
            w.writeheader()
            w.writerows(rows)
        os.replace(tmp, path)

    # --- status ---------------------------------------------------------------------------

    @staticmethod
    def problems(sheet: str, row: dict[str, str]) -> dict[str, str]:
        out = {}
        for field in SHEETS[sheet]["required"]:
            value = row.get(field, "")
            if field in LANG_OF:
                p = check_translation(LANG_OF[field], value)
            elif field == "checked":
                p = None if value.strip().lower() in {"y", "yes"} else "empty"
            else:
                p = None if value.strip() else "empty"
            if p:
                out[field] = p
        return out

    def status(self, sheet: str, row: dict[str, str]) -> dict[str, Any]:
        probs = self.problems(sheet, row)
        bad = {k: v for k, v in probs.items() if v != "empty"}
        state = "problem" if bad else ("todo" if probs else "done")
        return {
            "state": state,
            "problems": bad,
            "missing": sorted(k for k in probs if k not in bad),
        }

    def progress(self, sheet: str, rows: list[dict[str, str]]) -> dict[str, Any]:
        per_field = {
            f: sum(f not in self.problems(sheet, r) for r in rows)
            for f in SHEETS[sheet]["required"]
        }
        done = sum(self.status(sheet, r)["state"] == "done" for r in rows)
        return {"total": len(rows), "done": done, "fields": per_field}

    # --- generation context ---------------------------------------------------------------

    def passage_of(self) -> dict[str, str]:
        """Question id -> passage id, from the frozen Hindi generation items."""
        path = self.frozen / "generation/hi.jsonl"
        if not path.exists():
            return {}
        out = {}
        for line in open(path, encoding="utf-8"):
            item = json.loads(line)
            out[item["id"]] = item["passage_id"]
        return out

    def ordered(self, sheet: str, rows: list[dict[str, str]]) -> list[dict[str, Any]]:
        """Rows with status; generation rows grouped as passage, then its question/answer pairs."""
        enriched = [{**r, "status": self.status(sheet, r)} for r in rows]
        if sheet != "generation":
            return enriched
        passage_of = self.passage_of()
        by_passage: dict[str, list[dict[str, Any]]] = {}
        passages = []
        for r in enriched:
            if r["category"] == "passage":
                r["passage_id"] = r["id"]
                passages.append(r)
            else:
                r["passage_id"] = passage_of.get(r["id"].rsplit("/", 1)[0], "")
                by_passage.setdefault(r["passage_id"], []).append(r)
        out = []
        for p in passages:
            out.append(p)
            out.extend(by_passage.get(p["id"], []))
        return out

    # --- API ------------------------------------------------------------------------------

    def summary(self) -> list[dict[str, Any]]:
        out = []
        for s in self.available():
            meta = SHEETS[s]
            out.append(
                {
                    "name": s,
                    "title": meta["title"],
                    "source": meta["source"],
                    "fields": meta["fields"],
                    "required": meta["required"],
                    "progress": self.progress(s, self.read(s)),
                }
            )
        return out

    def sheet(self, sheet: str) -> dict[str, Any]:
        rows = self.read(sheet)
        return {"rows": self.ordered(sheet, rows), "progress": self.progress(sheet, rows)}

    def save(self, sheet: str, row_id: str, field: str, value: str) -> dict[str, Any]:
        if field not in SHEETS[sheet]["fields"]:
            raise ValueError(f"{field!r} is not editable in {sheet}")
        value = value.replace("\r\n", "\n")
        with self.lock:
            rows = self.read(sheet)  # re-read: keep any rows changed elsewhere
            match = [r for r in rows if r["id"] == row_id]
            if not match:
                raise KeyError(f"no row {row_id!r} in {sheet}")
            match[0][field] = value
            self.write(sheet, rows)
        return {"status": self.status(sheet, match[0]), "progress": self.progress(sheet, rows)}


def make_handler(bench: Workbench):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):  # noqa: A002 (quiet server)
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj: Any) -> None:
            self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json")

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send(200, HTML.read_bytes(), "text/html; charset=utf-8")
            elif self.path == "/api/sheets":
                self._json(200, bench.summary())
            elif self.path.startswith("/api/sheet/"):
                name = self.path.removeprefix("/api/sheet/")
                if name not in bench.available():
                    self._json(404, {"error": f"no worksheet {name!r}"})
                else:
                    self._json(200, bench.sheet(name))
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/api/save":
                self._json(404, {"error": "not found"})
                return
            try:
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if body["sheet"] not in bench.available():
                    raise KeyError(f"no worksheet {body['sheet']!r}")
                result = bench.save(body["sheet"], body["id"], body["field"], body["value"])
                self._json(200, result)
            except (KeyError, ValueError, TypeError) as e:
                self._json(400, {"error": str(e)})

    return Handler


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Local translation workbench.")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--work", type=Path, default=DATA / "work", help="worksheet folder")
    p.add_argument("--frozen", type=Path, default=DATA / "frozen")
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args(argv)
    bench = Workbench(args.work, args.frozen)
    if not bench.available():
        raise SystemExit(f"no worksheets in {args.work}; run `uv run python data/freeze.py` first")
    bench.snapshot()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(bench))
    url = f"http://127.0.0.1:{args.port}"
    print(f"Translation workbench on {url} (Ctrl+C to stop). Snapshots in {args.work}/.history/")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
