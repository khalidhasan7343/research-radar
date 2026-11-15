# CLI reference

Everything is one command, `radar` (or `python -m radar`). The help text below
is the output of `radar --help` and `radar <command> --help`.

Commands marked **(network)** contact an external service. Everything else
works offline once you have a corpus.

```text
usage: radar [-h] [--data DATA] [--config CONFIG]
             {ingest,update,track,changes,venues,status,analyze,report,novelty,reading,serve,demo} ...

Research Radar: map a research field and find openings.

positional arguments:
  {ingest,update,track,changes,venues,status,analyze,report,novelty,reading,serve,demo}
    ingest              add papers to the corpus
    update              fetch new papers for everything tracked, re-analyse, report what changed
    track               show or change what `radar update` keeps current
    changes             print what changed in the last update
    venues              list known venues
    status              corpus and analysis summary
    analyze             run the analysis pipeline
    report              write TREND_REPORT.md and .html
    novelty             how crowded is the neighbourhood of an idea?
    reading             tiered reading list for an idea or topic
    serve               open the web dashboard
    demo                build a demo corpus from RTanalysis and analyze it

options:
  -h, --help            show this help message and exit
  --data DATA           data directory (default ./data)
  --config CONFIG       path to radar.toml
```

## Global options

These go **before** the command name.

| Option | Meaning |
| --- | --- |
| `--data DIR` | Data directory (database, embeddings, HTTP cache). Default `./data`, or `data_dir` from the settings. |
| `--config FILE` | Settings file. Default `./radar.toml` if it exists. See [configuration.md](configuration.md). |

```bash
radar --data ~/radar-cv status
radar --config configs/nlp.toml analyze
```

Every command (except `--help`) creates the data directory and an empty
database if they do not exist.

## ingest

```text
usage: radar ingest [-h] {venues,arxiv,rtanalysis,file} ...
```

