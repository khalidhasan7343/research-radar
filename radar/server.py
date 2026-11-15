"""FastAPI backend for the dashboard. Everything is loaded into memory once;
POST /api/reload picks up a fresh analysis run without restarting."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import Settings
from .db import DB
from .trends import opportunity

WEB = Path(__file__).parent / "web"


def records(df: pd.DataFrame) -> list[dict]:
    if df is None or len(df) == 0:
        return []
    return json.loads(df.to_json(orient="records", force_ascii=False))


class State:
    def __init__(self, s: Settings):
        self.s = s
        self.db = DB(s.db_path)
        self.load()

    def load(self):
        db = self.db
        self.papers = db.papers()
        self.pc = db.read_table("paper_cluster")
        self.ready = len(self.pc) > 0 and db.has_table("trends")
        if not self.ready:
            return
        self.clusters = db.read_table("clusters", ("keywords", "representatives"))
        self.themes = db.read_table("themes", ("keywords", "clusters"))
        self.trends = db.read_table("trends")
        self.cy = db.read_table("cluster_year")
        self.terms = db.read_table("terms", ("counts", "per_1000"))
        self.op = db.read_table("open_problems")
        self.claims = db.read_table("position_claims")
        self.tp = db.read_table("transplants")
        self.tobs = db.read_table("transplant_observed")
        self.texp = db.read_table("transplant_expected")
        self.bridges = db.read_table("bridges")
        self.bridge_papers = db.read_table("bridge_papers")
        self.ideas = db.read_table("ideas", ("nearest",))
        self.p = self.papers.merge(self.pc, on="key", how="left").set_index("key", drop=False)
        self.label = dict(zip(self.clusters.cluster, self.clusters.label))
        self._ix = None

    @property
    def ix(self):
        if self._ix is None:
            from .ideas import Index

            self._ix = Index(self.s, self.papers, self.pc, np.load(self.s.emb_dir / "centroids.npy"))
        return self._ix

    def paper_brief(self, keys, extra: pd.DataFrame | None = None) -> list[dict]:
        keys = [k for k in keys if k in self.p.index]
        df = self.p.loc[keys, ["key", "title", "venue", "year", "presentation", "url", "citations", "cluster", "authors"]].reset_index(drop=True)
        df["authors"] = df.authors.map(lambda a: a[:6] if isinstance(a, list) else [])
        df["topic"] = df.cluster.map(self.label)
        if extra is not None:
            df = df.merge(extra, left_on="key", right_index=True, how="left")
        return records(df)


class TextReq(BaseModel):
    text: str = ""
    k: int = 25
    cluster: int | None = None


class IdeaReq(BaseModel):
    title: str
    rationale: str = ""


class WeightsReq(BaseModel):
    weights: dict


def create_app(s: Settings) -> FastAPI:
    st = State(s)
    app = FastAPI(title="Research Radar")

    def need():
        if not st.ready:
            raise HTTPException(409, "No analysis yet. Run `radar ingest ...` then `radar analyze`.")

    @app.get("/api/overview")
    def overview():
        summ = st.db.summary()
        out = {"ready": st.ready, "summary": records(summ), "n_papers": int(summ.n.sum()) if len(summ) else 0,
               "llm": {"enabled": s.llm_enabled, "model": s.llm_model},
               "cluster_info": st.db.get_meta("cluster_info"), "trend_info": st.db.get_meta("trend_info"),
               "last_run": st.db.get_meta("last_run"), "weights": st.db.get_meta("weights") or s.weights}
        if st.ready:
            tr = st.trends
            out["top_opportunity"] = records(tr.sort_values("opportunity", ascending=False).head(8))
            out["fastest"] = records(tr[tr.n_total >= 30].sort_values("momentum", ascending=False).head(8))
            out["cooling"] = records(tr[tr.n_total >= 30].sort_values("momentum").head(6))
            out["new_terms"] = records(st.terms[st.terms.status != "fading"].head(24))
            out["tags"] = tr.tag.value_counts().to_dict()
            out["n_topics"] = len(tr)
            out["n_open_problems"] = len(st.op)
            out["n_ideas"] = len(st.ideas)
        return out

    @app.get("/api/topics")
    def topics():
        need()
        series = {int(c): g.sort_values("year")[["year", "n", "share"]].to_dict("records") for c, g in st.cy.groupby("cluster")}
        tr = st.trends.merge(st.clusters[["cluster", "keywords", "summary", "size", "cx", "cy"]], on="cluster")
        return {"topics": records(tr), "series": series, "themes": records(st.themes)}

    @app.post("/api/rescore")
    def rescore(req: WeightsReq):
        need()
        tr = opportunity(st.trends.drop(columns=[c for c in st.trends if c.startswith("pct_")] + ["opportunity"]),
                         req.weights)
        return records(tr[["cluster", "opportunity"]])

    @app.get("/api/topics/{cid}")
    def topic(cid: int):
        need()
        if cid not in st.label:
            raise HTTPException(404)
        tr = st.trends[st.trends.cluster == cid].iloc[0].to_dict()
        cl = st.clusters[st.clusters.cluster == cid].iloc[0].to_dict()
        members = st.p[(st.p.cluster == cid)]
        rich = members[members.abstract.str.len() > 100]
        central = rich.sort_values("confidence", ascending=False).key.head(15).tolist()
        hl = rich[rich.presentation.isin(["oral", "spotlight"])].sort_values("confidence", ascending=False).key.head(15).tolist()
        cited = rich.dropna(subset=["citations"]).sort_values("citations", ascending=False).key.head(15).tolist()
        recent = rich.sort_values(["year", "date"], ascending=False).key.head(15).tolist()
        ops = st.op[st.op.cluster == cid].sort_values("year", ascending=False)
        ops = ops.merge(st.papers[["key", "title", "url"]], on="key", how="left")
        claims = st.claims[st.claims.cluster == cid]
        cent = st.ix.centroids
        sims = cent @ cent[cid]
        near = [int(c) for c in np.argsort(-sims)[1:7]]
        bp = st.bridge_papers[(st.bridge_papers.cluster == cid) | (st.bridge_papers.cluster2 == cid)].head(12)
        bp_extra = bp.set_index("key")[["cluster2", "margin"]]
        venues = members[members.venue != "arxiv"].groupby(["venue", "year"]).size().rename("n").reset_index()
        authors = pd.Series([a for al in rich.authors for a in al]).value_counts().head(12)
        series = st.cy[st.cy.cluster == cid].sort_values("year")[["year", "n", "share", "n_all"]]
        return {
            "metrics": json.loads(pd.Series(tr).to_json()), "cluster": json.loads(pd.Series(cl).to_json()),
            "series": records(series), "venues": records(venues),
            "papers": {"central": st.paper_brief(central), "highlighted": st.paper_brief(hl),
                       "cited": st.paper_brief(cited), "recent": st.paper_brief(recent)},
            "open_problems": records(ops.head(60)), "n_open_problems": len(ops),
            "claims": records(claims.head(20)),
            "neighbours": [{"cluster": c, "label": st.label[c], "similarity": round(float(sims[c]), 3)} for c in near],
            "bridge_papers": [dict(p, other_topic=st.label.get(int(p["cluster2"]) if p["cluster"] == cid else int(p["cluster"])))
                              for p in st.paper_brief(bp.key.tolist(), bp_extra)],
            "top_authors": [{"name": k, "n": int(v)} for k, v in authors.items()],
        }

    @app.get("/api/map")
    def map_points(theme: int | None = None):
        need()
        m = st.p.dropna(subset=["x"])
        if theme is not None:
            m = m[m.theme == theme]
        return {"x": m.x.round(3).tolist(), "y": m.y.round(3).tolist(), "c": m.cluster.astype(int).tolist(),
                "t": m.theme.astype(int).tolist(), "year": m.year.astype(int).tolist(),
                "hl": m.presentation.isin(["oral", "spotlight"]).astype(int).tolist(),
                "title": m.title.str.slice(0, 140).tolist(), "key": m.key.tolist(),
                "labels": records(st.clusters[["cluster", "label", "cx", "cy", "theme", "size"]])}

    @app.get("/api/terms")
    def terms():
        need()
        return records(st.terms)

    @app.get("/api/term")
    def term(q: str):
        need()
        from .terms import term_series

        return term_series(st.papers, q)

    @app.get("/api/gaps")
    def gaps():
        need()
        br = st.bridges.copy()
        if len(br):
            br["label_a"] = br.a.map(st.label)
            br["label_b"] = br.b.map(st.label)
        return {"transplants": records(st.tp.head(300)), "observed": records(st.tobs), "expected": records(st.texp),
                "bridges": records(br), "claims": records(st.claims.merge(st.papers[["key", "url"]], on="key", how="left")),
                "open_problem_kinds": st.op.kind.value_counts().to_dict()}

    @app.get("/api/open_problems")
    def open_problems(q: str = "", cluster: int | None = None, kind: str = "", limit: int = 100):
        need()
        op = st.op
        if cluster is not None:
            op = op[op.cluster == cluster]
        if kind:
            op = op[op.kind == kind]
        if q:
            op = op[op.sentence.str.contains(q, case=False, regex=False)]
        op = op.sort_values("year", ascending=False).head(limit).merge(st.papers[["key", "title", "url"]], on="key", how="left")
        op["topic"] = op.cluster.map(st.label)
        return {"n": int(len(op)), "items": records(op)}

    @app.get("/api/search")
    def search(q: str, k: int = 30):
        need()
        res = st.ix.search(q, k)
        return st.paper_brief(res.key.tolist(), res.set_index("key")[["similarity"]])

    @app.post("/api/novelty")
    def novelty(req: TextReq):
        need()
        if len(req.text.strip()) < 10:
            raise HTTPException(400, "Describe the idea in at least a sentence.")
        n = st.ix.novelty(req.text, req.k)
        nb = n.pop("neighbours")
        n["neighbours"] = st.paper_brief(nb.key.tolist(), nb.set_index("key")[["similarity"]])
        tr = st.trends.set_index("cluster")
        for c in n["clusters"]:
            r = tr.loc[c["cluster"]]
            c.update(label=st.label[c["cluster"]], momentum=float(r.momentum), competition=int(r.competition),
                     opportunity=float(r.opportunity), tag=r.tag)
        cids = [c["cluster"] for c in n["clusters"][:2]]
        ops = st.op[st.op.cluster.isin(cids) & st.op.kind.isin(["open_question", "missing_eval", "limitation"])]
        if len(ops):
            q = st.ix.encode(req.text)
            pos = {k: i for i, k in enumerate(st.ix.papers.key)}
            rows = [pos.get(k) for k in ops.key]
            ok = [r is not None for r in rows]
            ops = ops[ok].copy()
            ops["sim"] = st.ix.X[[r for r in rows if r is not None]] @ q
            ops = ops.sort_values("sim", ascending=False).drop_duplicates("key").head(10)
            ops = ops.merge(st.papers[["key", "title", "url"]], on="key", how="left")
        n["open_problems"] = records(ops)
        return n

    @app.post("/api/reading")
    def reading(req: TextReq):
        need()
        from .ideas import reading_list

        rl = reading_list(st.ix, req.text or None, req.cluster)
        return {"clusters": [{"cluster": c, "label": st.label[c]} for c in rl["clusters"]],
                "tiers": {t: st.paper_brief(df.key.tolist()) for t, df in rl["tiers"].items()}}

    @app.get("/api/ideas")
    def ideas():
        need()
        out = records(st.ideas)
        for i in out:
            i["nearest_papers"] = st.paper_brief(i.get("nearest") or [])[:3]
            i["topic"] = st.label.get(i.get("cluster", -1))
        return out

    @app.post("/api/ideas/refine")
    def refine(req: IdeaReq):
        need()
        from .llm import LLMUnavailable, refine_idea

        n = st.ix.novelty(req.title + ". " + req.rationale[:200], 10)
        nb = n["neighbours"]
        neighbours = [{"title": r.title, "venue": r.venue, "year": r.year, "similarity": r.similarity} for r in nb.itertuples()]
        cids = [c["cluster"] for c in n["clusters"][:2]]
        ops = st.op[st.op.cluster.isin(cids) & (st.op.kind == "open_question")].sentence.head(8).tolist()
        try:
            out = refine_idea(s, {"title": req.title, "rationale": req.rationale}, neighbours, ops)
        except LLMUnavailable as e:
            return JSONResponse({"error": str(e), "neighbours": neighbours[:5], "novelty": n["novelty"]}, status_code=200)
        return {"refined": out, "novelty": n["novelty"], "neighbours": neighbours[:5]}

    @app.get("/api/paper/{key:path}")
    def paper(key: str):
        need()
        if key not in st.p.index:
            raise HTTPException(404)
        r = st.p.loc[key]
        d = json.loads(r[["key", "title", "abstract", "venue", "year", "presentation", "url", "citations", "topic",
                          "cluster", "cluster2", "confidence", "margin", "arxiv_id", "doi"]].to_json())
        d["authors"] = r.authors
        d["topic_label"] = st.label.get(int(r.cluster)) if pd.notna(r.cluster) else None
        d["topic2_label"] = st.label.get(int(r.cluster2)) if pd.notna(r.cluster2) else None
        d["open_problems"] = st.op[st.op.key == key].sentence.tolist()
        return d

    @app.post("/api/reload")
    def reload():
        st.load()
        return {"ready": st.ready}

    app.mount("/static", StaticFiles(directory=WEB), name="static")

    @app.get("/")
    def index():
        return FileResponse(WEB / "index.html")

    return app
