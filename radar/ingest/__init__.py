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


RECENT_MAX_AGE = 5 * 86400  # re-fetch the current and previous year at most every 5 days


def get_tracking(db: DB) -> dict:
    return db.get_meta("tracking", None) or {"venues": [], "sources": [], "from_year": None, "arxiv": None}


def track(db: DB, venues=(), sources=(), from_year=None, arxiv_categories=None, untrack=()) -> dict:
    """Remember what to keep up to date. `radar update` uses this."""
    t = get_tracking(db)
    t["venues"] = sorted((set(t["venues"]) | set(venues)) - set(untrack))
    t["sources"] = sorted(set(t["sources"]) | set(sources))
    if from_year:
        t["from_year"] = min(from_year, t["from_year"] or from_year)
    if arxiv_categories:
        a = t.get("arxiv") or {"categories": [], "last_date": None}
        a["categories"] = sorted(set(a["categories"]) | set(arxiv_categories))
        t["arxiv"] = a
    db.set_meta("tracking", t)
    return t


def ingest_venues(s: Settings, db: DB, venues: list[str], years: list[int], sources: list[str],
                  limit: int = 0, log=print, refresh_recent: bool = True, remember: bool = True,
                  recent_from: int | None = None) -> dict:
    """Fetch every (venue, year) from each requested source. A source that fails
    is reported and skipped; the others still run, and cross-source duplicates
    merge in the database.

    Cached responses for years >= `recent_from` (default: the previous year) are
    re-fetched once they are older than RECENT_MAX_AGE; older years are served
    from the cache."""
    if recent_from is None:
        recent_from = date.today().year - 1
    stats = {}
    oa_cache = db.get_meta("openalex_sources", {}) or {}
    clients = {
        "openalex": _client(s, "openalex", 0.12),
        "s2": _client(s, "s2", 1.1 if not s.s2_api_key else 0.2,
                      {"x-api-key": s.s2_api_key} if s.s2_api_key else None),
        "openreview": _client(s, "openreview", 0.5),
    }
    blocked: set[str] = set()  # sources that refused this run (e.g. a bot challenge): not retried
    for venue in venues:
        if venue not in VENUES:
            log(f"! unknown venue '{venue}' (known: {', '.join(VENUES)})")
            continue
        for year in years:
            recent = year >= recent_from
            for c in clients.values():
                c.max_age = RECENT_MAX_AGE if (recent and refresh_recent) else None
            for src in sources:
                if src in blocked:
                    continue
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
                    not_applicable = src == "openreview" and not VENUES[venue].get("openreview")
                    if ins + mer == 0 and not not_applicable:
                        log(f"  ! {venue} {year} [{src}] returned no papers (not indexed yet, or the source "
                            f"names this venue differently)")
                except HttpError as e:
                    msg = str(e)
                    if "ChallengeRequired" in msg or "HTTP 401" in msg or "HTTP 403" in msg:
                        blocked.add(src)
                        log(f"  ! {src} refused access (HTTP 401/403{', bot challenge' if 'Challenge' in msg else ''}); "
                            f"skipping {src} for the rest of this run. "
                            + ("OpenReview no longer serves anonymous API clients; use --sources s2,openalex."
                               if src == "openreview" else "Check your API key or try again later."))
                    else:
                        log(f"  {venue} {year} [{src}]: skipped ({msg[:160]})")
                finally:
                    db.set_meta("openalex_sources", oa_cache)
    if remember and not limit:
        track(db, [v for v in venues if v in VENUES], sources, min(years) if years else None)
    return stats


def ingest_arxiv(s: Settings, db: DB, start: date, end: date, categories=None,
                 max_per_window: int = 2000, log=print):
    client = _client(s, "arxiv", 3.1)  # arXiv asks for >= 3 s between calls
    client.max_age = RECENT_MAX_AGE  # the newest window keeps growing
    cats = categories or ARXIV_ML_CATEGORIES
    out = db.upsert_papers(fetch_arxiv(client, cats, start, end, max_per_window, log=log), "arxiv")
    t = track(db, arxiv_categories=cats)
    a = t["arxiv"]
    a["last_date"] = max(filter(None, [a.get("last_date"), str(end)]))
    db.set_meta("tracking", t)
    return out


def ingest_rtanalysis(db: DB, repo: Path):
    return db.upsert_papers(import_rtanalysis(repo), "rtanalysis")


def ingest_file(db: DB, path: Path, venue: str = "", year: int = 0):
    return db.upsert_papers(import_file(path, venue, year), "file")