Adds papers to the corpus. Papers already in the database are merged, not
duplicated (see [architecture.md](architecture.md#deduplication)). After every
ingest, the per-venue, per-year summary is printed.

### ingest venues (network)

```text
usage: radar ingest venues [-h] --venues VENUES --years YEARS [--sources SOURCES] [--limit LIMIT]

options:
  --venues VENUES    comma list, e.g. neurips,icml,iclr,cvpr,acl (see `radar venues`)
  --years YEARS      e.g. 2023-2025 or 2024,2025
  --sources SOURCES  comma list of openalex,s2,openreview
  --limit LIMIT      max papers per venue-year-source (testing)
```

| Flag | Default | Notes |
| --- | --- | --- |
| `--venues` | required | Keys from `radar venues`. Unknown keys are reported and skipped. |
| `--years` | required | Ranges and lists can be combined: `2019,2022-2025`. |
| `--sources` | `openalex,openreview` | `openalex`, `s2` (Semantic Scholar), `openreview`. OpenReview is skipped for venues that do not use it. |
| `--limit` | `0` (no limit) | Fetch at most this many papers per venue, year and source. Limited ingests are **not** added to tracking. |

A source that fails (for example, OpenReview returning HTTP 403) is reported and
skipped; the other sources still run. Venues ingested without `--limit` are
tracked for `radar update`.

```bash
radar ingest venues --venues neurips,icml,iclr --years 2022-2025 --sources openalex,openreview
radar ingest venues --venues cvpr,acl --years 2024,2025 --sources openalex,s2
radar ingest venues --venues iclr --years 2025 --limit 50     # quick test
```

### ingest arxiv (network)

```text
usage: radar ingest arxiv [-h] --start START [--end END] [--categories CATEGORIES]
                          [--max-per-week MAX_PER_WEEK]

options:
  --start START         YYYY-MM-DD
  --end END
  --categories CATEGORIES
                        default: cs.LG,cs.AI,cs.CL,cs.CV,cs.RO,stat.ML,...
  --max-per-week MAX_PER_WEEK
```

| Flag | Default | Notes |
| --- | --- | --- |
| `--start` | required | First submission date. |
| `--end` | today | Last submission date. |
| `--categories` | `cs.LG,cs.AI,cs.CL,cs.CV,cs.RO,stat.ML,cs.IR,cs.MA,cs.NE` | Comma list of arXiv categories. |
| `--max-per-week` | `2000` | At most this many preprints per 7-day window. |

Preprints are fetched in 7-day windows. The categories are added to tracking,
so `radar update` continues from the last date fetched.

```bash
radar ingest arxiv --start 2025-06-01 --categories cs.LG,cs.CL,cs.CV
```

### ingest rtanalysis

```text
usage: radar ingest rtanalysis [-h] path

positional arguments:
  path        path to a clone of github.com/Faysal-star/RTanalysis
```

Imports the corpus committed in the RTanalysis repository from a local clone
(`10_corpus/clean/papers.parquet` and `titles_by_year.parquet`). Cloning the
repository needs network access; the import itself does not.

```bash
radar ingest rtanalysis ../RTanalysis
```

### ingest file

```text
usage: radar ingest file [-h] [--venue VENUE] [--year YEAR] path

positional arguments:
  path

options:
  --venue VENUE
  --year YEAR
```

Imports a `.csv`, `.json`, `.jsonl`/`.ndjson` or `.parquet` file (any other
extension is read as CSV). The file needs a title column. The recognised column
names are listed in [getting-started.md](getting-started.md#from-a-file-no-network).
`--venue` and `--year` fill in rows that have no venue or year. Venue names are
mapped to registered venue keys when they match (for example "NeurIPS" becomes
`neurips`).

```bash
radar ingest file my_papers.csv --venue neurips --year 2025
```

## update (network)

```text
usage: radar update [-h] [--force] [--years-back YEARS_BACK] [--out OUT]

options:
  --force               re-analyse even if no new papers arrived
  --years-back YEARS_BACK
                        also re-check this many past years (default 1)
  --out OUT
```

Fetches new papers for every tracked venue (current year and `--years-back`
earlier years) and for tracked arXiv categories (from two days before the last
date fetched), re-runs the whole analysis if anything new arrived, and writes
`CHANGES.md`, `changes.json`, `TREND_REPORT.md` and `TREND_REPORT.html` to
`--out` (default `reports`). If nothing is tracked yet, it stops with a message
explaining how to start tracking. See [updating.md](updating.md).

```bash
radar update
radar update --years-back 2
radar update --force
```

## track

```text
usage: radar track [-h] [--venues VENUES] [--sources SOURCES] [--from-year FROM_YEAR]
                   [--arxiv ARXIV] [--remove REMOVE]

options:
  --venues VENUES
  --sources SOURCES
  --from-year FROM_YEAR
  --arxiv ARXIV         arXiv categories to follow, e.g. cs.LG,cs.CL
  --remove REMOVE       venues to stop tracking
```

With no options, prints what is tracked. Options **add** to the tracked set:
`--venues`, `--sources` and `--arxiv` take comma lists; `--from-year` records
the earliest year of interest (the smaller of the old and new value is kept);
`--remove` stops tracking the given venues. Sources and arXiv categories can be
added but not removed from the CLI.

```bash
radar track
radar track --venues cvpr,acl --sources openalex --from-year 2024 --arxiv cs.LG,cs.CL
radar track --remove acl
```

## changes

```text
usage: radar changes [-h]
```

Prints the last "what's new" summary (the same text as `reports/CHANGES.md`),
or "No update has run yet."

## venues

```text
usage: radar venues [-h]
```

Lists the registered venues: key, display name, area and whether OpenReview
is used. There are 22 conference/journal venues plus `arxiv`.

## status

```text
usage: radar status [-h]
```

Prints papers per venue and year (`n`, `with_abstract` = abstract longer than
100 characters, `with_citations`, `highlighted` = oral or spotlight), then the
stored `cluster_info`, `trend_info` and `last_run` from the last analysis.

## analyze

```text
usage: radar analyze [-h] [--from {embed,cluster,gaps,trends,terms,ideas}] [--only ONLY]
                     [--backend BACKEND] [--clusters CLUSTERS] [--layout LAYOUT] [--force-embed]

options:
  --from {embed,cluster,gaps,trends,terms,ideas}
  --only ONLY           comma list of stages
  --backend BACKEND     tfidf | fastembed | sentence-transformers | ollama
  --clusters CLUSTERS   number of topics (default: automatic)
  --layout LAYOUT       tsne | umap | pca
  --force-embed
```

| Flag | Default | Notes |
| --- | --- | --- |
| `--from` | `embed` | Run this stage and every later one. |
| `--only` | all | Run only these stages, e.g. `--only terms` or `--only trends,ideas`. |
| `--backend` | `tfidf` | Embedding backend for this run; overrides the settings. `fastembed` needs the `semantic` extra and downloads a model on first use; `sentence-transformers` needs the `sbert` extra; `ollama` needs a running Ollama server. |
| `--clusters` | automatic | Number of topics. |
| `--layout` | `tsne` | 2-D map layout. `umap` needs the `umap` extra and falls back to t-SNE if it is missing. |
| `--force-embed` | off | Recompute embeddings even if the cache is up to date. |

After a full run (no `--only`), the change compared with the previous analysis
is written to `reports/CHANGES.md` and `reports/changes.json`, as with
`radar update`. Stages and their outputs are described in
[how-it-works.md](how-it-works.md).

```bash
radar analyze
radar analyze --from trends
radar analyze --only terms
radar analyze --clusters 80 --layout pca
radar analyze --backend fastembed           # needs network the first time (model download)
```

Search, novelty and the dashboard use the backend saved with the embeddings
(`data/embeddings/backend.joblib`). But the embed stage re-embeds whenever the
configured backend differs from the cached one, so a later `radar analyze` or
`radar update` without `--backend fastembed` switches back to TF-IDF. To keep a
non-default backend, set `embed_backend` in `radar.toml` (or
`RADAR_EMBED_BACKEND`) instead of using the flag.

## report

```text
usage: radar report [-h] [--out OUT]
```

Writes `TREND_REPORT.md` and `TREND_REPORT.html` to `--out` (default
`reports`). Needs a completed analysis.

```bash
radar report
radar report --out shared/
```

## novelty

```text
usage: radar novelty [-h] [-k K] idea
```

Scores how crowded the neighbourhood of an idea is (0 to 100), lists the three
nearest topics and the `-k` closest papers (default 15). Needs a completed
analysis. The score is defined in [how-it-works.md](how-it-works.md#novelty-scoring).

```bash
radar novelty "RL with verifiable rewards for probabilistic time-series forecasting"
radar novelty -k 30 "sparse autoencoders for protein language models"
```

## reading

```text
usage: radar reading [-h] [--cluster CLUSTER] [idea]
```

Prints a tiered reading list for an idea, or for a topic with `--cluster`.
Topic numbers appear in dashboard URLs (`#/topic/12`) and change whenever
clustering re-runs.

```bash
radar reading "test-time scaling for diffusion language models"
radar reading --cluster 12
```

## serve

```text
usage: radar serve [-h] [--host HOST] [--port PORT]
```

Starts the dashboard at `http://HOST:PORT` (default `127.0.0.1:8000`). See
[dashboard.md](dashboard.md). The server has no authentication; keep the
default host unless you know who can reach the machine.

```bash
radar serve
radar serve --port 8080
```

## demo

```text
usage: radar demo [-h] path

positional arguments:
  path        path to a clone of RTanalysis
```

Imports the RTanalysis corpus from a local clone, runs the full analysis and
writes `reports/TREND_REPORT.md` and `.html`.

```bash
git clone https://github.com/Faysal-star/RTanalysis.git ../RTanalysis   # network
radar demo ../RTanalysis
radar serve
```
