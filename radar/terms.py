"""Emerging and fading vocabulary.

Titles exist for every year, so terms are counted in titles (abstracts would
bias towards years that have them). The latest year is compared with all
earlier years using the log-odds ratio with an informative Dirichlet prior
(Monroe, Colaresi & Quinn 2008), which does not over-reward rare words the way
a raw ratio does.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .text import stopwords


def emerging_terms(df: pd.DataFrame, min_count: int = 8, top: int = 150) -> pd.DataFrame:
    from sklearn.feature_extraction.text import CountVectorizer

    conf = df[df.venue != "arxiv"] if (df.venue != "arxiv").sum() > 500 else df
    years = sorted(conf.year.unique())
    if len(years) < 2:
        return pd.DataFrame(columns=["term", "z", "status", "counts"])
    last = years[-1]
    cv = CountVectorizer(ngram_range=(1, 3), stop_words=stopwords(), min_df=min_count, binary=True,
                         token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z0-9\-]+\b")
    X = cv.fit_transform(conf.title.fillna("").str.lower())
    vocab = np.array(cv.get_feature_names_out())
    yr = conf.year.to_numpy()
    counts = {y: np.asarray(X[yr == y].sum(0)).ravel() for y in years}
    n_docs = {y: int((yr == y).sum()) for y in years}

    y1 = counts[last].astype(float)
    y0 = sum(counts[y] for y in years[:-1]).astype(float)
    prior = (y1 + y0) * 0.1 + 0.01
    n1, n0, a0 = y1.sum(), y0.sum(), prior.sum()
    l1 = np.log((y1 + prior) / (n1 + a0 - y1 - prior))
    l0 = np.log((y0 + prior) / (n0 + a0 - y0 - prior))
    var = 1 / (y1 + prior) + 1 / (y0 + prior)
    z = (l1 - l0) / np.sqrt(var)

    rows = []
    order = np.argsort(-z)
    picked = list(order[:top]) + list(order[::-1][: top // 2])
    for j in picked:
        c = {int(y): int(counts[y][j]) for y in years}
        rate = {int(y): round(1000 * counts[y][j] / max(n_docs[y], 1), 2) for y in years}
        prev = sum(c[int(y)] for y in years[:-1])
        if z[j] > 0:
            status = "new" if prev <= 2 and c[int(last)] >= min_count else "rising"
        else:
            status = "fading"
        rows.append({"term": vocab[j], "z": round(float(z[j]), 2), "status": status,
                     "counts": c, "per_1000": rate})
    out = pd.DataFrame(rows)
    # Remove sub-phrases dominated by a longer phrase with the same status.
    keep = []
    for r in out.itertuples():
        if any(r.term != o.term and r.term in o.term and o.status == r.status and abs(o.z) >= abs(r.z) * 0.9
               for o in out.itertuples()):
            continue
        keep.append(r.Index)
    return out.loc[keep].reset_index(drop=True)


def term_series(df: pd.DataFrame, term: str) -> dict:
    """Per-year rate (per 1000 papers) of a free-text term, for the dashboard."""
    conf = df[df.venue != "arxiv"] if (df.venue != "arxiv").sum() > 500 else df
    # Titles only: abstracts may exist for some years and not others.
    hit = conf.title.str.lower().str.contains(term.lower(), regex=False)
    g = pd.DataFrame({"year": conf.year, "hit": hit}).groupby("year").hit.agg(["sum", "count"])
    return {int(y): {"n": int(r["sum"]), "per_1000": round(1000 * r["sum"] / r["count"], 2)} for y, r in g.iterrows()}
