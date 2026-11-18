"""Keep the corpus current and say what changed.

`radar update` re-fetches the current and previous year for every tracked
venue (new proceedings appear in OpenAlex / OpenReview over several weeks),
pulls arXiv since the last run, re-runs the analysis, and writes a
"what's new" diff:

  * new releases      venue-years that did not exist before (e.g. NeurIPS 2026)
  * new papers        per venue-year counts that grew
  * new topics        clusters whose papers were mostly not in any old topic
  * movers            topics whose momentum / opportunity changed the most
  * new vocabulary    emerging terms that were not on the previous list

Topic ids change every time clustering re-runs, so topics are matched old ->
new by the papers they share, not by id.
"""
from __future__ import annotations

import json
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from .config import Settings
from .db import DB


def snapshot(db: DB) -> dict | None:
    if not db.has_table("trends"):
        return None
    tr = db.read_table("trends")
    terms = db.read_table("terms")
    return {
        "date": db.get_meta("last_run"),
        "summary": db.summary(),
        "pc": db.read_table("paper_cluster")[["key", "cluster"]],
        "trends": tr[["cluster", "label", "momentum", "opportunity", "competition", "tag"]].copy(),
        "terms": set(terms[terms.status != "fading"].term) if len(terms) else set(),
    }


def diff(old: dict | None, db: DB) -> dict:
    now = db.summary()
    out = {"date": time.strftime("%Y-%m-%d %H:%M"), "since": old["date"] if old else None,
           "n_papers": int(now.n.sum()), "new_releases": [], "grown": [], "new_topics": [], "movers": [],
           "new_terms": []}
    if old is None:
        out["first_run"] = True
        return out
    o = old["summary"].set_index(["venue", "year"]).n
    for r in now.itertuples():
        before = int(o.get((r.venue, r.year), 0))
        if before == 0:
            out["new_releases"].append({"venue": r.venue, "year": int(r.year), "n": int(r.n)})
        elif r.n > before:
            out["grown"].append({"venue": r.venue, "year": int(r.year), "before": before, "n": int(r.n)})
    out["n_new_papers"] = int(now.n.sum() - old["summary"].n.sum())

    tr = db.read_table("trends")
    pc = db.read_table("paper_cluster")[["key", "cluster"]]
    m = pc.merge(old["pc"], on="key", suffixes=("", "_old"))
    otr = old["trends"].set_index("cluster")
    old_rank = otr.opportunity.rank(ascending=False)
    new_rank = tr.set_index("cluster").opportunity.rank(ascending=False)
    groups = dict(tuple(m.groupby("cluster")))
    for c in tr.cluster:
        g = groups.get(c, m.iloc[0:0])  # a topic made only of new papers has no overlap at all
        vc = g.cluster_old.value_counts()
        size_new = int((pc.cluster == c).sum())
        r = tr[tr.cluster == c].iloc[0]
        frac_known = len(g) / max(size_new, 1)  # share of this topic's papers that existed before
        match_share = vc.iloc[0] / max(len(g), 1) if len(vc) else 0.0
        # New = mostly new papers, or old papers that used to be scattered across topics.
        if frac_known < 0.3 or match_share < 0.4:
            out["new_topics"].append({"cluster": int(c), "label": r.label, "size": size_new,
                                      "new_paper_share": round(1 - frac_known, 2), "momentum": float(r.momentum)})
            continue
        oc = int(vc.index[0])
        if oc not in otr.index:
            continue
        ob = otr.loc[oc]
        out["movers"].append({
            "cluster": int(c), "label": r.label, "old_label": ob.label,
            "momentum_before": float(ob.momentum), "momentum": float(r.momentum),
            "opportunity_before": float(ob.opportunity), "opportunity": float(r.opportunity),
            "rank_before": int(old_rank[oc]), "rank": int(new_rank[c]),
            "tag_before": ob.tag, "tag": r.tag,
        })
    mv = pd.DataFrame(out["movers"])
    if len(mv):
        mv["delta"] = (mv.opportunity - mv.opportunity_before).abs() + 10 * (mv.momentum - mv.momentum_before).abs()
        mv = mv[(mv.delta >= 3) | (mv.tag != mv.tag_before)]
        out["movers"] = mv.sort_values("delta", ascending=False).drop(columns="delta").head(15).to_dict("records")
    terms = db.read_table("terms")
    if len(terms):
        fresh = terms[(terms.status != "fading") & ~terms.term.isin(old["terms"])]
        out["new_terms"] = fresh.term.head(20).tolist()
    return out


