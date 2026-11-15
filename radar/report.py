"""Trend report as Markdown and standalone HTML, built from the same blocks."""
from __future__ import annotations

import html
import json
from pathlib import Path

import pandas as pd

from .db import DB


class Doc:
    def __init__(self):
        self.blocks: list[tuple] = []

    def h(self, level, text):
        self.blocks.append(("h", level, text))

    def p(self, text):
        self.blocks.append(("p", text))

    def note(self, text):
        self.blocks.append(("note", text))

    def table(self, df: pd.DataFrame):
        self.blocks.append(("table", df))

    def md(self) -> str:
        out = []
        for b in self.blocks:
            if b[0] == "h":
                out.append("#" * b[1] + " " + b[2])
            elif b[0] == "p":
                out.append(b[1])
            elif b[0] == "note":
                out.append("> " + b[1])
            else:
                df = b[1]
                cols = [str(c) for c in df.columns]
                rows = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
                for r in df.itertuples(index=False):
                    rows.append("| " + " | ".join(_fmt(v).replace("|", "/") for v in r) + " |")
                out.append("\n".join(rows))
            out.append("")
        return "\n".join(out)

    def html(self, title: str) -> str:
        body = []
        for b in self.blocks:
            if b[0] == "h":
                body.append(f"<h{b[1]}>{html.escape(b[2])}</h{b[1]}>")
            elif b[0] == "p":
                body.append(f"<p>{html.escape(b[1])}</p>")
            elif b[0] == "note":
                body.append(f"<blockquote>{html.escape(b[1])}</blockquote>")
            else:
                df = b[1]
                head = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
                rows = "".join("<tr>" + "".join(f"<td>{html.escape(_fmt(v))}</td>" for v in r) + "</tr>"
                               for r in df.itertuples(index=False))
                body.append(f"<div class='tw'><table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>")
        return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif;max-width:1080px;margin:40px auto;padding:0 20px;color:#1d2330}}
h1{{font-size:28px}} h2{{margin-top:2.2em;border-bottom:1px solid #e3e6ec;padding-bottom:6px}}
table{{border-collapse:collapse;width:100%;font-size:13px}} th,td{{padding:6px 8px;border-bottom:1px solid #eceff4;text-align:left;vertical-align:top}}
th{{background:#f6f7f9;font-weight:600}} .tw{{overflow-x:auto}} blockquote{{margin:1em 0;padding:8px 14px;background:#f4f6fb;border-left:3px solid #4a6cf7;color:#3a4250}}
</style></head><body>{''.join(body)}</body></html>"""


def _fmt(v) -> str:
    if isinstance(v, float):
        if pd.isna(v):
            return "–"
        return f"{v:.3g}" if abs(v) < 1000 else f"{v:,.0f}"
    if isinstance(v, (list, dict)):
        return json.dumps(v) if isinstance(v, dict) else ", ".join(map(str, v))
    return str(v)


def build_report(db: DB, out_dir: Path, top: int = 15) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summ = db.summary()
    tr = db.read_table("trends")
    ci = db.get_meta("cluster_info", {}) or {}
    ti = db.get_meta("trend_info", {}) or {}
    w = db.get_meta("weights", {}) or {}
    d = Doc()
    d.h(1, "Research Radar — trend report")
    d.p(f"{int(summ.n.sum()):,} papers ({int(summ.with_abstract.sum()):,} with abstracts) from "
        f"{summ.venue.nunique()} venues, {summ.year.min()}–{summ.year.max()}. Generated {db.get_meta('last_run', '')}.")
    d.note("This report states what was measured. Which direction to take is a judgement: the opportunity score below "
           "is a weighted mean of percentile ranks with the weights printed underneath, so it can be argued with.")
    d.h(2, "1. Corpus")
    d.table(summ)
    d.p(f"{ci.get('k')} topics in {ci.get('themes')} themes, embedding backend '{ci.get('backend')}'. "
        + (f"Agreement with the venues' official topic taxonomy (AMI): {ci['ami_vs_official_topics']:.3f}. "
           if ci.get("ami_vs_official_topics") else "")
        + (f"{ci.get('title_only_assigned'):,} title-only papers were placed by title; title placement agrees with "
           f"abstract placement for {ci['title_agreement']:.0%} of papers that have both, and every trend count uses "
           f"title placement for all years so the comparison is like-for-like."
           if ci.get("title_agreement") else ""))
    if ti.get("panel_venues"):
        d.p(f"Share calculations use the venues present in both {ti['first']} and {ti['last']}: "
            + ", ".join(v.upper() for v in ti["panel_venues"]) + ".")

    cols = ["label", "competition", "momentum", "recent_growth", "reward_lift", "impact", "openness",
            "entry_cost_label", "opportunity", "tag"]
    cols = [c for c in cols if c in tr and not tr[c].isna().all()]
    d.h(2, "2. Highest opportunity")
    d.table(tr.sort_values("opportunity", ascending=False)[cols].head(top))
    d.p("Weights: " + ", ".join(f"{k}={v}" for k, v in w.items()) + ".")
    d.h(2, "3. Fastest growing (share of papers)")
    d.table(tr[tr.n_total >= 30].sort_values("momentum", ascending=False)[cols].head(top))
    d.h(2, "4. Cooling")
    d.table(tr[tr.n_total >= 30].sort_values("momentum")[cols].head(10))
    if tr.reward_lift.notna().any():
        d.h(2, "5. What committees reward")
        d.p("Oral + spotlight rate relative to what each topic's venue mix predicts. Lift > 1: highlighted more than expected.")
        d.table(tr.sort_values("reward_lift", ascending=False)[["label", "highlight_rate", "reward_lift", "competition"]].head(12))

    terms = db.read_table("terms")
    if len(terms):
        d.h(2, "6. Emerging vocabulary")
        t = terms[terms.status != "fading"].head(25)
        d.table(t[["term", "status", "z", "counts"]])
        d.h(3, "Fading")
        d.table(terms[terms.status == "fading"].head(12)[["term", "z", "counts"]])

    tp = db.read_table("transplants")
    if len(tp):
        d.h(2, "7. Untried combinations (method × domain)")
        d.p("Observed papers combining a method and a domain vs the number expected from how common each is.")
        d.table(tp.head(20)[["method", "domain", "observed", "expected", "gap_z", "method_growth"]])
    br = db.read_table("bridges")
    if len(br):
        lab = dict(zip(tr.cluster, tr.label))
        b = br.head(12).copy()
        b["topic_a"] = b.a.map(lab)
        b["topic_b"] = b.b.map(lab)
        d.h(2, "8. Under-connected neighbouring topics")
        d.table(b[["topic_a", "topic_b", "similarity", "n_bridge", "expected", "underconnected"]])
    ideas = db.read_table("ideas")
    if len(ideas):
        d.h(2, "9. Idea seeds")
        d.p("Each seed is traceable to one of the measurements above. Novelty = share of corpus papers that sit closer to "
            "their nearest neighbour than this idea does to its nearest paper (higher = emptier neighbourhood).")
        d.table(ideas[["idea_id", "kind", "title", "novelty", "rationale"]].head(25))
    md = out_dir / "TREND_REPORT.md"
    ht = out_dir / "TREND_REPORT.html"
    md.write_text(d.md(), encoding="utf-8")
    ht.write_text(d.html("Research Radar — trend report"), encoding="utf-8")
    return md, ht
