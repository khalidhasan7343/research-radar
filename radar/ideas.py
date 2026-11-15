"""Search, novelty checking, reading lists and idea generation."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import SEED, Settings
from .embed import EmbeddingStore


class Index:
    """In-memory semantic index over papers that have abstracts."""

    def __init__(self, s: Settings, papers: pd.DataFrame, pc: pd.DataFrame, centroids: np.ndarray):
        self.s = s
        store = EmbeddingStore(s)
        keys, full, _title = store.load()
        self.backend = store.backend()
        pos = {k: i for i, k in enumerate(keys)}
        p = papers.merge(pc[["key", "cluster", "theme", "space"]], on="key", how="left")
        p = p[p.key.isin(pos)]
        self.papers = p.reset_index(drop=True)
        self.rows = np.array([pos[k] for k in self.papers.key])
        self.X = full[self.rows]
        self.searchable = (self.papers.abstract.fillna("").str.len() > 100).to_numpy()
        if self.searchable.sum() < 100:
            self.searchable[:] = True
        self.centroids = centroids
        self._nn_ref = None

    def encode(self, text: str) -> np.ndarray:
        return self.backend.encode([text])[0]

    def search(self, text: str, k: int = 30, mask: np.ndarray | None = None) -> pd.DataFrame:
        q = self.encode(text)
        sims = self.X @ q
        m = self.searchable if mask is None else (self.searchable & mask)
        sims = np.where(m, sims, -1)
        top = np.argsort(-sims)[:k]
        out = self.papers.iloc[top].copy()
        out["similarity"] = sims[top].round(4)
        return out

    def _reference_nn(self) -> np.ndarray:
        """Nearest-neighbour similarity of random corpus papers to the rest of the
        corpus. A query whose best match is weaker than most papers' best match is
        unusually far from existing work."""
        if self._nn_ref is None:
            rng = np.random.default_rng(SEED)
            idx = np.where(self.searchable)[0]
            samp = rng.choice(idx, min(400, len(idx)), replace=False)
            S = self.X[samp] @ self.X[idx].T
            S[np.arange(len(samp)), np.searchsorted(idx, samp)] = -1
            self._nn_ref = np.sort(S.max(1))
        return self._nn_ref

    def novelty(self, text: str, k: int = 25) -> dict:
        q = self.encode(text)
        nn = self.search(text, k)
        best = float(nn.similarity.iloc[0]) if len(nn) else 0.0
        ref = self._reference_nn()
        # Share of corpus papers whose nearest neighbour is closer than the query's.
        score = float((ref > best).mean())
        csims = self.centroids @ q
        top_c = np.argsort(-csims)[:3]
        top5 = nn.similarity.head(5).mean() if len(nn) else 0
        verdict = ("crowded: very close prior work exists" if score < 0.25 else
                   "incremental: related work is dense" if score < 0.55 else
                   "distinct: sparse neighbourhood" if score < 0.85 else
                   "far from the corpus: check it is in scope, or reword it")
        return {"novelty": round(100 * score, 1), "best_similarity": round(best, 4),
                "mean_top5_similarity": round(float(top5), 4), "verdict": verdict,
                "clusters": [{"cluster": int(c), "similarity": round(float(csims[c]), 4)} for c in top_c],
                "neighbours": nn}


def reading_list(ix: Index, text: str | None = None, cluster: int | None = None, per_tier: int = 12) -> dict:
    """Tiered reading list. Every tier is ranked by relevance (similarity to the
    idea, or centrality in the topic) blended with prominence (citations or
    oral/spotlight), and no paper appears in two tiers."""
    p = ix.papers
    if text:
        q = ix.encode(text)
        rel_all = ix.X @ q
        nn = ix.search(text, 80)
        clusters = list(dict.fromkeys(nn.cluster.dropna().astype(int).head(20)))[:3]
    else:
        clusters = [int(cluster)]
        C = ix.centroids[clusters[0]]
        rel_all = ix.X @ C
        nn = None
    m = (p.cluster.isin(clusters) & ix.searchable).to_numpy()
    pool = p[m].copy()
    pool["relevance"] = rel_all[m]
    if pool.citations.notna().mean() > 0.3:
        prom = pool.groupby("year").citations.rank(pct=True).fillna(0)
    else:
        prom = pool.presentation.map({"oral": 1.0, "spotlight": 0.7}).fillna(0.0)
    pool["prominence"] = prom
    r = pool.relevance.rank(pct=True)
    pool["score"] = 0.55 * r + 0.45 * pool.prominence
    last = int(p[p.venue != "arxiv"].year.max()) if (p.venue != "arxiv").any() else int(p.year.max())
    used: set = set()

    def take(df, n):
        df = df[~df.key.isin(used)].head(n)
        used.update(df.key)
        return df

    tiers = {}
    tiers["T0 foundational (prominent and on-topic)"] = take(
        pool[(pool.prominence > 0) & (pool.venue != "arxiv")].sort_values("score", ascending=False), per_tier)
    tiers["T1 recent work at the frontier"] = take(
        pool[(pool.year >= last - 1) & (pool.venue != "arxiv")].sort_values("score", ascending=False), per_tier)
    if nn is not None:
        tiers["T2 closest to your idea (read before committing)"] = take(nn, per_tier * 2)
    arx = pool[pool.venue == "arxiv"]
    if len(arx):
        tiers["T3 latest preprints"] = take(arx.sort_values(["date", "relevance"], ascending=False), per_tier)
    return {"clusters": clusters, "tiers": tiers}


def generate_ideas(trends: pd.DataFrame, transplants: pd.DataFrame, bridges: pd.DataFrame,
                   open_problems: pd.DataFrame, clusters: pd.DataFrame, max_ideas: int = 40) -> pd.DataFrame:
    """Evidence-backed idea seeds. Each is traceable to a measured gap; none is a
    recommendation until a human (or the LLM critic) has looked at it."""
    lab = dict(zip(clusters.cluster, clusters.label))
    t = trends.set_index("cluster")
    ideas = []

    # 1) Transplants: method popular & growing, domain popular, cell nearly empty.
    if len(transplants):
        tp = transplants[(transplants.observed <= transplants.expected * 0.35)].copy()
        tp["score"] = tp.gap_z * np.clip(tp.method_growth, 0.5, 3)
        for r in tp.sort_values("score", ascending=False).head(15).itertuples():
            ideas.append({
                "kind": "transplant", "title": f"{r.method} for {r.domain}",
                "rationale": (f"{r.method} appears in {r.method_total} papers and {r.domain} in {r.domain_total}, "
                              f"so ~{r.expected:.0f} papers would combine them by chance; only {r.observed} do. "
                              f"Method usage grew x{r.method_growth} recently."),
                "evidence_score": round(float(r.score), 2), "cluster": -1,
            })

    # 2) Open problems in high-opportunity clusters.
    if len(open_problems):
        top = t.sort_values("opportunity", ascending=False).head(12)
        for cid, r in top.iterrows():
            ops = open_problems[(open_problems.cluster == cid) & open_problems.kind.isin(["open_question", "missing_eval"])]
            if ops.empty:
                continue
            ops = ops.sort_values("year", ascending=False)
            s = ops.iloc[0]
            ideas.append({
                "kind": "open problem", "title": f"Close an admitted gap in {lab[cid]}",
                "rationale": (f"Topic opportunity {r.opportunity:.0f}/100 ({r.tag}); {len(ops)} papers state open questions. "
                              f"Most recent: “{s.sentence[:260]}”"),
                "evidence_score": round(float(r.opportunity) / 20, 2), "cluster": int(cid), "source_key": s.key,
            })

    # 3) Under-connected neighbouring topics, both growing.
    if len(bridges):
        for r in bridges.head(25).itertuples():
            ma, mb = t.momentum.get(r.a, 1), t.momentum.get(r.b, 1)
            if ma < 1.0 and mb < 1.0:
                continue
            ideas.append({
                "kind": "bridge", "title": f"Combine “{lab[r.a]}” with “{lab[r.b]}”",
                "rationale": (f"The two topics are semantically close (sim {r.similarity:.2f}) yet only {r.n_bridge} papers sit "
                              f"between them vs ~{r.expected:.0f} expected. Momentum x{ma:.2f} and x{mb:.2f}."),
                "evidence_score": round(float(r.underconnected), 2), "cluster": int(r.a), "cluster_b": int(r.b),
            })
            if sum(i["kind"] == "bridge" for i in ideas) >= 12:
                break

    # 4) Rising topics that are cheap to enter.
    rising = t[(t.momentum >= 1.3) & (t.entry_cost_label == "cheap")].sort_values("opportunity", ascending=False).head(8)
    for cid, r in rising.iterrows():
        ideas.append({
            "kind": "low-cost entry", "title": f"Theory / analysis angle on {lab[cid]}",
            "rationale": (f"Share grew x{r.momentum:.2f}; abstracts in this topic lean on analysis and training-free methods "
                          f"(entry cost: cheap). {int(r.competition)} papers last year."),
            "evidence_score": round(float(r.opportunity) / 20, 2), "cluster": int(cid),
        })

    df = pd.DataFrame(ideas)
    if df.empty:
        return df
    # Scores are on different scales per kind, so interleave kinds round-robin.
    df["_r"] = df.groupby("kind").evidence_score.rank(ascending=False, method="first")
    df = df.sort_values(["_r", "evidence_score"], ascending=[True, False]).drop(columns="_r")
    df = df.head(max_ideas).reset_index(drop=True)
    df.insert(0, "idea_id", range(1, len(df) + 1))
    return df