def changes_markdown(ch: dict) -> str:
    L = [f"# What's new — {ch['date']}", ""]
    if ch.get("first_run"):
        return "\n".join(L + ["First analysis; nothing to compare with yet."])
    L.append(f"Since {ch['since']}: **{ch.get('n_new_papers', 0):,} new papers** ({ch['n_papers']:,} total).")
    L.append("")
    if ch["new_releases"]:
        L += ["## New releases", ""] + [f"- **{r['venue'].upper()} {r['year']}** — {r['n']:,} papers" for r in ch["new_releases"]] + [""]
    if ch["grown"]:
        L += ["## Updated", ""] + [f"- {r['venue'].upper()} {r['year']}: {r['before']:,} → {r['n']:,}" for r in ch["grown"]] + [""]
    if ch["new_topics"]:
        L += ["## New topics", ""] + [f"- {t['label']} — {t['size']} papers, {t['new_paper_share']:.0%} of them new, momentum ×{t['momentum']:.2f}"
                                       for t in ch["new_topics"]] + [""]
    if ch["movers"]:
        L += ["## Biggest movers", "", "| topic | momentum | opportunity | rank | signal |", "|---|---|---|---|---|"]
        for t in ch["movers"]:
            sig = t["tag"] if t["tag"] == t["tag_before"] else f"{t['tag_before']} → **{t['tag']}**"
            L.append(f"| {t['label']} | ×{t['momentum_before']:.2f} → ×{t['momentum']:.2f} | "
                     f"{t['opportunity_before']:.0f} → {t['opportunity']:.0f} | #{t['rank_before']} → #{t['rank']} | {sig} |")
        L.append("")
    if ch["new_terms"]:
        L += ["## New on the emerging-terms list", "", ", ".join(ch["new_terms"]), ""]
    if not (ch["new_releases"] or ch["grown"] or ch["new_topics"] or ch["movers"] or ch["new_terms"]):
        L.append("No meaningful changes.")
    return "\n".join(L)


def run_update(s: Settings, db: DB, force: bool = False, years_back: int = 1, out_dir: Path = Path("reports"),
               log=print) -> dict:
    from . import pipeline
    from .ingest import get_tracking, ingest_arxiv, ingest_venues
    from .report import build_report

    t = get_tracking(db)
    if not t["venues"] and not t.get("arxiv"):
        raise SystemExit("Nothing is tracked yet. Ingest something first (it is tracked automatically), or run\n"
                         "  radar track --venues neurips,icml,iclr --sources s2,openalex --from-year 2023")
    before = db.count()
    old = snapshot(db)
    this = date.today().year
    years = list(range(this - years_back, this + 1))
    if t["venues"]:
        log(f"checking {', '.join(v.upper() for v in t['venues'])} for {years[0]}–{years[-1]} via {', '.join(t['sources'])}")
        # Every year being re-checked must bypass old cached responses, not
        # just the current and previous one, or --years-back > 1 finds nothing.
        ingest_venues(s, db, t["venues"], years, t["sources"] or ["openalex"], log=log, remember=False,
                      recent_from=years[0])
    a = t.get("arxiv")
    if a:
        start = date.fromisoformat(a["last_date"]) - timedelta(days=2) if a.get("last_date") else date.today() - timedelta(days=30)
        log(f"arXiv {start} → {date.today()}")
        ingest_arxiv(s, db, start, date.today(), a["categories"], log=log)
    new = db.count() - before
    log(f"{new:,} new papers")
    if new == 0 and not force and old is not None:
        ch = {"date": time.strftime("%Y-%m-%d %H:%M"), "since": old["date"], "n_papers": db.count(), "n_new_papers": 0,
              "new_releases": [], "grown": [], "new_topics": [], "movers": [], "new_terms": [], "no_change": True}
        _record(db, ch, out_dir)
        return ch
    pipeline.run(s, db, log=log)
    ch = diff(old, db)
    _record(db, ch, out_dir)
    build_report(db, out_dir)
    return ch


def _record(db: DB, ch: dict, out_dir: Path):
    db.set_meta("changes", ch)
    hist = db.get_meta("update_history", []) or []
    hist.append({"date": ch["date"], "n_papers": ch["n_papers"], "n_new": ch.get("n_new_papers", 0),
                 "releases": [f"{r['venue']} {r['year']}" for r in ch.get("new_releases", [])]})
    db.set_meta("update_history", hist[-200:])
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "CHANGES.md").write_text(changes_markdown(ch), encoding="utf-8")
    (out_dir / "changes.json").write_text(json.dumps(ch, indent=1, default=str), encoding="utf-8")
