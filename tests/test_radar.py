"""Tests: parsers against recorded API shapes, dedupe rules, metrics, and a
small end-to-end run on a synthetic corpus (no network)."""
from __future__ import annotations

import json
import random

import numpy as np
import pandas as pd
import pytest

from radar.config import Settings
from radar.db import DB
from radar.ingest.sources import (parse_arxiv_feed, parse_openalex_work, parse_openreview_note, parse_s2_paper)
from radar.text import normalize_title, openalex_abstract


# ------------------------------------------------------------------ parsers
def test_openalex_abstract_rebuild():
    inv = {"Deep": [0], "nets": [1, 4], "are": [2], "fun": [3]}
    assert openalex_abstract(inv) == "Deep nets are fun nets"


def test_parse_openalex_work():
    w = {"id": "https://openalex.org/W123", "title": "A Paper", "publication_year": 2024, "publication_date": "2024-07-01",
         "abstract_inverted_index": {"Hello": [0], "world": [1]}, "cited_by_count": 17, "doi": "https://doi.org/10.1/x",
         "authorships": [{"author": {"display_name": "Ada"}, "institutions": [{"display_name": "MIT"}]}],
         "primary_location": {"landing_page_url": "https://x.org/p"},
         "locations": [{"landing_page_url": "https://arxiv.org/abs/2401.00001v2"}], "ids": {}}
    p = parse_openalex_work(w, "icml")
    assert p["key"] == "openalex:W123" and p["abstract"] == "Hello world" and p["citations"] == 17
    assert p["authors"] == ["Ada"] and p["institutions"] == ["MIT"] and p["arxiv_id"] == "2401.00001" and p["doi"] == "10.1/x"


def test_parse_s2_and_openreview():
    p = parse_s2_paper({"paperId": "abc", "title": "T", "abstract": None, "authors": [{"name": "B"}], "year": 2025,
                        "citationCount": 3, "externalIds": {"ArXiv": "2501.1"}}, "neurips")
    assert p["key"] == "s2:abc" and p["abstract"] == "" and p["arxiv_id"] == "2501.1"
    n = {"id": "xyz", "content": {"title": {"value": "Position: X"}, "abstract": {"value": "A"},
                                   "authors": {"value": ["C"]}, "venue": {"value": "ICLR 2025 Oral"}}}
    r = parse_openreview_note(n, "iclr", 2025)
    assert r["presentation"] == "oral" and r["paper_type"] == "position"
    n["content"]["venue"] = {"value": "Submitted to ICLR 2025"}
    assert parse_openreview_note(n, "iclr", 2025) is None


