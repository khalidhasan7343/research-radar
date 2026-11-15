# Architecture

## Module map

```text
radar/
  __main__.py        `python -m radar` entry point
  cli.py             argument parsing and command dispatch (`radar ...`)
  config.py          Settings dataclass, radar.toml + RADAR_* loading, SEED
  db.py              SQLite store, paper upsert and cross-source merge rules
  text.py            title normalisation, sentence splitting, stop words, OpenAlex abstract rebuild
  ingest/
    __init__.py      ingest_venues / ingest_arxiv / ingest_rtanalysis / ingest_file, tracking
    http.py          cached, rate-limited HTTP client with retries
    sources.py       fetchers and parsers: OpenAlex, Semantic Scholar, OpenReview, arXiv, RTanalysis, files
    venues.py        venue registry, arXiv default categories, presentation-tier parsing
  embed.py           embedding backends and the on-disk embedding store
  cluster.py         topics, themes, title-space placement, labels, 2-D layout, AMI
  gaps.py            open problems, position claims, transplants, under-connected topics
  trends.py          per-topic metrics, opportunity score, tags
  terms.py           emerging / fading vocabulary
  ideas.py           semantic index, novelty, reading lists, idea seeds
  pipeline.py        runs the stages in order; each stage reads and writes the database
  update.py          snapshot, diff ("what's new"), run_update
  report.py          TREND_REPORT.md and .html
  llm.py             optional OpenAI-compatible LLM calls
  server.py          FastAPI backend for the dashboard
  web/               index.html, app.js, style.css (no build step)
tests/
  test_radar.py      parsers, merge rules, a synthetic end-to-end run, API, updates
```

Data flow:

```text
ingest/* --> db.papers --> pipeline: embed -> cluster -> gaps -> trends -> terms -> ideas --> db tables
                                                                                              |
                                      report.py <-------------------------------------------+
                                      server.py + web/ <------------------------------------+
update.py: ingest (tracked) -> pipeline -> diff -> reports/CHANGES.md
```

## Files on disk

| Path | Contents |
| --- | --- |
| `data/radar.db` | SQLite database: corpus and all analysis tables |
| `data/embeddings/full.npy`, `title.npy` | full and title vectors, one row per paper |
| `data/embeddings/meta.json` | paper keys (row order), backend name, cache signature |
| `data/embeddings/backend.joblib` | the fitted backend, used to embed queries |
| `data/embeddings/centroids.npy` | topic centroids |
| `data/cache/<source>/*.txt` | cached HTTP responses |
| `reports/` | `TREND_REPORT.md`, `TREND_REPORT.html`, `CHANGES.md`, `changes.json` |

## Database tables

`papers` and `meta` are created by `db.py`. The other tables are written by the
pipeline (each stage replaces its tables).

