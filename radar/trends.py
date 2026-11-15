"""Per-topic measurements and a transparent opportunity score.

Measured per cluster (all share-based: venues grow every year, so raw counts
flatter everything):

  momentum        share in latest year / share in earliest year
  recent_growth   share latest / share previous year
  acceleration    change in log growth rate (is growth speeding up?)
  forecast_share  log-linear extrapolation of share one year ahead
  reward_lift     oral+spotlight rate vs what the cluster's venue mix predicts
  impact          mean within-venue-year citation percentile (if citations known)
  openness        fraction of papers admitting an open problem / limitation
  competition     papers in the latest year
  entry_cost      compute-heaviness index from abstract language
  concentration   share of papers with a repeat author (>=3 papers in topic)
  arxiv_lead      topic share on arXiv (latest 12 months) / share at venues

Only venues present in both the first and last year enter the share
calculations (a balanced panel), so adding NeurIPS for one year does not make
every NeurIPS-heavy topic look like it is booming.

The opportunity score is a weighted mean of percentile ranks. Weights live in
the settings and can be changed live in the dashboard: they are a judgement,
kept visible on purpose.
"""
from __future__ import annotations

import re
from collections import Counter

import numpy as np
import pandas as pd

# Adapted from RTanalysis by Faysal Mahmud (Faysal-star),
# https://github.com/Faysal-star/RTanalysis
EXPENSIVE = re.compile(
    r"\b(?:pre-?train(?:ing|ed)?|from scratch|billion[- ]parameter|\d+\s*b\b|70b|405b|gpu[- ]?(?:hours|days)|"
    r"large[- ]scale training|foundation model training|rlhf|continued pretraining|thousands of gpus|"
    r"trillion tokens?)\b", re.I)
CHEAP = re.compile(
    r"\b(?:training[- ]free|we prove|theorem|we analy[sz]e|post-?hoc|inference[- ]time|zero-?shot|"
    r"plug-?and-?play|no (?:additional )?training|closed[- ]form|provabl|lower bound|upper bound|"
    r"theoretical(?:ly)?|sample complexity|regret bound)\b", re.I)

COMPONENTS = {
    # name: (column, higher_is_better)
    "momentum": ("momentum", True),
    "acceleration": ("acceleration", True),
    "reward": ("reward_lift", True),
    "impact": ("impact", True),
    "openness": ("openness", True),
    "low_competition": ("competition", False),
    "low_entry_cost": ("entry_cost", False),
    "low_concentration": ("concentration", False),
}


def _pct(s: pd.Series, higher_is_better: bool) -> pd.Series:
    r = s.rank(pct=True, na_option="keep")
    return r if higher_is_better else 1 - r + 1 / max(s.notna().sum(), 1)


def opportunity(metrics: pd.DataFrame, weights: dict) -> pd.DataFrame:
    m = metrics.copy()
    num = pd.Series(0.0, index=m.index)
    den = pd.Series(0.0, index=m.index)
    for comp, (col, hib) in COMPONENTS.items():
        p = _pct(m[col], hib)
        m[f"pct_{comp}"] = p.round(4)
        w = float(weights.get(comp, 0))
        ok = p.notna()
        num[ok] += w * p[ok]
        den[ok] += w
    m["opportunity"] = (100 * num / den.replace(0, np.nan)).round(1)
    return m


def _tag(r) -> str:
    rising = r.momentum >= 1.25
    falling = r.momentum <= 0.8
    crowded = r.pct_low_competition < 0.3 if pd.notna(r.pct_low_competition) else False
    rewarded = r.reward_lift >= 1.15 if pd.notna(r.reward_lift) else False
    if falling:
        return "cooling"
    if rising and rewarded and not crowded:
        return "sweet spot"
    if rising and crowded:
        return "hot & crowded"
    if rising:
        return "rising"
    if rewarded and not crowded:
        return "niche gem"
    if crowded:
        return "mainstream"
    return "steady"


