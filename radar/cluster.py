"""Topic structure: fine clusters, coarse themes, labels and a 2-D map.

Differences from a plain UMAP+HDBSCAN run:

* No paper is thrown away as "noise". Every paper gets a cluster plus a
  confidence (cosine to its centroid) and a margin (gap to the runner-up
  cluster). Low-margin papers are *bridges* between two topics, which is
  exactly where new directions tend to come from, so they are kept and
  surfaced instead of dropped.
* Two levels: fine clusters (automatic: 12-150, from corpus size) grouped
  into themes (automatic: 4-8).
* Title-only papers (older years) are assigned in title space (see embed.py).
* Labels are c-TF-IDF keyphrases with redundancy removed, optionally rewritten
  by an LLM.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import SEED, Settings
from .text import doc_text, stopwords

RICH_MIN_CHARS = 200


def rich_mask(df: pd.DataFrame) -> np.ndarray:
    m = (df["abstract"].fillna("").str.len() >= RICH_MIN_CHARS).to_numpy()
    # With too few abstracts there is nothing to gain from the two-space trick.
    if m.sum() < max(500, 0.15 * len(df)):
        return np.ones(len(df), dtype=bool)
    return m


def auto_k(n: int) -> int:
    return int(np.clip(round(np.sqrt(n / 3)), 12, 150))


def _centroids(X: np.ndarray, labels: np.ndarray, k: int) -> np.ndarray:
    C = np.zeros((k, X.shape[1]), dtype=np.float32)
    for c in range(k):
        m = labels == c
        if m.any():
            C[c] = X[m].mean(0)
    n = np.linalg.norm(C, axis=1, keepdims=True)
    n[n == 0] = 1
    return C / n


def _top2(S: np.ndarray):
    order = np.argsort(-S, axis=1)[:, :2]
    rows = np.arange(len(S))
    return order[:, 0], order[:, 1], S[rows, order[:, 0]], S[rows, order[:, 1]]


def ctfidf_keywords(docs_by_cluster: dict[int, list[str]], top: int = 10) -> dict[int, list[str]]:
    from sklearn.feature_extraction.text import CountVectorizer

    ids = sorted(docs_by_cluster)
    joined = [" ".join(docs_by_cluster[i]) for i in ids]
    # Each "document" here is a whole cluster, so min_df must stay 1: a term that
    # occurs in a single cluster is the most distinctive kind. Rare noise is
    # removed by total frequency instead.
    cv = CountVectorizer(ngram_range=(1, 3), stop_words=stopwords(), min_df=1,
                         token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z0-9\-]+\b")
    try:
        X = cv.fit_transform(joined).astype(np.float64).tocsc()
    except ValueError:  # vocabulary empty (tiny corpus)
        return {i: [] for i in ids}
    keep = np.asarray(X.sum(0)).ravel() >= 5
    X = X[:, keep].tocsr()
    vocab = np.array(cv.get_feature_names_out())[keep]
    tf = X.multiply(1 / np.maximum(X.sum(1), 1)).tocsr()
    A = X.sum() / X.shape[0]
    f = np.asarray(X.sum(0)).ravel()
    idf = np.log1p(A / np.maximum(f, 1))
    W = tf.multiply(idf).tocsr()
    out = {}
    for row, cid in enumerate(ids):
        r = W.getrow(row).toarray().ravel()
        cand = np.argsort(-r)[: top * 6]
        chosen: list[str] = []
        for j in cand:
            if r[j] <= 0:
                break
            t = vocab[j]
            # drop near-duplicates: 'language model' vs 'language models', sub/super-phrases
            stem = t.rstrip("s")
            if any(stem in c or c.rstrip("s") in t for c in chosen):
                continue
            chosen.append(t)
            if len(chosen) >= top:
                break
        out[cid] = chosen
    return out


def make_label(keywords: list[str], n: int = 3) -> str:
    # Prefer multi-word phrases; they are more specific than single words.
    phrases = [k for k in keywords if " " in k][:n]
    for k in keywords:
        if len(phrases) >= n:
            break
        if k not in phrases:
            phrases.append(k)
    return " · ".join(phrases[:n]) or "misc"


def layout_2d(X: np.ndarray, method: str, log=print) -> np.ndarray:
    from sklearn.decomposition import PCA

    if method == "umap":
        try:
            import umap

            return umap.UMAP(n_neighbors=20, min_dist=0.1, metric="cosine", random_state=SEED).fit_transform(X)
        except ImportError:
            log("  umap not installed, falling back to t-SNE")
            method = "tsne"
    Xp = PCA(n_components=min(50, X.shape[1]), random_state=SEED).fit_transform(X)
    if method == "pca" or len(X) < 50:
        return Xp[:, :2]
    from sklearn.manifold import TSNE

    return TSNE(n_components=2, perplexity=min(40, max(5, len(X) // 100)), init="pca",
                learning_rate="auto", random_state=SEED, n_jobs=-1).fit_transform(Xp)


def run_clustering(s: Settings, df: pd.DataFrame, full: np.ndarray, title: np.ndarray, log=print):
    """Returns (paper_cluster, clusters, themes, centroids)."""
    from sklearn.cluster import AgglomerativeClustering, KMeans

    rich = rich_mask(df)
    conf_df = df[~df.venue.eq("arxiv")] if (~df.venue.eq("arxiv")).sum() > 500 else df
    fit_idx = np.where(rich & df.index.isin(conf_df.index))[0]
    Xf = full[fit_idx]
    k = s.n_clusters or auto_k(len(fit_idx))
    log(f"  k-means: {len(fit_idx):,} papers -> {k} clusters")
    km = KMeans(n_clusters=k, n_init=4, random_state=SEED).fit(Xf)
    C_full = _centroids(Xf, km.labels_, k)

    # Every paper with an abstract (incl. arXiv) placed in full space.
    n = len(df)
    cl = np.full(n, -1)
    cl2 = np.full(n, -1)
    conf = np.zeros(n, dtype=np.float32)
    marg = np.zeros(n, dtype=np.float32)
    space = np.array([""] * n, dtype=object)
    idx_r = np.where(rich)[0]
    a, b, s1, s2 = _top2(full[idx_r] @ C_full.T)
    cl[idx_r], cl2[idx_r], conf[idx_r], marg[idx_r] = a, b, s1, s1 - s2
    space[idx_r] = "full"

    # Title-only papers placed in title space against title centroids.
    idx_t = np.where(~rich)[0]
    cl_trend = cl.copy()
    title_agreement = None
    if len(idx_t):
        C_title = _centroids(title[idx_r], cl[idx_r], k)
        a, b, s1, s2 = _top2(title[idx_t] @ C_title.T)
        cl[idx_t], cl2[idx_t], conf[idx_t], marg[idx_t] = a, b, s1, s1 - s2
        space[idx_t] = "title"
        log(f"  {len(idx_t):,} title-only papers assigned via title centroids")
        # For trend counting every year must be placed the same way, otherwise a
        # topic whose titles are less distinctive than its abstracts looks like
        # it is growing simply because recent years have abstracts. So trends
        # use a title-space assignment for *all* papers.
        cl_trend = (title @ C_title.T).argmax(1)
        title_agreement = float((cl_trend[idx_r] == cl[idx_r]).mean())
        log(f"  title-space vs abstract-space agreement on papers with abstracts: {title_agreement:.1%}")

    # Themes: agglomerative clustering of centroids.
    n_themes = s.n_themes or int(np.clip(round(k / 8), 4, 8))
    n_themes = min(n_themes, k)
    # Ward on unit vectors ~ cosine, and gives balanced themes (average linkage
    # tends to produce one giant theme plus singletons).
    theme_of = AgglomerativeClustering(n_clusters=n_themes, linkage="ward").fit_predict(C_full)
    sizes = np.bincount(cl[cl >= 0], minlength=k)

    # Labels
    texts = [doc_text(t, a) for t, a in zip(df.title, df.abstract)]
    by_c: dict[int, list[str]] = {c: [] for c in range(k)}
    for i in idx_r:
        by_c[cl[i]].append(texts[i])
    for i in idx_t:
        by_c[cl[i]].append(texts[i])
    kw = ctfidf_keywords(by_c, top=12)
    by_t: dict[int, list[str]] = {t: [] for t in range(n_themes)}
    for c in range(k):
        by_t[int(theme_of[c])].extend(by_c[c])
    tkw = ctfidf_keywords(by_t, top=10)

    # 2-D map of papers with abstracts (capped for speed).
    xy = np.full((n, 2), np.nan, dtype=np.float32)
    lay_idx = idx_r
    if len(lay_idx) > 20000:
        rng = np.random.default_rng(SEED)
        lay_idx = np.sort(rng.choice(lay_idx, 20000, replace=False))
    log(f"  2-D layout ({s.layout}) of {len(lay_idx):,} papers")
    pts = layout_2d(full[lay_idx], s.layout, log)
    pts = (pts - pts.mean(0)) / (pts.std(0) + 1e-9)
    xy[lay_idx] = pts

    keys = df.key.to_numpy()
    paper_cluster = pd.DataFrame({
        "key": keys, "cluster": cl, "cluster2": cl2, "cluster_trend": cl_trend, "theme": theme_of[cl],
        "confidence": conf.round(4), "margin": marg.round(4), "space": space,
        "x": xy[:, 0].round(3), "y": xy[:, 1].round(3),
    })

    reps = {}
    for c in range(k):
        m = np.where((cl == c) & rich)[0]
        if len(m):
            top = m[np.argsort(-conf[m])[:5]]
            reps[c] = [keys[i] for i in top]
    centroid_xy = paper_cluster.dropna(subset=["x"]).groupby("cluster")[["x", "y"]].median()
    clusters = pd.DataFrame({
        "cluster": np.arange(k),
        "theme": theme_of,
        "label": [make_label(kw[c]) for c in range(k)],
        "keywords": [kw[c] for c in range(k)],
        "size": sizes,
        "representatives": [reps.get(c, []) for c in range(k)],
        "cx": [float(centroid_xy.x.get(c, np.nan)) for c in range(k)],
        "cy": [float(centroid_xy.y.get(c, np.nan)) for c in range(k)],
        "summary": [""] * k,
    })
    themes = pd.DataFrame({
        "theme": np.arange(n_themes),
        "label": [make_label(tkw[t], 2) for t in range(n_themes)],
        "keywords": [tkw[t] for t in range(n_themes)],
        "clusters": [[int(c) for c in np.where(theme_of == t)[0]] for t in range(n_themes)],
        "size": [int(sizes[theme_of == t].sum()) for t in range(n_themes)],
    })
    paper_cluster.attrs["title_agreement"] = title_agreement
    return paper_cluster, clusters, themes, C_full


def topic_purity(df: pd.DataFrame, labels: np.ndarray) -> float | None:
    """AMI against the venues' official topic taxonomy, when they provide one.

    Only topics from an official source (OpenReview primary areas, RTanalysis
    venue topics) are used; OpenAlex topics and arXiv categories are different
    taxonomies and would make the score meaningless."""
    from sklearn.metrics import adjusted_mutual_info_score

    from .db import OFFICIAL_TOPIC_SOURCES

    src = df["topic_source"] if "topic_source" in df else pd.Series("", index=df.index)
    m = (df["topic"].fillna("").str.len().gt(0).to_numpy() & src.isin(OFFICIAL_TOPIC_SOURCES).to_numpy()
         & (labels >= 0))
    if m.sum() < 200:
        return None
    return float(adjusted_mutual_info_score(df.topic[m], labels[m]))
