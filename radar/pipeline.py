"""Run the analysis stages in order. Each stage reads from and writes to the
SQLite database, so any stage can be re-run on its own."""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from . import cluster as C
from . import gaps as G
from .config import Settings
from .db import DB
from .embed import EmbeddingStore
from .ideas import Index, generate_ideas
from .terms import emerging_terms
from .trends import compute_trends
from .text import doc_text

STAGES = ["embed", "cluster", "gaps", "trends", "terms", "ideas"]


def _papers(db: DB) -> pd.DataFrame:
    df = db.papers()
    if df.empty:
        raise SystemExit("The database is empty. Run `radar ingest ...` first.")
    return df.reset_index(drop=True)


def stage_embed(s: Settings, db: DB, force=False, log=print):
    df = _papers(db)
    full = [doc_text(t, a) for t, a in zip(df.title, df.abstract)]
    titles = [doc_text(t, None) for t in df.title]
    EmbeddingStore(s).build(df.key.tolist(), full, titles, fit_mask=C.rich_mask(df), force=force, log=log)


def stage_cluster(s: Settings, db: DB, log=print):
    df = _papers(db)
    keys, full, title = EmbeddingStore(s).load()
    if keys != df.key.tolist():
        log("  corpus changed since embedding; re-embedding")
        stage_embed(s, db, log=log)
        keys, full, title = EmbeddingStore(s).load()
    pc, clusters, themes, cent = C.run_clustering(s, df, full, title, log)
    np.save(s.emb_dir / "centroids.npy", cent)
    ami = C.topic_purity(df, pc.cluster.to_numpy())
    db.write_table("paper_cluster", pc)
    db.write_table("clusters", clusters)
    db.write_table("themes", themes)
    db.set_meta("cluster_info", {"k": len(clusters), "themes": len(themes), "ami_vs_official_topics": ami,
                                 "backend": s.embed_backend,
                                 "title_only_assigned": int((pc.space == "title").sum()),
                                 "title_agreement": pc.attrs.get("title_agreement")})
    log(f"  {len(clusters)} clusters in {len(themes)} themes" + (f", AMI vs official topics {ami:.3f}" if ami else ""))
    if s.llm_enabled:
        stage_llm_labels(s, db, log)


def stage_llm_labels(s: Settings, db: DB, log=print):
    from .llm import LLMUnavailable, label_cluster

    clusters = db.read_table("clusters", ("keywords", "representatives"))
    papers = db.papers().set_index("key")
    pc = db.read_table("paper_cluster")
    log(f"  labelling {len(clusters)} clusters with {s.llm_model}")
    labels, sums = [], []
    for r in clusters.itertuples():
        keys = pc[(pc.cluster == r.cluster) & (pc.space == "full")].sort_values("confidence", ascending=False).key.head(12)
        titles = papers.loc[keys, "title"].tolist()
        try:
            out = label_cluster(s, r.keywords, titles)
            labels.append(str(out.get("label") or r.label)[:60])
            sums.append(str(out.get("summary") or ""))
        except LLMUnavailable as e:
            log(f"  ! {e}; keeping keyword labels")
            return
    clusters["label"] = labels
    clusters["summary"] = sums
    db.write_table("clusters", clusters)


def stage_gaps(s: Settings, db: DB, log=print):
    df = _papers(db)
    pc = db.read_table("paper_cluster")
    clusters = db.read_table("clusters", ("keywords",))
    cent = np.load(s.emb_dir / "centroids.npy")
    op = G.extract_open_problems(df, pc)
    claims = G.extract_position_claims(df, pc)
    obs, exp, cells = G.transplant_matrix(df)
    br, bp = G.bridges(pc, cent, clusters)
    db.write_table("open_problems", op)
    db.write_table("position_claims", claims)
    db.write_table("transplants", cells)
    db.write_table("transplant_observed", obs.reset_index().rename(columns={"index": "method"}))
    db.write_table("transplant_expected", exp.reset_index().rename(columns={"index": "method"}))
    db.write_table("bridges", br)
    db.write_table("bridge_papers", bp)
    log(f"  {len(op):,} open-problem sentences, {len(claims)} position claims, "
        f"{len(cells)} method x domain cells, {len(br)} topic pairs")


def stage_trends(s: Settings, db: DB, log=print):
    df = _papers(db)
    pc = db.read_table("paper_cluster")
    clusters = db.read_table("clusters", ("keywords",))
    op = db.read_table("open_problems")
    tr, cy, meta = compute_trends(df, pc, clusters, op, s.weights)
    db.write_table("trends", tr)
    db.write_table("cluster_year", cy)
    db.set_meta("trend_info", meta)
    db.set_meta("weights", s.weights)
    top = tr.sort_values("opportunity", ascending=False).head(5)
    log("  top opportunities: " + "; ".join(f"{r.label} ({r.opportunity:.0f})" for r in top.itertuples()))


def stage_terms(s: Settings, db: DB, log=print):
    terms = emerging_terms(_papers(db))
    db.write_table("terms", terms)
    log(f"  {int((terms.status == 'new').sum()) if len(terms) else 0} new and "
        f"{int((terms.status == 'rising').sum()) if len(terms) else 0} rising terms")


def stage_ideas(s: Settings, db: DB, log=print):
    tr = db.read_table("trends")
    clusters = db.read_table("clusters", ("keywords",))
    ideas = generate_ideas(tr, db.read_table("transplants"), db.read_table("bridges"),
                           db.read_table("open_problems"), clusters)
    if ideas.empty:
        db.write_table("ideas", ideas)
        return
    ix = Index(s, _papers(db), db.read_table("paper_cluster"), np.load(s.emb_dir / "centroids.npy"))
    nov, best, nearest = [], [], []
    for r in ideas.itertuples():
        q = r.title + ". " + r.rationale.split(".")[0]
        n = ix.novelty(q, k=5)
        nov.append(n["novelty"])
        best.append(n["best_similarity"])
        nearest.append(n["neighbours"].key.head(5).tolist())
    ideas["novelty"] = nov
    ideas["best_similarity"] = best
    ideas["nearest"] = nearest
    db.write_table("ideas", ideas)
    log(f"  {len(ideas)} idea seeds")


FUNCS = {"embed": stage_embed, "cluster": stage_cluster, "gaps": stage_gaps, "trends": stage_trends,
         "terms": stage_terms, "ideas": stage_ideas}


def run(s: Settings, db: DB, start: str = "embed", only: list[str] | None = None, log=print):
    todo = only or STAGES[STAGES.index(start):]
    for st in todo:
        t0 = time.time()
        log(f"[{st}]")
        FUNCS[st](s, db, log=log)
        log(f"  ({time.time() - t0:.1f}s)")
    db.set_meta("last_run", time.strftime("%Y-%m-%d %H:%M"))
