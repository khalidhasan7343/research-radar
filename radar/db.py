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
    topic          TEXT DEFAULT '',        -- topic label from the source (see topic_source)
    topic_source   TEXT DEFAULT '',        -- which source `topic` came from, e.g. 'openreview'
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
    "year", "presentation", "paper_type", "topic", "topic_source", "url", "doi", "arxiv_id",
    "citations", "date", "sources",
]
_LIST_COLS = ("authors", "institutions", "sources")

# Sources whose `topic` is the venue's own official taxonomy (OpenReview's
# primary area; the venue topics in the RTanalysis corpus). OpenAlex topics and
# arXiv categories are different taxonomies.
OFFICIAL_TOPIC_SOURCES = ("openreview", "rtanalysis")


def _topic_rank(source: str) -> int:
    """Which topic to keep when two records merge: official > other > arXiv > none."""
    if not source:
        return 0
    if source in OFFICIAL_TOPIC_SOURCES:
        return 3
    return 1 if source == "arxiv" else 2


class DB:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.conn() as c:
            c.executescript(SCHEMA)
            self._migrate(c)

    @staticmethod
    def _migrate(c) -> None:
        """Upgrade databases created before `topic_source` existed. Where a paper
        came from a single source, that source is its topic source; merged papers
        stay unknown until they are ingested again."""
        cols = {r[1] for r in c.execute("PRAGMA table_info(papers)")}
        if "topic_source" in cols:
            return
        c.execute("ALTER TABLE papers ADD COLUMN topic_source TEXT DEFAULT ''")
        rows = c.execute("SELECT key, sources FROM papers WHERE topic != ''").fetchall()
        for key, sources in rows:
            src = json.loads(sources or "[]")
            if len(src) == 1:
                c.execute("UPDATE papers SET topic_source=? WHERE key=?", (src[0], key))

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

    def coverage_warnings(self, tracked_venues=()) -> list[str]:
        """Plain-language warnings about a corpus too thin to trust. Silent gaps
        (a test fetch with --limit, a source that refused access) otherwise only
        show up as odd numbers in the dashboard."""
        df = self.summary()
        out = []
        conf = df[df.venue != "arxiv"]
        for v in sorted(set(tracked_venues) - set(conf.venue)):
            out.append(f"{v}: tracked but has no papers. Run `radar ingest venues --venues {v} ...`.")
        for venue, g in conf.groupby("venue"):
            peak = g.n.max()
            for r in g.itertuples():
                if r.n < 150:
                    out.append(f"{venue} {r.year}: only {r.n} papers. Either a test fetch (--limit) or the "
                               f"proceedings are not indexed yet; re-ingest without --limit, or wait and run "
                               f"`radar update`.")
                elif r.n < 0.4 * peak:
                    out.append(f"{venue} {r.year}: {r.n} papers vs {peak} in its largest year; "
                               f"probably incomplete (or still being indexed).")
                if r.n >= 150 and r.with_abstract < 0.5 * r.n:
                    out.append(f"{venue} {r.year}: only {r.with_abstract}/{r.n} papers have abstracts; "
                               f"topics will lean on titles for this year (abstracts often fill in later).")
        if len(conf) and conf.highlighted.sum() == 0:
            out.append("No oral/spotlight decisions in the corpus, so reward lift is unavailable "
                       "(needs OpenReview or the RTanalysis import).")
        n_conf, n_arx = int(conf.n.sum()), int(df[df.venue == "arxiv"].n.sum())
        if n_arx and n_arx > n_conf:
            out.append(f"arXiv ({n_arx:,}) outnumbers conference papers ({n_conf:,}); topics will mostly "
                       f"reflect arXiv while trend scores use conference papers only.")
        return out

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
    for col in ("abstract", "presentation", "topic", "topic_source", "url", "doi", "arxiv_id", "date"):
        out[col] = (out[col] or "").strip() if isinstance(out[col], str) else (out[col] or "")
    out["topic_source"] = (out["topic_source"] or source) if out["topic"] else ""
    out["paper_type"] = out["paper_type"] or "main"
    if out["citations"] is not None:
        out["citations"] = int(out["citations"])
    return out


def _merge(old: dict, new: dict) -> dict:
    m = dict(old)
    old_is_preprint = old.get("venue") == "arxiv"
    # Keep the topic from the most authoritative taxonomy; on a tie, the
    # longer label (the general rule below).
    o_rank, n_rank = _topic_rank(old.get("topic_source") or ""), _topic_rank(new.get("topic_source") or "")
    if n_rank > o_rank or (n_rank == o_rank and len(new.get("topic") or "") > len(old.get("topic") or "")):
        m["topic"], m["topic_source"] = new.get("topic") or "", new.get("topic_source") or ""
    for k in COLUMNS:
        if k in ("key", "sources", "topic", "topic_source"):
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