def compute_trends(df: pd.DataFrame, pc: pd.DataFrame, clusters: pd.DataFrame,
                   open_problems: pd.DataFrame, weights: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = df[["key", "venue", "year", "presentation", "citations", "abstract", "authors", "date"]].merge(
        pc[["key", "cluster"] + (["cluster_trend"] if "cluster_trend" in pc else [])], on="key")
    if "cluster_trend" not in d:
        d["cluster_trend"] = d["cluster"]
    k = len(clusters)
    conf = d[d.venue != "arxiv"]
    arx = d[d.venue == "arxiv"]

    # Guard against half-published years: a venue-year with under half the
    # previous year's papers is still being indexed. Counting it would make
    # every topic at that venue look like it collapsed.
    vy_all = conf.groupby(["venue", "year"]).size()
    incomplete = [(v, int(y)) for (v, y), n in vy_all.items()
                  if (v, y - 1) in vy_all.index and n < 0.5 * vy_all[(v, y - 1)]]
    if incomplete:
        bad = pd.MultiIndex.from_tuples(incomplete)
        conf = conf[~pd.MultiIndex.from_arrays([conf.venue, conf.year]).isin(bad)]

    years = sorted(conf.year.unique())
    first, last = years[0], years[-1]
    vy = conf.groupby(["venue", "year"]).size()
    panel_venues = [v for v in conf.venue.unique() if (v, first) in vy.index and (v, last) in vy.index]
    panel = conf[conf.venue.isin(panel_venues)] if panel_venues else conf
    N_y = panel.groupby("year").size()
    # Counts over time use the like-for-like (title-space) assignment.
    n_cy = panel.groupby(["cluster_trend", "year"]).size().unstack(fill_value=0).reindex(range(k), fill_value=0)
    for y in years:
        if y not in n_cy.columns:
            n_cy[y] = 0
    n_cy = n_cy[sorted(n_cy.columns)]
    share = (n_cy + 0.5) / N_y.reindex(n_cy.columns).to_numpy()

    out = pd.DataFrame({"cluster": range(k)})
    out["n_total"] = conf.groupby("cluster_trend").size().reindex(range(k), fill_value=0).to_numpy()
    out["competition"] = n_cy[last].to_numpy()
    out["momentum"] = (share[last] / share[first]).round(3).to_numpy() if first != last else 1.0
    py = years[-2] if len(years) >= 2 else last
    out["recent_growth"] = (share[last] / share[py]).round(3).to_numpy()
    if len(years) >= 3:
        ppy = years[-3]
        out["acceleration"] = (np.log(share[last] / share[py]) - np.log(share[py] / share[ppy])).round(3).to_numpy()
    else:
        out["acceleration"] = np.nan

    # Log-linear forecast of share, one year ahead.
    yrs = np.array(n_cy.columns, dtype=float)
    if len(yrs) >= 2:
        L = np.log(share.to_numpy())
        A = np.vstack([yrs, np.ones_like(yrs)]).T
        coef, *_ = np.linalg.lstsq(A, L.T, rcond=None)
        proj = np.exp(coef[0] * (yrs[-1] + 1) + coef[1])
        proj = np.minimum(proj, share[last].to_numpy() * 3)
        out["forecast_share"] = (proj * 100).round(3)
        out["forecast_n"] = np.round(proj * N_y[last]).astype(int)
    else:
        out["forecast_share"] = np.nan
        out["forecast_n"] = np.nan
    out["share_last"] = (n_cy[last] / N_y[last] * 100).round(3).to_numpy()

    # Reward lift over venue-mix expectation (venue-years that report tiers).
    known = conf[conf.presentation.isin(["oral", "spotlight", "poster"])]
    tiers = known.groupby(["venue", "year"]).presentation.apply(lambda s: s.isin(["oral", "spotlight"]).mean())
    tiers = tiers[tiers > 0]
    if len(tiers):
        kk = known.set_index(["venue", "year"]).loc[tiers.index].reset_index()
        kk["rate"] = [tiers[(v, y)] for v, y in zip(kk.venue, kk.year)]
        kk["hl"] = kk.presentation.isin(["oral", "spotlight"])
        g = kk.groupby("cluster").agg(obs=("hl", "sum"), exp=("rate", "sum"), n=("hl", "size"))
        g = g.reindex(range(k))
        out["highlight_rate"] = (g.obs / g.n * 100).round(2).to_numpy()
        out["reward_lift"] = ((g.obs + 1) / (g.exp + 1)).round(3).to_numpy()
    else:
        out["highlight_rate"] = np.nan
        out["reward_lift"] = np.nan

    # Citation impact: within (venue, year) percentile, averaged per cluster.
    cit = conf.dropna(subset=["citations"])
    if len(cit) > 0.3 * len(conf):
        pct = cit.groupby(["venue", "year"]).citations.rank(pct=True)
        out["impact"] = (pct.groupby(cit.cluster).mean().reindex(range(k)) * 100).round(1).to_numpy()
        out["median_citations"] = cit.groupby("cluster").citations.median().reindex(range(k)).to_numpy()
    else:
        out["impact"] = np.nan
        out["median_citations"] = np.nan

    # Openness.
    rich = conf[conf.abstract.fillna("").str.len() > 200]
    n_rich = rich.groupby("cluster").size().reindex(range(k), fill_value=0)
    if len(open_problems):
        op = open_problems[open_problems.kind.isin(["open_question", "limitation", "missing_eval"])]
        op_papers = op.drop_duplicates("key").groupby("cluster").size().reindex(range(k), fill_value=0)
        out["openness"] = (op_papers / n_rich.replace(0, np.nan)).round(3).to_numpy()
        out["n_open_problems"] = op.groupby("cluster").size().reindex(range(k), fill_value=0).to_numpy()
    else:
        out["openness"] = np.nan
        out["n_open_problems"] = 0

    # Entry cost.
    if len(rich):
        e = rich.abstract.str.contains(EXPENSIVE)
        c = rich.abstract.str.contains(CHEAP)
        idx = (e.astype(int) - c.astype(int)).groupby(rich.cluster).mean().reindex(range(k))
        out["entry_cost"] = idx.round(3).to_numpy()
        q1, q2 = np.nanquantile(idx, [1 / 3, 2 / 3]) if idx.notna().any() else (0, 0)
        out["entry_cost_label"] = ["?" if pd.isna(v) else "cheap" if v <= q1 else "expensive" if v > q2 else "moderate"
                                   for v in idx]
    else:
        out["entry_cost"] = np.nan
        out["entry_cost_label"] = "?"

    # Concentration: papers with a repeat author (>= 3 papers in this topic, last 2 years).
    recent = conf[conf.year >= years[-2]] if len(years) >= 2 else conf
    conc, team = [], []
    for cid in range(k):
        sub = recent[recent.cluster == cid]
        authors = [a for a in sub.authors if isinstance(a, list) and a]
        if len(authors) < 10:
            conc.append(np.nan)
            team.append(np.nan)
            continue
        cnt = Counter(x for al in authors for x in al)
        conc.append(np.mean([any(cnt[x] >= 3 for x in al) for al in authors]))
        team.append(float(np.median([len(al) for al in authors])))
    out["concentration"] = np.round(conc, 3)
    out["median_team"] = team

    # arXiv as a leading indicator.
    if len(arx) > 200:
        dates = pd.to_datetime(arx.date, errors="coerce")
        cut = dates.max() - pd.Timedelta(days=365)
        ra = arx[dates >= cut]
        a_share = ra.groupby("cluster").size().reindex(range(k), fill_value=0) / max(len(ra), 1)
        c_share = n_cy[last] / max(N_y[last], 1)
        out["arxiv_lead"] = ((a_share + 1e-4) / (c_share + 1e-4)).round(3).to_numpy()
        out["arxiv_recent"] = ra.groupby("cluster").size().reindex(range(k), fill_value=0).to_numpy()
    else:
        out["arxiv_lead"] = np.nan
        out["arxiv_recent"] = 0

    out["mean_year"] = conf.groupby("cluster_trend").year.mean().reindex(range(k)).round(2).to_numpy()
    out = opportunity(out, weights)
    out["tag"] = [_tag(r) for r in out.itertuples()]
    out = clusters[["cluster", "theme", "label"]].merge(out, on="cluster")

    cy = n_cy.stack().rename("n").reset_index()
    cy.columns = ["cluster", "year", "n"]
    cy["share"] = [round(100 * n / N_y[y], 3) for n, y in zip(cy.n, cy.year)]
    all_cy = conf.groupby(["cluster_trend", "year"]).size().rename("n_all").reset_index()
    all_cy.columns = ["cluster", "year", "n_all"]
    cy = cy.merge(all_cy, on=["cluster", "year"], how="left").fillna({"n_all": 0})
    meta = {"years": [int(y) for y in years], "panel_venues": panel_venues, "first": int(first), "last": int(last),
            "incomplete_venue_years": [f"{v} {y}" for v, y in incomplete]}
    return out, cy, meta
