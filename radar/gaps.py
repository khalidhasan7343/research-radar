"""Where the field says it is stuck, and where nobody has looked yet.

1. Open problems   sentences in abstracts that admit a gap ("remains open",
                   "underexplored", "fails to", "future work", ...), typed.
2. Position claims what position papers argue the field should do differently.
3. Transplants     method x domain matrix. Cells observed far below what the
                   row and column totals predict are candidate transplants:
                   a popular method nobody has tried on a popular domain.
4. Bridges         pairs of topics that are close in embedding space but share
                   few papers -- under-connected neighbours.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .text import sentences

OPEN_PATTERNS = {
    "open_question": r"\b(?:remains? (?:largely |an |a |)?(?:open|unclear|unknown|unresolved|elusive|unexplored)"
                     r"|open (?:question|problem|challenge)s?|little is known|poorly understood"
                     r"|not (?:yet |)well[- ]understood|has (?:not|rarely) been (?:studied|explored|addressed)"
                     r"|under-?explored|largely unexplored|lack of (?:theoretical )?understanding)\b",
    "limitation": r"\b(?:fail(?:s|ed)? to|struggle(?:s|d)? (?:to|with)|suffer(?:s|ed)? from|bottleneck"
                  r"|brittle|do(?:es)? not (?:generalize|scale)|limited (?:to|by)|prohibitive(?:ly)?"
                  r"|key limitation|major limitation|fundamental limitation)\b",
    "missing_eval": r"\b(?:no (?:existing |standard |)benchmark|lack(?:s|ing)? (?:of )?(?:a )?(?:standardi[sz]ed |rigorous |)"
                    r"(?:benchmarks?|evaluations?|metrics?)|evaluation (?:is|remains) (?:limited|challenging))\b",
    "future_work": r"\b(?:future (?:work|research|direction)s?|we call (?:on|for)|research agenda|calls? for)\b",
}
_OPEN = {k: re.compile(v, re.I) for k, v in OPEN_PATTERNS.items()}
_CLAIM = re.compile(r"\b(?:we argue|this (?:position )?paper argues|we contend|we advocate|we call|should|must|"
                    r"needs? to|it is time)\b", re.I)

# --- method x domain lexicons ---------------------------------------------
METHODS = {
    "diffusion models": r"diffusion model|denoising diffusion|score-based|diffusion",
    "flow matching": r"flow matching|rectified flow",
    "state space models": r"state[- ]space model|mamba|\bssm\b",
    "mixture of experts": r"mixture[- ]of[- ]experts|\bmoe\b",
    "reinforcement learning": r"reinforcement learning|\brl\b|policy gradient",
    "RL from verifiable rewards": r"\brlvr\b|verifiable reward|\bgrpo\b",
    "preference optimisation": r"\bdpo\b|preference optimi[sz]ation|\brlhf\b",
    "LLM agents": r"\bagents?\b|agentic",
    "chain-of-thought / reasoning": r"chain[- ]of[- ]thought|\bcot\b|reasoning model",
    "test-time scaling": r"test[- ]time (?:scaling|compute|training|adaptation)",
    "in-context learning": r"in[- ]context learning",
    "retrieval augmentation": r"retrieval[- ]augmented|\brag\b",
    "contrastive learning": r"contrastive",
    "graph neural networks": r"graph neural|\bgnns?\b|message passing",
    "neural operators": r"neural operator|fourier neural operator|deeponet",
    "conformal prediction": r"conformal",
    "optimal transport": r"optimal transport|wasserstein|sinkhorn",
    "bayesian inference": r"bayesian|variational inference|gaussian process",
    "causal inference": r"causal (?:inference|discovery|effect|graph|structure)|counterfactual|treatment effect",
    "sparse autoencoders / interpretability": r"sparse autoencoder|\bsaes?\b|mechanistic interpretab",
    "knowledge distillation": r"distillation|distill",
    "quantization / pruning": r"quantiz|pruning|sparsit",
    "low-rank adaptation": r"\blora\b|low[- ]rank adapt",
    "federated learning": r"federated",
    "meta-learning": r"meta[- ]learning",
    "evolutionary search": r"evolutionary|genetic algorithm",
    "program synthesis": r"program synthesis|code generation",
    "energy-based models": r"energy[- ]based",
    "gaussian splatting / NeRF": r"gaussian splatting|\bnerf\b|neural radiance",
    "world models": r"world models?",
    "physics-informed learning": r"physics[- ]informed|\bpinns?\b",
    "symbolic regression": r"symbolic regression",
}
DOMAINS = {
    "proteins": r"protein",
    "molecules / drugs": r"molecul|drug|ligand",
    "materials": r"materials? (?:science|discovery|design|propert)|crystal|alloy",
    "genomics / single-cell": r"genom|single[- ]cell|\bdna\b|\brna\b|gene expression",
    "medicine / clinical": r"medical|clinical|patient|radiolog|patholog|\behr\b|health",
    "neuroscience": r"neuroscien|\bbrain\b|\bfmri\b|\beeg\b|neural recording",
    "weather / climate": r"weather|climate|precipitation",
    "earth observation": r"remote sensing|satellite|earth observation",
    "physics / PDEs": r"\bpdes?\b|partial differential|fluid dynamic|navier|physical system",
    "chemistry": r"chemi|reaction",
    "robotics": r"robot|manipulation|locomotion",
    "autonomous driving": r"autonomous driving|self[- ]driving|\bvehicles?\b",
    "time series": r"time[- ]series|forecast",
    "tabular data": r"tabular",
    "graphs / networks": r"\bgraphs?\b|node classification|link prediction",
    "3D / scenes": r"\b3d\b|point cloud|scene",
    "video": r"\bvideos?\b",
    "audio / speech": r"audio|speech|acoustic",
    "music": r"\bmusic",
    "code / software": r"code generation|source code|software engineering|program repair|\bcoding\b|repositor",
    "mathematics / theorem proving": r"theorem prov|mathematical reasoning|math word|\bmath\b|olympiad|formal proof|\blean\b",
    "education": r"education|tutor|classroom|\bstudents\b (?:learning|performance|essays)",
    "law / policy": r"\blegal\b|\blaw\b|policy[- ]mak",
    "finance / economics": r"financ|economic|market|trading",
    "recommendation": r"recommend(?:er|ation)",
    "cybersecurity": r"security|malware|vulnerab|intrusion",
    "chip design / EDA": r"chip|circuit|\beda\b|hardware design",
    "multilingual / low-resource": r"multilingual|low[- ]resource language|cross[- ]lingual",
    "social science": r"social science|survey data|political|opinion",
    "agriculture / ecology": r"agricultur|crop|ecolog|biodiversity|species",
}


def extract_open_problems(df: pd.DataFrame, pc: pd.DataFrame) -> pd.DataFrame:
    rows = []
    cl = dict(zip(pc.key, pc.cluster))
    for r in df.itertuples(index=False):
        if not r.abstract:
            continue
        for sent in sentences(r.abstract):
            for kind, rx in _OPEN.items():
                if rx.search(sent):
                    rows.append({"key": r.key, "cluster": int(cl.get(r.key, -1)), "kind": kind,
                                 "year": r.year, "venue": r.venue, "sentence": sent[:600]})
                    break
    return pd.DataFrame(rows, columns=["key", "cluster", "kind", "year", "venue", "sentence"])


def extract_position_claims(df: pd.DataFrame, pc: pd.DataFrame) -> pd.DataFrame:
    rows = []
    cl = dict(zip(pc.key, pc.cluster))
    pos = df[(df.paper_type == "position") | df.title.str.lower().str.startswith("position:")]
    for r in pos.itertuples(index=False):
        for sent in sentences(r.abstract or ""):
            if _CLAIM.search(sent):
                rows.append({"key": r.key, "cluster": int(cl.get(r.key, -1)), "year": r.year,
                             "title": r.title, "claim": sent[:600]})
    return pd.DataFrame(rows, columns=["key", "cluster", "year", "title", "claim"])


def _match_matrix(texts: pd.Series, lex: dict) -> pd.DataFrame:
    low = texts.str.lower()
    return pd.DataFrame({name: low.str.contains(rx, regex=True) for name, rx in lex.items()})


def transplant_matrix(df: pd.DataFrame):
    """Observed vs expected co-occurrence of method and domain terms."""
    rich = df[df.abstract.fillna("").str.len() > 200]
    use = rich if len(rich) > 500 else df
    text = use.title.fillna("") + ". " + use.abstract.fillna("")
    M = _match_matrix(text, METHODS)
    D = _match_matrix(text, DOMAINS)
    N = len(use)
    obs = M.T.astype(int) @ D.astype(int)
    expected = np.outer(M.sum(), D.sum()) / max(N, 1)
    exp_df = pd.DataFrame(expected, index=obs.index, columns=obs.columns)

    # Growth of each method, measured on titles (available for every year):
    # rate in the latest year / rate in earlier years.
    conf = df[df.venue != "arxiv"] if (df.venue != "arxiv").sum() > 500 else df
    years = sorted(conf.year.unique())
    if len(years) >= 2:
        MT = _match_matrix(conf.title.fillna(""), METHODS)
        last = (conf.year == years[-1]).to_numpy()
        m_growth = (MT[last].mean() + 2e-3) / (MT[~last].mean() + 2e-3)
    else:
        m_growth = pd.Series(1.0, index=list(METHODS))

    cells = []
    for m in obs.index:
        for d in obs.columns:
            o, e = int(obs.loc[m, d]), float(exp_df.loc[m, d])
            if e < 2:
                continue
            # Poisson tail-ish surprise: how far below expectation.
            gap = (e - o) / np.sqrt(e)
            cells.append({"method": m, "domain": d, "observed": o, "expected": round(e, 1),
                          "ratio": round((o + 0.5) / (e + 0.5), 3), "gap_z": round(gap, 2),
                          "method_total": int(M[m].sum()), "domain_total": int(D[d].sum()),
                          "method_growth": round(float(m_growth.get(m, 1.0)), 2)})
    cells = pd.DataFrame(cells)
    if not cells.empty:
        cells = cells.sort_values("gap_z", ascending=False).reset_index(drop=True)
    return obs, exp_df.round(1), cells


def bridges(pc: pd.DataFrame, centroids: np.ndarray, clusters: pd.DataFrame, margin_thr: float = 0.03,
            top: int = 60) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pairs of clusters that are semantically close but share few bridge papers,
    and the bridge papers themselves."""
    k = len(centroids)
    S = centroids @ centroids.T
    bp = pc[(pc.margin < margin_thr) & (pc.cluster2 >= 0) & (pc.space == "full")]
    pair_counts = pd.Series(0, index=pd.MultiIndex.from_tuples([], names=["a", "b"]), dtype=int)
    if len(bp):
        a = np.minimum(bp.cluster, bp.cluster2)
        b = np.maximum(bp.cluster, bp.cluster2)
        pair_counts = pd.Series(1, index=pd.MultiIndex.from_arrays([a, b], names=["a", "b"])).groupby(level=[0, 1]).sum()
    size = clusters.set_index("cluster")["size"]
    rows = []
    iu = np.triu_indices(k, 1)
    sims = S[iu]
    thr = np.quantile(sims, 0.85) if len(sims) else 1
    for i, j, sim in zip(*iu, sims):
        if sim < thr:
            continue
        n = int(pair_counts.get((i, j), 0))
        # Expected bridge papers grows with both cluster sizes and similarity.
        rows.append({"a": int(i), "b": int(j), "similarity": round(float(sim), 3), "n_bridge": n,
                     "size_a": int(size.get(i, 0)), "size_b": int(size.get(j, 0))})
    br = pd.DataFrame(rows)
    if not br.empty:
        rate = (br.n_bridge.sum() + 1) / (np.sqrt(br.size_a * br.size_b) * br.similarity).sum()
        br["expected"] = (rate * np.sqrt(br.size_a * br.size_b) * br.similarity).round(1)
        br["underconnected"] = ((br.expected - br.n_bridge) / np.sqrt(br.expected + 1)).round(2)
        br = br.sort_values("underconnected", ascending=False).head(top).reset_index(drop=True)
    papers = bp.sort_values("margin")[["key", "cluster", "cluster2", "margin"]].head(3000)
    return br, papers
