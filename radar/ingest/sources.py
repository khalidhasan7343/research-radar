"""Paper sources. Every fetcher yields plain dicts in the `papers` schema.

| source           | key needed | gives                                          |
|------------------|------------|------------------------------------------------|
| OpenAlex         | no         | abstracts, authors, institutions, citations    |
| Semantic Scholar | optional   | abstracts, citations, arXiv ids                |
| OpenReview v2    | no         | abstracts, oral/spotlight/poster decisions     |
| arXiv            | no         | preprints (leading indicator), abstracts       |
| RTanalysis       | -          | imports the original repo's committed corpus   |
| CSV / JSONL      | -          | anything else you have                         |
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path
from typing import Iterator

import pandas as pd

from ..text import openalex_abstract
from .http import Client, HttpError
from .venues import VENUES, classify_presentation, venue_key

Log = callable


def _log(msg: str, log=None):
    (log or print)(msg)


# ============================================================== OpenAlex
OPENALEX = "https://api.openalex.org"


def openalex_resolve_source(client: Client, venue: str, cache: dict) -> str | None:
    v = VENUES.get(venue, {})
    query = v.get("openalex") or venue
    if query in cache:
        return cache[query]
    data = client.get_json(f"{OPENALEX}/sources", {"search": query, "per-page": 5})
    results = data.get("results", [])
    # Prefer conference proceedings with the most works.
    results.sort(key=lambda r: (r.get("type") == "conference", r.get("works_count", 0)), reverse=True)
    sid = results[0]["id"].rsplit("/", 1)[-1] if results else None
    cache[query] = sid
    return sid


def parse_openalex_work(w: dict, venue: str) -> dict:
    authors, insts = [], []
    for a in w.get("authorships", []) or []:
        name = (a.get("author") or {}).get("display_name")
        if name:
            authors.append(name)
        for i in a.get("institutions", []) or []:
            if i.get("display_name") and i["display_name"] not in insts:
                insts.append(i["display_name"])
    ids = w.get("ids") or {}
    arxiv = ""
    for loc in w.get("locations", []) or []:
        url = (loc.get("landing_page_url") or "")
        m = re.search(r"arxiv\.org/abs/([\w.\-/]+?)(v\d+)?$", url)
        if m:
            arxiv = m.group(1)
    return {
        "key": "openalex:" + (w.get("id") or "").rsplit("/", 1)[-1],
        "title": w.get("title") or w.get("display_name") or "",
        "abstract": openalex_abstract(w.get("abstract_inverted_index")),
        "authors": authors,
        "institutions": insts,
        "venue": venue,
        "year": w.get("publication_year"),
        "url": (w.get("primary_location") or {}).get("landing_page_url") or ids.get("doi") or "",
        "doi": (w.get("doi") or "").replace("https://doi.org/", ""),
        "arxiv_id": arxiv,
        "citations": w.get("cited_by_count"),
        "date": w.get("publication_date") or "",
        "topic": ((w.get("primary_topic") or {}).get("display_name")) or "",
    }


def fetch_openalex(client: Client, venue: str, year: int, cache: dict, limit: int = 0, log=None) -> Iterator[dict]:
    sid = openalex_resolve_source(client, venue, cache)
    if not sid:
        _log(f"  openalex: no source found for {venue}", log)
        return
    cursor, n = "*", 0
    select = ("id,doi,title,display_name,publication_year,publication_date,abstract_inverted_index,"
              "authorships,cited_by_count,primary_location,locations,ids,primary_topic")
    while cursor:
        data = client.get_json(f"{OPENALEX}/works", {
            "filter": f"primary_location.source.id:{sid},publication_year:{year}",
            "per-page": 200, "cursor": cursor, "select": select,
        })
        for w in data.get("results", []):
            yield parse_openalex_work(w, venue)
            n += 1
            if limit and n >= limit:
                return
        cursor = (data.get("meta") or {}).get("next_cursor")
        if not data.get("results"):
            break


# ======================================================= Semantic Scholar
S2 = "https://api.semanticscholar.org/graph/v1"


def parse_s2_paper(p: dict, venue: str) -> dict:
    ext = p.get("externalIds") or {}
    return {
        "key": "s2:" + (p.get("paperId") or ""),
        "title": p.get("title") or "",
        "abstract": p.get("abstract") or "",
        "authors": [a.get("name") for a in (p.get("authors") or []) if a.get("name")],
        "venue": venue,
        "year": p.get("year"),
        "url": p.get("url") or "",
        "doi": ext.get("DOI") or "",
        "arxiv_id": ext.get("ArXiv") or "",
        "citations": p.get("citationCount"),
        "date": p.get("publicationDate") or "",
    }


def fetch_semantic_scholar(client: Client, venue: str, year: int, limit: int = 0, log=None) -> Iterator[dict]:
    v = VENUES.get(venue, {}).get("s2") or venue
    token, n = None, 0
    fields = "title,abstract,authors,year,venue,citationCount,externalIds,url,publicationDate"
    while True:
        params = {"venue": v, "year": str(year), "fields": fields}
        if token:
            params["token"] = token
        data = client.get_json(f"{S2}/paper/search/bulk", params)
        for p in data.get("data", []) or []:
            yield parse_s2_paper(p, venue)
            n += 1
            if limit and n >= limit:
                return
        token = data.get("token")
        if not token:
            break


# ============================================================ OpenReview
OPENREVIEW = "https://api2.openreview.net"


def _orv(content: dict, k: str):
    v = content.get(k)
    return v.get("value") if isinstance(v, dict) else v


def parse_openreview_note(n: dict, venue: str, year: int) -> dict | None:
    c = n.get("content") or {}
    venue_str = _orv(c, "venue") or ""
    if not venue_str or "submitted" in venue_str.lower() or "withdrawn" in venue_str.lower() \
            or "rejected" in venue_str.lower():
        return None
    title = _orv(c, "title") or ""
    return {
        "key": f"openreview:{n.get('id')}",
        "title": title,
        "abstract": _orv(c, "abstract") or "",
        "authors": _orv(c, "authors") or [],
        "venue": venue,
        "year": year,
        "presentation": classify_presentation(venue_str),
        "paper_type": "position" if title.lower().startswith("position:") else "main",
        "topic": _orv(c, "primary_area") or "",
        "url": f"https://openreview.net/forum?id={n.get('id')}",
    }


def fetch_openreview(client: Client, venue: str, year: int, limit: int = 0, log=None) -> Iterator[dict]:
    tmpl = VENUES.get(venue, {}).get("openreview")
    if not tmpl:
        _log(f"  openreview: {venue} does not use OpenReview", log)
        return
    vid = tmpl.format(year=year)
    offset, n = 0, 0
    while True:
        data = client.get_json(f"{OPENREVIEW}/notes", {"content.venueid": vid, "limit": 1000, "offset": offset})
        notes = data.get("notes", [])
        for note in notes:
            p = parse_openreview_note(note, venue, year)
            if p:
                yield p
                n += 1
                if limit and n >= limit:
                    return
        if len(notes) < 1000:
            break
        offset += 1000


# ================================================================= arXiv
ARXIV = "https://export.arxiv.org/api/query"
_A = "{http://www.w3.org/2005/Atom}"


def parse_arxiv_feed(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    out = []
    for e in root.findall(f"{_A}entry"):
        aid = (e.findtext(f"{_A}id") or "").rsplit("/abs/", 1)[-1]
        aid = re.sub(r"v\d+$", "", aid)
        published = (e.findtext(f"{_A}published") or "")[:10]
        title = re.sub(r"\s+", " ", e.findtext(f"{_A}title") or "").strip()
        if not aid or not title:
            continue
        out.append({
            "key": f"arxiv:{aid}",
            "title": title,
            "abstract": re.sub(r"\s+", " ", e.findtext(f"{_A}summary") or "").strip(),
            "authors": [a.findtext(f"{_A}name") for a in e.findall(f"{_A}author")],
            "venue": "arxiv",
            "year": int(published[:4]) if published else 0,
            "paper_type": "preprint",
            "url": f"https://arxiv.org/abs/{aid}",
            "arxiv_id": aid,
            "date": published,
            "topic": ",".join(c.get("term") for c in e.findall(f"{_A}category")),
        })
    return out


def fetch_arxiv(client: Client, categories: list[str], start: date, end: date,
                max_per_window: int = 2000, window_days: int = 7, log=None) -> Iterator[dict]:
    cat_q = " OR ".join(f"cat:{c}" for c in categories)
    d = start
    while d <= end:
        e = min(d + timedelta(days=window_days - 1), end)
        q = f"({cat_q}) AND submittedDate:[{d:%Y%m%d}0000 TO {e:%Y%m%d}2359]"
        offset = 0
        while offset < max_per_window:
            text = client.get(ARXIV, {"search_query": q, "start": offset, "max_results": 200,
                                      "sortBy": "submittedDate", "sortOrder": "ascending"})
            batch = parse_arxiv_feed(text)
            yield from batch
            if len(batch) < 200:
                break
            offset += 200
        _log(f"  arxiv {d}..{e}: window done", log)
        d = e + timedelta(days=1)


# ============================================================ RTanalysis
def import_rtanalysis(repo: Path) -> Iterator[dict]:
    """Import the committed corpus of github.com/Faysal-star/RTanalysis."""
    clean = Path(repo) / "10_corpus" / "clean"
    papers = pd.read_parquet(clean / "papers.parquet")
    seen = set()
    for r in papers.itertuples(index=False):
        venue = venue_key(r.venue)
        seen.add((r.venue, int(r.year), str(r.paper_id)))
        yield {
            "key": f"{r.venue}{int(r.year)}:{r.paper_id}",
            "title": r.title or r.index_title,
            "abstract": r.abstract or "",
            "authors": list(r.authors) if r.authors is not None else [],
            "venue": venue, "year": int(r.year),
            "presentation": r.presentation or "",
            "paper_type": r.paper_type or "main",
            "topic": r.primary_topic or "",
            "url": r.url or "",
            "date": r.date_published or "",
        }
    titles = pd.read_parquet(clean / "titles_by_year.parquet")
    for r in titles.itertuples(index=False):
        if (r.venue, int(r.year), str(r.paper_id)) in seen:
            continue
        yield {
            "key": f"{r.venue}{int(r.year)}:{r.paper_id}",
            "title": r.title, "venue": venue_key(r.venue), "year": int(r.year),
            "paper_type": "position" if str(r.title).lower().startswith("position:") else "main",
        }


# ================================================================= files
FILE_ALIASES = {
    "abstract": ["abstract", "summary", "abstracttext"],
    "title": ["title", "paper_title", "name"],
    "authors": ["authors", "author", "author_list"],
    "year": ["year", "publication_year"],
    "venue": ["venue", "conference", "journal", "source"],
    "citations": ["citations", "citationcount", "cited_by_count", "n_citations"],
    "presentation": ["presentation", "decision", "track", "type"],
    "url": ["url", "link", "pdf"],
}


def import_file(path: Path, default_venue: str = "", default_year: int = 0) -> Iterator[dict]:
    path = Path(path)
    if path.suffix in (".jsonl", ".ndjson"):
        df = pd.read_json(path, lines=True)
    elif path.suffix == ".json":
        df = pd.DataFrame(json.loads(path.read_text(encoding="utf-8")))
    elif path.suffix == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)
    lower = {c.lower().replace(" ", "_"): c for c in df.columns}
    cols = {}
    for field, names in FILE_ALIASES.items():
        for n in names:
            if n in lower:
                cols[field] = lower[n]
                break
    if "title" not in cols:
        raise ValueError(f"{path}: no title column (looked for {FILE_ALIASES['title']})")
    for i, r in enumerate(df.to_dict("records")):
        get = lambda f, d=None: r.get(cols[f], d) if f in cols else d  # noqa: E731
        authors = get("authors", [])
        if isinstance(authors, str):
            authors = [a.strip() for a in re.split(r";|\band\b|,(?![^()]*\))", authors) if a.strip()]
        cit = get("citations")
        venue = venue_key(str(get("venue") or default_venue or "unknown"))
        yield {
            "key": f"file:{path.stem}:{i}",
            "title": str(get("title") or ""),
            "abstract": str(get("abstract") or "") if not pd.isna(get("abstract", "")) else "",
            "authors": list(authors) if authors is not None else [],
            "venue": venue,
            "year": int(get("year") or default_year or 0),
            "citations": int(cit) if cit is not None and not pd.isna(cit) else None,
            "presentation": classify_presentation(str(get("presentation") or "")),
            "url": str(get("url") or ""),
        }


__all__ = [
    "HttpError", "fetch_openalex", "fetch_semantic_scholar", "fetch_openreview",
    "fetch_arxiv", "import_rtanalysis", "import_file", "parse_arxiv_feed",
    "parse_openalex_work", "parse_s2_paper", "parse_openreview_note",
]
