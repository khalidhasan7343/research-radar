"""High-level ingest entry points used by the CLI."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from ..config import Settings
from ..db import DB
from .http import Client, HttpError
from .sources import (fetch_arxiv, fetch_openalex, fetch_openreview, fetch_semantic_scholar,
                      import_file, import_rtanalysis)
from .venues import ARXIV_ML_CATEGORIES, VENUES

SOURCES = ("openalex", "s2", "openreview")


def _client(s: Settings, name: str, interval: float, headers=None) -> Client:
    ua = f"research-radar/1.0 (mailto:{s.contact_email})" if s.contact_email else ""
    return Client(s.cache_dir / name, min_interval=interval, user_agent=ua, headers=headers)


def ingest_venues(s: Settings, db: DB, venues: list[str], years: list[int], sources: list[str],
                  limit: int = 0, log=print) -> dict:
    """Fetch every (venue, year) from each requested source. A source that fails
    is reported and skipped; the others still run, and cross-source duplicates
    merge in the database."""
    stats = {}
    oa_cache = db.get_meta("openalex_sources", {}) or {}
    clients = {
        "openalex": _client(s, "openalex", 0.12),
        "s2": _client(s, "s2", 1.1 if not s.s2_api_key else 0.2,
                      {"x-api-key": s.s2_api_key} if s.s2_api_key else None),
        "openreview": _client(s, "openreview", 0.5),
    }
    for venue in venues:
        if venue not in VENUES:
            log(f"! unknown venue '{venue}' (known: {', '.join(VENUES)})")
            continue
        for year in years:
            for src in sources:
                try:
                    if src == "openalex":
                        it = fetch_openalex(clients[src], venue, year, oa_cache, limit, log)
                    elif src == "s2":
                        it = fetch_semantic_scholar(clients[src], venue, year, limit, log)
                    elif src == "openreview":
                        it = fetch_openreview(clients[src], venue, year, limit, log)
                    else:
                        log(f"! unknown source {src}")
                        continue
                    ins, mer = db.upsert_papers(it, src)
                    stats[(venue, year, src)] = (ins, mer)
                    log(f"  {venue} {year} [{src}]: +{ins} new, {mer} merged")
                except HttpError as e:
                    log(f"  {venue} {year} [{src}]: skipped ({str(e)[:160]})")
                finally:
                    db.set_meta("openalex_sources", oa_cache)
    return stats


def ingest_arxiv(s: Settings, db: DB, start: date, end: date, categories=None,
                 max_per_window: int = 2000, log=print):
    client = _client(s, "arxiv", 3.1)  # arXiv asks for >= 3 s between calls
    it = fetch_arxiv(client, categories or ARXIV_ML_CATEGORIES, start, end, max_per_window, log=log)
    return db.upsert_papers(it, "arxiv")


def ingest_rtanalysis(db: DB, repo: Path):
    return db.upsert_papers(import_rtanalysis(repo), "rtanalysis")


def ingest_file(db: DB, path: Path, venue: str = "", year: int = 0):
    return db.upsert_papers(import_file(path, venue, year), "file")
