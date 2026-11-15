"""SQLite storage. One file holds the corpus and every analysis table.

Papers are keyed by `key` (a stable id from their source). Cross-source
duplicates (same paper from OpenAlex and Semantic Scholar, say) are merged on
(normalized title, year), keeping the richest value of every field.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable

import pandas as pd

from .text import normalize_title

SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    key            TEXT PRIMARY KEY,
    title          TEXT NOT NULL,
    title_norm     TEXT NOT NULL,
    abstract       TEXT DEFAULT '',
    authors        TEXT DEFAULT '[]',      -- JSON list
    institutions   TEXT DEFAULT '[]',      -- JSON list
    venue          TEXT NOT NULL,          -- canonical short name, e.g. 'neurips'
    year           INTEGER NOT NULL,
    presentation   TEXT DEFAULT '',        -- oral / spotlight / poster / '' (unknown)
    paper_type     TEXT DEFAULT 'main',    -- main / position / workshop / preprint
    topic          TEXT DEFAULT '',        -- official venue topic if any
    url            TEXT DEFAULT '',
    doi            TEXT DEFAULT '',
    arxiv_id       TEXT DEFAULT '',
    citations      INTEGER,                -- NULL = unknown
    date           TEXT DEFAULT '',
    sources        TEXT DEFAULT '[]'       -- JSON list of sources that reported it
);
CREATE INDEX IF NOT EXISTS ix_papers_tn ON papers(title_norm, year);
CREATE INDEX IF NOT EXISTS ix_papers_vy ON papers(venue, year);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""

COLUMNS = [
    "key", "title", "title_norm", "abstract", "authors", "institutions", "venue",
    "year", "presentation", "paper_type", "topic", "url", "doi", "arxiv_id",
    "citations", "date", "sources",
]
_LIST_COLS = ("authors", "institutions", "sources")


class DB:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def conn(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()

    # ------------------------------------------------------------------ papers
    def upsert_papers(self, papers: Iterable[dict], source: str) -> tuple[int, int]:
        """Insert or merge papers. Returns (inserted, merged)."""
        inserted = merged = 0
        with self.conn() as c:
            for p in papers:
                p = _prepare(p, source)
                if not p["title_norm"]:
                    continue
                row = c.execute("SELECT * FROM papers WHERE key=?", (p["key"],)).fetchone()
                if row is None:
                    # Same title in the same year = same paper. Across adjacent
                    # years only a preprint and its venue version are merged
                    # (the venue record wins); two venues never merge.
                    for cand in c.execute(
                        "SELECT * FROM papers WHERE title_norm=? AND year BETWEEN ? AND ?",
                        (p["title_norm"], p["year"] - 1, p["year"] + 1),
                    ).fetchall():
                        if cand["year"] == p["year"] and (cand["venue"] == p["venue"] or "arxiv" in (cand["venue"], p["venue"])) \
                                or "arxiv" in (cand["venue"], p["venue"]):
                            row = cand
                            break
                if row is None:
                    c.execute(
                        f"INSERT INTO papers ({','.join(COLUMNS)}) VALUES ({','.join('?' * len(COLUMNS))})",
                        [p[k] for k in COLUMNS],
                    )
                    inserted += 1
                else:
                    m = _merge(dict(row), p)
                    sets = ",".join(f"{k}=?" for k in COLUMNS if k != "key")
                    c.execute(
                        f"UPDATE papers SET {sets} WHERE key=?",
                        [m[k] for k in COLUMNS if k != "key"] + [row["key"]],
                    )
                    merged += 1
        return inserted, merged

    def papers(self, where: str = "", params: tuple = ()) -> pd.DataFrame:
        with self.conn() as c:
            df = pd.read_sql_query(f"SELECT * FROM papers {where} ORDER BY key", c, params=params)
        for col in _LIST_COLS:
            df[col] = df[col].map(lambda s: json.loads(s) if s else [])
        return df

    def count(self) -> int:
        with self.conn() as c:
            return c.execute("SELECT COUNT(*) FROM papers").fetchone()[0]

    def summary(self) -> pd.DataFrame:
        with self.conn() as c:
            return pd.read_sql_query(
                "SELECT venue, year, COUNT(*) n, SUM(LENGTH(abstract)>100) with_abstract, "
                "SUM(citations IS NOT NULL) with_citations, SUM(presentation IN ('oral','spotlight')) highlighted "
                "FROM papers GROUP BY venue, year ORDER BY venue, year",
                c,
            )

    # ---------------------------------------------------------- analysis tables
    def write_table(self, name: str, df: pd.DataFrame) -> None:
        df = df.copy()
        for col in df.columns:
            if df[col].map(lambda v: isinstance(v, (list, dict))).any():
                df[col] = df[col].map(json.dumps)
        with self.conn() as c:
            df.to_sql(name, c, if_exists="replace", index=False)

    def read_table(self, name: str, json_cols: tuple = ()) -> pd.DataFrame:
        with self.conn() as c:
            exists = c.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
            ).fetchone()
            if not exists:
                return pd.DataFrame()
            df = pd.read_sql_query(f"SELECT * FROM {name}", c)
        for col in json_cols:
            if col in df:
                df[col] = df[col].map(lambda s: json.loads(s) if isinstance(s, str) and s else s)
        return df

    def has_table(self, name: str) -> bool:
        with self.conn() as c:
            return bool(
                c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
            )

    def set_meta(self, k: str, v) -> None:
        with self.conn() as c:
            c.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (k, json.dumps(v)))

    def get_meta(self, k: str, default=None):
        with self.conn() as c:
            row = c.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return json.loads(row[0]) if row else default


def _prepare(p: dict, source: str) -> dict:
    out = {k: p.get(k) for k in COLUMNS}
    out["title"] = (out["title"] or "").strip()
    out["title_norm"] = normalize_title(out["title"])
    out["venue"] = (out["venue"] or "unknown").lower()
    out["year"] = int(out["year"] or 0)
    out["key"] = out["key"] or f"{source}:{out['venue']}{out['year']}:{out['title_norm'][:80]}"
    for col in _LIST_COLS:
        v = out[col] or []
        if isinstance(v, str):
            v = [v]
        out[col] = list(v)
    out["sources"] = sorted(set(out["sources"]) | {source})
    for col in _LIST_COLS:
        out[col] = json.dumps(out[col])
    for col in ("abstract", "presentation", "topic", "url", "doi", "arxiv_id", "date"):
        out[col] = (out[col] or "").strip() if isinstance(out[col], str) else (out[col] or "")
    out["paper_type"] = out["paper_type"] or "main"
    if out["citations"] is not None:
        out["citations"] = int(out["citations"])
    return out


def _merge(old: dict, new: dict) -> dict:
    m = dict(old)
    old_is_preprint = old.get("venue") == "arxiv"
    for k in COLUMNS:
        if k in ("key", "sources"):
            continue
        ov, nv = old.get(k), new.get(k)
        if k in ("venue", "year", "paper_type"):
            # A real venue beats 'arxiv'.
            if old_is_preprint and new.get("venue") != "arxiv":
                m[k] = nv
            continue
        if k == "citations":
            vals = [v for v in (ov, nv) if v is not None]
            m[k] = max(vals) if vals else None
        elif k in ("authors", "institutions"):
            m[k] = nv if len(json.loads(nv or "[]")) > len(json.loads(ov or "[]")) else ov
        elif isinstance(nv, str) and len(nv) > len(ov or ""):
            m[k] = nv
    m["sources"] = json.dumps(sorted(set(json.loads(old["sources"])) | set(json.loads(new["sources"]))))
    return m
