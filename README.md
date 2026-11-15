# Research Radar

Map an entire research field from its conference papers, measure where it is
moving, find the gaps, and test your own ideas against everything already
published. It runs on a laptop CPU, needs no API keys, and comes with an
interactive web dashboard.

It grew out of [RTanalysis](https://github.com/Faysal-star/RTanalysis), a
pipeline that turned ICML/ICLR 2024–2026 into a trend report and a reading
list. Research Radar keeps the same idea (measure the field first, so you
stop reasoning only from what you happen to have read) and extends it to every major
ML venue, a live dashboard, and an idea-testing loop.

```
pip install -e .
radar demo path/to/RTanalysis      # 24k ICML/ICLR papers -> full analysis in ~2 min
radar serve                        # http://127.0.0.1:8000
```

---

## What you get

| Page | What it answers |
|---|---|
| **Overview** | What is growing, what is cooling, which topics look like openings, what new vocabulary appeared this year |
| **Landscape map** | Every paper placed by meaning (zoom, pan, click to read). Shaded by the opportunity score of its topic; filter by theme, year, orals/spotlights |
| **Topics & scores** | Sortable table of every topic with 10+ measurements and share sparklines. **Drag the weights and the ranking updates live** |
| **Topic page** | Share-per-year chart, forecast, neighbouring topics, most active authors, central/highlighted/cited/recent papers, every admitted open problem, position-paper claims, papers that sit between this topic and another, and a reading list |
| **Emerging terms** | New, rising and fading words and phrases (log-odds with an informative Dirichlet prior), plus a curve for any term you type |
| **Gaps & transplants** | Method × domain heatmap of observed vs expected papers, the biggest untried combinations, neighbouring topics that rarely meet, a searchable list of admitted open problems, and what position papers argue |
| **Ideas** | 40 evidence-backed idea seeds, each traced to a measurement and scored for novelty. With an LLM: research question, falsifiable hypothesis, killing experiment, first-week plan |
| **Idea lab** | Paste an idea and get: novelty score, which topics it lands in and how they are trending, the closest existing papers, nearby open problems, and a 4-tier reading list |

There is also a CLI for everything, and a `TREND_REPORT.md`/`.html` you can share.

## What's new compared with RTanalysis

| | RTanalysis | Research Radar |
|---|---|---|
| Venues | ICML, ICLR | 22 venues registered (NeurIPS, ICML, ICLR, CVPR, ICCV, ECCV, ACL, EMNLP, NAACL, AAAI, IJCAI, KDD, CoRL, COLM, TMLR, …) plus arXiv and your own CSV/JSON files |
| Sources | scraped conference pages | OpenAlex (abstracts, institutions, **citations**), Semantic Scholar, OpenReview (oral/spotlight decisions), arXiv, with cached, resumable, rate-limited fetching and cross-source deduplication |
| Hardware | GPU (~15 min) | laptop CPU, ~90 s for 24k papers (neural embeddings optional) |
| Clustering | UMAP+HDBSCAN, 40 % of papers discarded as noise | every paper kept, with confidence and runner-up topic; two levels (topics → themes); papers near a boundary surfaced as *bridges* |
| Title-only years | assigned by title | assigned by title, **and every year is counted the same way**, so a topic cannot look like it is growing just because recent years have abstracts (see *Validity* below) |
| Trend metrics | momentum, reward, entry cost, concentration | + acceleration, one-year forecast, citation impact, openness, arXiv leading indicator, a composite opportunity score with visible weights, and auto tags (sweet spot / niche gem / hot & crowded / cooling) |
| Gaps | open problems, position claims, transplants | + typed open problems (open question / limitation / missing evaluation / future work), statistically scored transplants with method growth, under-connected neighbouring topics |
| Ideas | manual | generated seeds, novelty scoring calibrated against the corpus, tiered reading lists with no repeats, optional LLM refinement and critique |
| Output | Markdown/PDF report | web dashboard + Markdown/HTML report + CLI |

## Install

Python 3.11+.

```bash
git clone <this repo> && cd research-radar
pip install -e .              # core: numpy, pandas, scikit-learn, fastapi
pip install -e ".[semantic]"  # optional: better embeddings on CPU (fastembed)
pip install -e ".[dev]"       # optional: tests
```

## Build a corpus

```bash
radar venues                                            # list known venues

# Conference papers. OpenAlex gives abstracts + citations; OpenReview gives oral/spotlight tiers.
radar ingest venues --venues neurips,icml,iclr --years 2022-2025 --sources openalex,openreview
radar ingest venues --venues cvpr,acl,emnlp --years 2023-2025 --sources openalex,s2

# Recent preprints, used as a leading indicator (what is coming next year)
radar ingest arxiv --start 2025-06-01 --categories cs.LG,cs.CL,cs.CV

# Reuse the RTanalysis corpus, or any CSV/JSONL with a title column
radar ingest rtanalysis ../RTanalysis
radar ingest file my_papers.csv --venue neurips --year 2025

radar status
```

Every request is cached in `data/cache/`, so an interrupted crawl resumes and a
re-run costs nothing. The same paper from several sources is merged on title
and year, keeping the richest version of each field. A preprint merges into its
conference version, and the venue record wins.

Tips:
- Set `contact_email` in `radar.toml` to join OpenAlex's faster "polite pool".
- Semantic Scholar works without a key but is slow. A free key from
  semanticscholar.org raises the limit (`s2_api_key`).
- OpenReview sometimes serves a bot challenge to scripts (RTanalysis hit this).
  When it does, the source is skipped and the others still run.
- `--limit 50` fetches a small sample per venue-year, which is handy for a quick test.

## Analyse

```bash
radar analyze                       # embed -> cluster -> gaps -> trends -> terms -> ideas
radar analyze --from trends         # re-run from any stage
radar analyze --backend fastembed   # semantic embeddings (downloads ~130 MB once)
radar analyze --clusters 80 --layout umap
radar report                        # reports/TREND_REPORT.md + .html
radar serve
```

From the terminal:

```bash
radar novelty "RL with verifiable rewards for probabilistic time-series forecasting"
radar reading "test-time scaling for diffusion language models"
radar reading --cluster 33
```

## Free LLM features (optional)

Every feature works without an LLM. With one, topic labels become readable
names with summaries, and ideas can be refined into a research question,
hypothesis, killing experiment and risk assessment. Any OpenAI-compatible
endpoint works. The free option is [Ollama](https://ollama.com):

```bash
ollama pull qwen2.5:7b
export RADAR_LLM_BASE_URL=http://localhost:11434/v1
export RADAR_LLM_MODEL=qwen2.5:7b
radar analyze --from cluster        # relabels topics
radar serve                         # "Refine" buttons appear
```

LM Studio, and the free tiers of Groq or OpenRouter (set `RADAR_LLM_API_KEY`),
work the same way.

## How the measurements work

All share-based, because venues grow every year and raw counts flatter
everything.

| Metric | Definition |
|---|---|
| momentum | topic share of papers in the latest year ÷ share in the first year |
| recent growth, acceleration | latest ÷ previous year; change in log growth rate |
| forecast | log-linear extrapolation of share, one year ahead (capped at 3×) |
| reward lift | oral+spotlight rate ÷ the rate the topic's own venue mix predicts (venues differ a lot in how many talks they award) |
| impact | mean citation percentile within each venue-year (so old papers aren't favoured) |
| openness | share of abstracts in the topic that admit an open problem, limitation or missing evaluation |
| entry cost | compute-heavy vs analysis/training-free language in abstracts, as tertiles |
| concentration | share of recent papers with an author who has ≥3 papers in the topic |
| arXiv lead | topic share on arXiv in the last 12 months ÷ share at venues |
| **opportunity** | weighted mean of the percentile ranks above. The weights are a judgement, kept visible in `radar.toml` and adjustable live |

Only venues present in both the first and last year enter share
calculations (a balanced panel), so adding NeurIPS for a single year does not
inflate every NeurIPS-heavy topic.

**Novelty** of an idea = the share of corpus papers whose nearest neighbour is
closer to them than the idea's nearest paper is to the idea. 0 means it sits on
top of existing work. 100 means it is further from everything than almost any
real paper, which can mean genuinely new or out of scope.

### Validity checks the pipeline reports

- Agreement (AMI) between discovered topics and the venues' official topic
  taxonomy. 0.3–0.5 is healthy: topics should refine the taxonomy, not copy it.
- Title-space vs abstract-space agreement for papers that have both. On the
  RTanalysis corpus this is 58 % across 63 topics. Because it is not 100 %,
  trend counts use title placement for **every** year. Mixing methods would
  make a topic look like it is growing just because recent years have abstracts. In
  testing that mix flipped spiking neural networks from declining to "rising".
- On the RTanalysis corpus the results agree with the original repo's: reasoning,
  RLVR, agents, diffusion LMs and KV-cache work rising; conformal prediction,
  fairness, privacy, GNNs and federated learning cooling.

## Project layout

```
radar/
  ingest/        venues registry, OpenAlex / S2 / OpenReview / arXiv / file importers, cached HTTP
  db.py          SQLite store + cross-source merge rules
  embed.py       tfidf (default) / fastembed / sentence-transformers / ollama backends
  cluster.py     topics, themes, labels, bridges, 2-D map
  trends.py      metrics + opportunity score
  terms.py       emerging / fading vocabulary
  gaps.py        open problems, position claims, transplants, under-connected topics
  ideas.py       semantic index, novelty, reading lists, idea seeds
  llm.py         optional OpenAI-compatible LLM layer
  report.py      Markdown + HTML report
  server.py      FastAPI backend
  web/           dashboard (vanilla JS, no build step)
tests/           parsers, merge rules, synthetic end-to-end, API
```

## Caveats

- Abstract keyword lexicons (entry cost, open problems, methods × domains) are
  heuristics. They are good at ranking and bad at exact counts. Read the sentences
  behind any number before acting on it.
- The default TF-IDF embeddings match words, not meaning. For idea checking,
  `--backend fastembed` finds paraphrased prior work much better.
- Reward lift needs venues that publish oral/spotlight decisions
  (OpenReview, or the RTanalysis import). Impact needs citations (OpenAlex/S2).
  Metrics without data show as "–" and drop out of the score.
- Novelty is distance to *this* corpus. Always read the T2 tier of the reading
  list before committing.