| Table | Written by | One row per | Main columns |
| --- | --- | --- | --- |
| `papers` | ingest | paper | `key`, `title`, `title_norm`, `abstract`, `authors` (JSON), `institutions` (JSON), `venue`, `year`, `presentation`, `paper_type`, `topic`, `topic_source`, `url`, `doi`, `arxiv_id`, `citations`, `date`, `sources` (JSON) |
| `meta` | various | key | `k`, `v` (JSON) |
| `paper_cluster` | cluster | paper | `key`, `cluster`, `cluster2`, `cluster_trend`, `theme`, `confidence`, `margin`, `space`, `x`, `y` |
| `clusters` | cluster | topic | `cluster`, `theme`, `label`, `keywords`, `size`, `representatives`, `cx`, `cy`, `summary` |
| `themes` | cluster | theme | `theme`, `label`, `keywords`, `clusters`, `size` |
| `open_problems` | gaps | sentence | `key`, `cluster`, `kind`, `year`, `venue`, `sentence` |
| `position_claims` | gaps | sentence | `key`, `cluster`, `year`, `title`, `claim` |
| `transplants` | gaps | method x domain pair | `method`, `domain`, `observed`, `expected`, `ratio`, `gap_z`, `method_total`, `domain_total`, `method_growth` |
| `transplant_observed`, `transplant_expected` | gaps | method | one column per domain |
| `bridges` | gaps | topic pair | `a`, `b`, `similarity`, `n_bridge`, `size_a`, `size_b`, `expected`, `underconnected` |
| `bridge_papers` | gaps | paper | `key`, `cluster`, `cluster2`, `margin` |
| `trends` | trends | topic | all metrics in [how-it-works.md](how-it-works.md#metrics-per-topic), `pct_*` percentiles, `opportunity`, `tag` |
| `cluster_year` | trends | topic x year | `cluster`, `year`, `n` (panel), `share` (%), `n_all` (all venues) |
| `terms` | terms | term | `term`, `z`, `status`, `counts` (JSON), `per_1000` (JSON) |
| `ideas` | ideas | seed | `idea_id`, `kind`, `title`, `rationale`, `evidence_score`, `cluster`, `novelty`, `best_similarity`, `nearest` (JSON) and kind-specific columns |

`meta` keys: `tracking`, `openalex_sources` (resolved OpenAlex source ids),
`cluster_info`, `trend_info`, `weights`, `last_run`, `changes`,
`update_history`.

## Deduplication

`DB.upsert_papers` in `radar/db.py`:

1. A paper whose `key` already exists is merged into that row.
2. Otherwise, rows with the same normalised title (lowercase ASCII, punctuation
   removed) within one year are candidates. A candidate matches if it is the
   same year and the same venue, or if either record is from arXiv (a preprint
   and its venue version, up to one year apart). Two different venues never
   merge.
3. Merging keeps the longer string for text fields, the longer author and
   institution lists, the higher citation count and the union of sources. When
   the existing record is a preprint and the new one is not, the venue, year and
   paper type of the venue record win. The `topic` is chosen by where it came
   from (`topic_source`): an official venue taxonomy (OpenReview, RTanalysis)
   beats other sources (such as OpenAlex), which beat arXiv categories; between
   equals, the longer label wins.

Databases created before the `topic_source` column existed are upgraded when
they are opened (`DB._migrate`): the column is added, and papers that came from
a single source get that source.

## Adding a venue

Add an entry to `VENUES` in `radar/ingest/venues.py`. An illustrative example
(check each name against the source before relying on it):

```python
"icassp": {"name": "ICASSP", "s2": "ICASSP",
           "openalex": "International Conference on Acoustics, Speech and Signal Processing",
           "openreview": "", "area": "audio"},
```

- `name`: display name.
- `s2`: the value Semantic Scholar uses in its `venue` filter.
- `openalex`: the search string used to find the OpenAlex source; the source
  with type `conference` and the most works among the top results is chosen.
- `openreview`: the OpenReview v2 venue id with `{year}`, or `""`.
- `area`: a coarse field label. Currently it is only shown by `radar venues`.

Then try it on a small sample and check the counts:

```bash
radar ingest venues --venues icassp --years 2024 --limit 50
radar status
```

## Adding a data source

1. In `radar/ingest/sources.py`, write a parser that turns one API record into a
   dict with the `papers` columns (`key`, `title`, `abstract`, `authors`,
   `venue`, `year`, ...), and a generator `fetch_<source>(client, venue, year,
   limit, log)` that pages through the API with the `Client` from
   `radar/ingest/http.py`. Give keys a unique prefix (`"mysource:" + id`).
2. In `radar/ingest/__init__.py`, create a client with a suitable
   `min_interval` in `ingest_venues` and add a branch for the source name. For a
   source that is not organised by venue and year, add a function like
   `ingest_arxiv` and a subcommand in `radar/cli.py`.
3. Add a parser test with a recorded response shape in `tests/test_radar.py`
   (tests must not use the network).
4. Document it in `docs/data-sources.md`, including its terms of use.

## Adding a metric

1. Compute it in `compute_trends` in `radar/trends.py` as a new column of `out`,
   one value per topic, using `NaN` when there is not enough data.
2. To include it in the opportunity score, add it to `COMPONENTS` (weight name
   -> column, higher-is-better) and give it a default weight in
   `Settings.weights` in `radar/config.py` and in `radar.toml.example`.
3. To show it, add it to `COLS` in `radar/web/app.js` (Topics table) and,
   if wanted, to `cols` in `build_report` in `radar/report.py`.
4. Add a test on the synthetic corpus in `tests/test_radar.py`, and define it in
   `docs/how-it-works.md`.

## Reproducibility

`radar/config.py` defines `SEED`, used for k-means, SVD, t-SNE/UMAP/PCA and
sampling, so re-running the analysis on the same corpus and settings gives the
same topics.

## HTTP API

The dashboard uses these endpoints (`radar/server.py`); they return JSON.

| Method | Path | Returns |
| --- | --- | --- |
| GET | `/api/overview` | corpus summary, analysis info, top/fastest/cooling topics, last changes |
| GET | `/api/topics` | all topics with metrics, share series, themes |
| POST | `/api/rescore` | opportunity per topic for `{"weights": {...}}` |
| GET | `/api/topics/{cid}` | one topic: metrics, papers, open problems, claims, neighbours, bridge papers |
| GET | `/api/map` | 2-D points and topic label positions (`?theme=`) |
| GET | `/api/terms` | emerging terms |
| GET | `/api/term?q=` | per-year rate of a term in titles |
| GET | `/api/gaps` | transplants, heatmap matrices, bridges, claims |
| GET | `/api/open_problems` | filtered open problems (`q`, `cluster`, `kind`, `limit`) |
| GET | `/api/search?q=&k=` | nearest papers |
| POST | `/api/novelty` | novelty for `{"text": ..., "k": ...}` |
| POST | `/api/reading` | reading list for `{"text": ...}` or `{"cluster": ...}` |
| GET | `/api/ideas` | idea seeds |
| POST | `/api/ideas/refine` | LLM refinement for `{"title": ..., "rationale": ...}` |
| GET | `/api/paper/{key}` | one paper |
| POST | `/api/reload` | reload the analysis from the database |
