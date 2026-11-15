"""Command line: `radar <command> ...`  (or `python -m radar ...`)."""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from .config import load_settings
from .db import DB


def _years(spec: str) -> list[int]:
    out = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="radar", description="Research Radar: map a research field and find openings.")
    ap.add_argument("--data", help="data directory (default ./data)")
    ap.add_argument("--config", help="path to radar.toml")
    sub = ap.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("ingest", help="add papers to the corpus")
    isub = i.add_subparsers(dest="src", required=True)
    v = isub.add_parser("venues", help="fetch venue papers from OpenAlex / Semantic Scholar / OpenReview")
    v.add_argument("--venues", required=True, help="comma list, e.g. neurips,icml,iclr,cvpr,acl  (see `radar venues`)")
    v.add_argument("--years", required=True, help="e.g. 2023-2025 or 2024,2025")
    v.add_argument("--sources", default="openalex,openreview", help="comma list of openalex,s2,openreview")
    v.add_argument("--limit", type=int, default=0, help="max papers per venue-year-source (testing)")
    a = isub.add_parser("arxiv", help="fetch recent arXiv preprints (leading indicator)")
    a.add_argument("--start", required=True, help="YYYY-MM-DD")
    a.add_argument("--end", default=str(date.today()))
    a.add_argument("--categories", default="", help="default: cs.LG,cs.AI,cs.CL,cs.CV,cs.RO,stat.ML,...")
    a.add_argument("--max-per-week", type=int, default=2000)
    r = isub.add_parser("rtanalysis", help="import the corpus committed in the RTanalysis repo")
    r.add_argument("path", help="path to a clone of github.com/Faysal-star/RTanalysis")
    f = isub.add_parser("file", help="import a CSV / JSONL / JSON / parquet file")
    f.add_argument("path")
    f.add_argument("--venue", default="")
    f.add_argument("--year", type=int, default=0)

    sub.add_parser("venues", help="list known venues")
    sub.add_parser("status", help="corpus and analysis summary")

    an = sub.add_parser("analyze", help="run the analysis pipeline")
    an.add_argument("--from", dest="start", default="embed",
                    choices=["embed", "cluster", "gaps", "trends", "terms", "ideas"])
    an.add_argument("--only", default="", help="comma list of stages")
    an.add_argument("--backend", help="tfidf | fastembed | sentence-transformers | ollama")
    an.add_argument("--clusters", type=int, help="number of topics (default: automatic)")
    an.add_argument("--layout", help="tsne | umap | pca")
    an.add_argument("--force-embed", action="store_true")

    rp = sub.add_parser("report", help="write TREND_REPORT.md and .html")
    rp.add_argument("--out", default="reports")

    nv = sub.add_parser("novelty", help="how crowded is the neighbourhood of an idea?")
    nv.add_argument("idea")
    nv.add_argument("-k", type=int, default=15)
    rl = sub.add_parser("reading", help="tiered reading list for an idea or topic")
    rl.add_argument("idea", nargs="?")
    rl.add_argument("--cluster", type=int)

    sv = sub.add_parser("serve", help="open the web dashboard")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)

    demo = sub.add_parser("demo", help="build a demo corpus from RTanalysis and analyze it")
    demo.add_argument("path", help="path to a clone of RTanalysis")

    args = ap.parse_args(argv)
    over = {"data_dir": Path(args.data) if args.data else None}
    if args.cmd == "analyze":
        over.update(embed_backend=args.backend, n_clusters=args.clusters, layout=args.layout)
    s = load_settings(args.config, **over)
    s.ensure_dirs()
    db = DB(s.db_path)

    if args.cmd == "venues":
        from .ingest.venues import VENUES

        for k, v in VENUES.items():
            print(f"{k:10s} {v['name']:10s} area={v['area']:9s} openreview={'yes' if v['openreview'] else 'no'}")
    elif args.cmd == "ingest":
        from . import ingest as I

        if args.src == "venues":
            I.ingest_venues(s, db, [x.strip().lower() for x in args.venues.split(",")], _years(args.years),
                            [x.strip() for x in args.sources.split(",")], args.limit)
        elif args.src == "arxiv":
            cats = [c.strip() for c in args.categories.split(",") if c.strip()] or None
            print(I.ingest_arxiv(s, db, date.fromisoformat(args.start), date.fromisoformat(args.end), cats,
                                 args.max_per_week))
        elif args.src == "rtanalysis":
            ins, mer = I.ingest_rtanalysis(db, Path(args.path))
            print(f"imported {ins:,} papers ({mer} merged)")
        else:
            ins, mer = I.ingest_file(db, Path(args.path), args.venue, args.year)
            print(f"imported {ins:,} papers ({mer} merged)")
        print(db.summary().to_string(index=False))
    elif args.cmd == "status":
        print(db.summary().to_string(index=False))
        for k in ("cluster_info", "trend_info", "last_run"):
            print(k, "=", db.get_meta(k))
    elif args.cmd == "analyze":
        from . import pipeline

        if args.force_embed:
            from .pipeline import stage_embed

            stage_embed(s, db, force=True)
            if args.start == "embed":
                args.start = "cluster"
        only = [x.strip() for x in args.only.split(",") if x.strip()] or None
        pipeline.run(s, db, start=args.start, only=only)
    elif args.cmd == "report":
        from .report import build_report

        md, ht = build_report(db, Path(args.out))
        print(f"wrote {md} and {ht}")
    elif args.cmd in ("novelty", "reading"):
        import numpy as np

        from .ideas import Index, reading_list

        ix = Index(s, db.papers(), db.read_table("paper_cluster"), np.load(s.emb_dir / "centroids.npy"))
        if args.cmd == "novelty":
            n = ix.novelty(args.idea, args.k)
            labels = dict(zip(*db.read_table("clusters")[["cluster", "label"]].T.values))
            print(f"novelty {n['novelty']}/100 — {n['verdict']}  (best match similarity {n['best_similarity']})")
            print("nearest topics: " + "; ".join(f"{labels[c['cluster']]} ({c['similarity']})" for c in n["clusters"]))
            for r in n["neighbours"].itertuples():
                print(f"  {r.similarity:.3f}  [{r.venue.upper()} {r.year}] {r.title}")
        else:
            rlist = reading_list(ix, args.idea, args.cluster)
            for tier, df in rlist["tiers"].items():
                print(f"\n## {tier}")
                for r in df.itertuples():
                    print(f"  [{r.venue.upper()} {r.year}{' ' + r.presentation if r.presentation in ('oral', 'spotlight') else ''}] {r.title}  {r.url}")
    elif args.cmd == "serve":
        import uvicorn

        from .server import create_app

        print(f"Research Radar on http://{args.host}:{args.port}")
        uvicorn.run(create_app(s), host=args.host, port=args.port, log_level="warning")
    elif args.cmd == "demo":
        from . import ingest as I
        from . import pipeline
        from .report import build_report

        ins, _ = I.ingest_rtanalysis(db, Path(args.path))
        print(f"imported {ins:,} papers")
        pipeline.run(s, db)
        md, _ = build_report(db, Path("reports"))
        print(f"report: {md}\nnext: radar serve")
    return 0


if __name__ == "__main__":
    sys.exit(main())