def test_parse_arxiv_feed():
    xml = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry>
    <id>http://arxiv.org/abs/2501.01234v3</id><published>2025-01-03T00:00:00Z</published>
    <title>  Some
     Title</title><summary>Abs text.</summary><author><name>D E</name></author>
    <category term="cs.LG"/><category term="cs.AI"/></entry></feed>"""
    (p,) = parse_arxiv_feed(xml)
    assert p["arxiv_id"] == "2501.01234" and p["title"] == "Some Title" and p["year"] == 2025 and p["topic"] == "cs.LG,cs.AI"


# ------------------------------------------------------------------- dedupe
def test_merge_rules(tmp_path):
    db = DB(tmp_path / "t.db")
    db.upsert_papers([{"key": "a", "title": "Great Paper!", "venue": "arxiv", "year": 2023, "abstract": "short"}], "arxiv")
    # venue version next year merges into the preprint and takes over venue/year
    ins, mer = db.upsert_papers([{"key": "b", "title": "Great paper", "venue": "icml", "year": 2024,
                                  "abstract": "a much longer abstract", "citations": 5}], "openalex")
    assert (ins, mer) == (0, 1)
    p = db.papers().iloc[0]
    assert p.venue == "icml" and p.year == 2024 and p.citations == 5 and "longer" in p.abstract
    assert set(p.sources) == {"arxiv", "openalex"}
    # two venues in adjacent years never merge
    ins, _ = db.upsert_papers([{"key": "c", "title": "Great paper", "venue": "iclr", "year": 2025}], "x")
    assert ins == 1


def test_topic_source_prefers_official_taxonomy(tmp_path):
    db = DB(tmp_path / "t.db")
    db.upsert_papers([{"key": "a", "title": "Some Paper", "venue": "iclr", "year": 2025,
                       "topic": "Machine Learning Methods and Applications"}], "openalex")
    assert db.papers().iloc[0].topic_source == "openalex"
    # the venue's own (shorter) area replaces OpenAlex's topic ...
    db.upsert_papers([{"key": "b", "title": "Some paper", "venue": "iclr", "year": 2025,
                       "topic": "optimization"}], "openreview")
    p = db.papers().iloc[0]
    assert (p.topic, p.topic_source) == ("optimization", "openreview")
    # ... and is not replaced by a later, longer OpenAlex topic
    db.upsert_papers([{"key": "c", "title": "Some paper", "venue": "iclr", "year": 2025,
                       "topic": "A much longer OpenAlex topic label"}], "openalex")
    p = db.papers().iloc[0]
    assert (p.topic, p.topic_source) == ("optimization", "openreview")


def test_old_database_gets_topic_source(tmp_path):
    import sqlite3

    from radar.db import SCHEMA

    path = tmp_path / "old.db"
    old_schema = "\n".join(line for line in SCHEMA.splitlines() if not line.strip().startswith("topic_source"))
    with sqlite3.connect(path) as c:
        c.executescript(old_schema)
        assert "topic_source" not in {r[1] for r in c.execute("PRAGMA table_info(papers)")}
        cols = "key, title, title_norm, venue, year, topic, sources"
        c.execute(f"INSERT INTO papers ({cols}) VALUES ('p1','A','a','iclr',2025,'optimization','[\"openreview\"]')")
        c.execute(f"INSERT INTO papers ({cols}) VALUES ('p2','B','b','iclr',2025,'theory','[\"openalex\", \"openreview\"]')")
    db = DB(path)
    src = dict(zip(db.papers().key, db.papers().topic_source))
    assert src == {"p1": "openreview", "p2": ""}  # merged record: origin unknown until re-ingested


def test_topic_purity_uses_official_topics_only():
    from radar.cluster import topic_purity

    n = 300
    labels = np.arange(n) % 3
    df = pd.DataFrame({"topic": [f"t{x}" for x in labels], "topic_source": ["openreview"] * n})
    assert topic_purity(df, labels) == pytest.approx(1.0)
    df["topic_source"] = "openalex"
    assert topic_purity(df, labels) is None  # not the venue's taxonomy


def test_normalize_title():
    assert normalize_title("Café: The (Über) Model!") == "cafe the uber model"


# ------------------------------------------------------------- end-to-end
TOPICS = {
    "diffusion": ("diffusion model image generation denoising score sampling", 1.0),
    "agents": ("llm agent tool use planning web agent benchmark", 3.0),  # growing
    "graphs": ("graph neural network node classification message passing", 0.4),  # shrinking
    "bandits": ("bandit regret bound online learning exploration theorem", 1.0),
}


def _corpus(n_per_year=600, seed=0):
    rnd = random.Random(seed)
    rows = []
    for year, scale in ((2023, 0.0), (2024, 0.5), (2025, 1.0)):
        weights = {t: (1 - scale) + scale * g for t, (_, g) in TOPICS.items()}
        tot = sum(weights.values())
        for i in range(n_per_year):
            t = rnd.choices(list(weights), [w / tot for w in weights.values()])[0]
            words = TOPICS[t][0].split()
            title = " ".join(rnd.sample(words, 4)) + f" {t} study {i}"
            abstract = " ".join(rnd.choices(words, k=60)) + (" this remains an open question ." if rnd.random() < .2 else "")
            rows.append({"key": f"{year}-{i}", "title": title, "venue": "conf", "year": year,
                         "abstract": abstract if year == 2025 else "",
                         "presentation": ("oral" if rnd.random() < (0.15 if t == "bandits" else 0.04) else "poster") if year == 2025 else "",
                         "authors": [f"author{rnd.randint(0, 80)}" for _ in range(3)]})
    return rows


@pytest.fixture(scope="module")
def analysed(tmp_path_factory):
    from radar import pipeline

    d = tmp_path_factory.mktemp("radar")
    s = Settings(data_dir=d, layout="pca", n_clusters=4, embed_dim=32)
    s.ensure_dirs()
    db = DB(s.db_path)
    db.upsert_papers(_corpus(), "synthetic")
    pipeline.run(s, db, log=lambda *_: None)
    return s, db


def test_pipeline_finds_trends(analysed):
    s, db = analysed
    tr = db.read_table("trends")
    assert len(tr) == 4
    # map each cluster to the ground-truth topic most of its papers came from
    pc = db.read_table("paper_cluster").merge(db.papers()[["key", "title"]], on="key")
    pc["truth"] = pc.title.str.extract(r" (\w+) study \d+$")[0]
    truth = pc.groupby("cluster").truth.agg(lambda s: s.value_counts().index[0])
    assert truth.nunique() == 4
    mom = {truth[c]: m for c, m in zip(tr.cluster, tr.momentum)}
    assert mom["agents"] > 1.5 and mom["graphs"] < 0.8
    rew = {truth[c]: r for c, r in zip(tr.cluster, tr.reward_lift)}
    assert rew["bandits"] == max(rew.values())
    assert tr.opportunity.between(0, 100).all()


def test_pipeline_outputs(analysed):
    s, db = analysed
    assert len(db.read_table("open_problems")) > 0
    assert db.read_table("paper_cluster").cluster.min() >= 0  # nobody discarded as noise
    terms = db.read_table("terms")
    assert len(terms) and "status" in terms


def test_novelty_and_reading(analysed):
    from radar.ideas import Index, reading_list

    s, db = analysed
    ix = Index(s, db.papers(), db.read_table("paper_cluster"), np.load(s.emb_dir / "centroids.npy"))
    near = ix.novelty("llm agent tool use planning benchmark")
    far = ix.novelty("protein folding with cryo electron microscopy")
    assert near["novelty"] <= far["novelty"]
    rl = reading_list(ix, "graph neural network message passing")
    keys = [k for df in rl["tiers"].values() for k in df.key]
    assert len(keys) == len(set(keys))  # no paper in two tiers


def test_server(analysed):
    from fastapi.testclient import TestClient

    from radar.server import create_app

    s, db = analysed
    c = TestClient(create_app(s))
    assert c.get("/api/overview").json()["ready"]
    assert len(c.get("/api/topics").json()["topics"]) == 4
    assert c.get("/api/topics/0").status_code == 200
    assert c.post("/api/novelty", json={"text": "bandit regret bounds for online exploration"}).json()["neighbours"]
    assert c.post("/api/rescore", json={"weights": {"momentum": 1}}).status_code == 200
    assert c.get("/").status_code == 200


def test_openness_counts_only_rich_conference_papers():
    from radar.trends import compute_trends

    long = "word " * 60
    rows = [{"key": f"c{c}-{y}-{i}", "venue": "conf", "year": y, "abstract": long, "cluster": c}
            for c in (0, 1) for y in (2024, 2025) for i in range(20)]
    rows += [{"key": f"a{i}", "venue": "arxiv", "year": 2025, "abstract": long, "cluster": 0} for i in range(50)]
    df = pd.DataFrame(rows).assign(presentation="", citations=None, authors=[[] for _ in rows], date="")
    pc = df[["key", "cluster"]]
    clusters = pd.DataFrame({"cluster": [0, 1], "theme": [0, 0], "label": ["a", "b"]})
    # two conference papers and every arXiv paper in topic 0 admit an open problem
    op_keys = ["c0-2025-0", "c0-2025-1"] + [f"a{i}" for i in range(50)]
    op = pd.DataFrame({"key": op_keys, "cluster": 0, "kind": "open_question"})
    tr, _, _ = compute_trends(df, pc, clusters, op, {"openness": 1})
    assert tr.set_index("cluster").openness[0] == pytest.approx(2 / 40)


def test_report(analysed, tmp_path):
    from radar.report import build_report

    s, db = analysed
    md, ht = build_report(db, tmp_path)
    assert "Highest opportunity" in md.read_text() and ht.read_text().startswith("<!DOCTYPE html>")


# ------------------------------------------------------------------ updates
def test_cache_expiry(tmp_path):
    import os

    from radar.ingest.http import Client

    c = Client(tmp_path)
    path = c._key("https://x", {"a": 1})
    path.write_text("old")
    assert c.get("https://x", {"a": 1}) == "old"  # kept forever by default
    c.max_age = 60
    os.utime(path, (0, 0))  # pretend it is ancient
    c.s.get = lambda *a, **k: type("R", (), {"status_code": 200, "text": "new", "headers": {}})()
    assert c.get("https://x", {"a": 1}) == "new"


def test_recent_from_controls_cache_refresh(tmp_path, monkeypatch):
    from radar import ingest

    s = Settings(data_dir=tmp_path / "d")
    s.ensure_dirs()
    db = DB(s.db_path)
    seen = {}

    def fake_fetch(client, venue, year, cache, limit, log):
        seen[year] = client.max_age
        return iter(())

    monkeypatch.setattr(ingest, "fetch_openalex", fake_fetch)
    ingest.ingest_venues(s, db, ["icml"], [2015], ["openalex"], log=lambda *_: None)
    assert seen[2015] is None  # an old year is served from the cache by default
    ingest.ingest_venues(s, db, ["icml"], [2015], ["openalex"], log=lambda *_: None, recent_from=2015)
    assert seen[2015] == ingest.RECENT_MAX_AGE


def test_update_refreshes_every_year_it_rechecks(tmp_path, monkeypatch):
    from datetime import date

    from radar import ingest
    from radar.update import run_update

    s = Settings(data_dir=tmp_path / "d")
    s.ensure_dirs()
    db = DB(s.db_path)
    ingest.track(db, ["icml"], ["openalex"], 2020)
    calls = {}

    class Stop(Exception):
        pass

    def fake_ingest(s_, db_, venues, years, sources, **kw):
        calls.update(years=years, **kw)
        raise Stop

    monkeypatch.setattr(ingest, "ingest_venues", fake_ingest)
    with pytest.raises(Stop):
        run_update(s, db, years_back=3, log=lambda *_: None)
    this = date.today().year
    assert calls["years"] == list(range(this - 3, this + 1)) and calls["recent_from"] == this - 3


def test_update_detects_release_and_new_topic(tmp_path, monkeypatch):
    from radar import ingest, pipeline
    from radar.update import changes_markdown, run_update

    s = Settings(data_dir=tmp_path / "d", layout="pca", n_clusters=6, embed_dim=32)
    s.ensure_dirs()
    db = DB(s.db_path)
    db.upsert_papers(_corpus(), "synthetic")
    ingest.track(db, ["icml"], ["openalex"], 2023)
    pipeline.run(s, db, log=lambda *_: None)

    rnd = random.Random(1)
    quantum = "quantum circuit qubit error correction variational ansatz".split()

    def fake_ingest(s_, db_, venues, years, sources, **kw):
        rows = [r | {"key": "26-" + r["key"], "year": 2026, "title": r["title"] + " v2"} for r in _corpus(seed=5) if r["year"] == 2025]
        rows += [{"key": f"q{i}", "title": " ".join(rnd.sample(quantum, 4)) + f" quantum study {i}", "venue": "conf", "year": 2026,
                  "abstract": " ".join(rnd.choices(quantum, k=60))} for i in range(150)]
        # a venue whose 2026 papers are only half indexed must not distort trends
        rows += [{"key": f"o{y}-{i}", "title": f"other venue paper {y} {i} diffusion", "venue": "other", "year": y,
                  "abstract": "diffusion model image generation denoising " * 10} for y, n in ((2025, 200), (2026, 40)) for i in range(n)]
        return db_.upsert_papers(rows, "fake")

    monkeypatch.setattr(ingest, "ingest_venues", fake_ingest)
    ch = run_update(s, db, out_dir=tmp_path / "r", log=lambda *_: None)
    rel = {(r["venue"], r["year"]) for r in ch["new_releases"]}
    assert ("conf", 2026) in rel and ch["n_new_papers"] > 600
    assert any("quantum" in t["label"] or "qubit" in t["label"] for t in ch["new_topics"]), (ch["new_topics"], db.read_table("clusters").label.tolist())
    assert "other 2026" in db.get_meta("trend_info")["incomplete_venue_years"]
    assert "New releases" in changes_markdown(ch) and (tmp_path / "r" / "CHANGES.md").exists()

    monkeypatch.setattr(ingest, "ingest_venues", lambda *a, **k: (0, 0))
    ch2 = run_update(s, db, out_dir=tmp_path / "r", log=lambda *_: None)
    assert ch2.get("no_change") and len(db.get_meta("update_history")) == 2
