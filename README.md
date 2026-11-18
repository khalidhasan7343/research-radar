# Research Radar

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Runs on CPU](https://img.shields.io/badge/runs%20on-laptop%20CPU-lightgrey.svg)](docs/getting-started.md)

**Map a research field from its conference papers, see where it is heading,
and check whether your idea is new.**

Research Radar downloads paper metadata from open sources and groups the papers
into topics. It measures which topics are growing or cooling, finds the gaps
authors admit to, and checks your own idea against everything already
published. It runs on a laptop CPU, needs no API keys, and comes with a web
dashboard.

<!-- TODO: add a dashboard screenshot at docs/img/overview.png and show it here:
![Research Radar overview page](docs/img/overview.png) -->

**New here?** Read the one-page [User manual](docs/user-manual.md).

---

## Who it is for

- **PhD students and early researchers** choosing a direction or a thesis topic.
- **Researchers moving into a new area** who want the lay of the land quickly.
- **Advisors and labs** tracking what major venues reward, every few days.
- **Anyone with a new idea** who wants to know who has done it already.

## What it does

| | |
| --- | --- |
| **Builds a corpus** | 22 venues (NeurIPS, ICML, ICLR, CVPR, ACL, EMNLP, AAAI, KDD, CoRL, ...), arXiv preprints, and your own CSV/JSON/parquet files. Duplicates across sources are merged. |
| **Finds topics** | Groups papers into topics and themes and places every paper on a 2-D map. Papers between two topics are flagged as bridges. |
| **Measures trends** | Per topic: momentum, acceleration, a one-year forecast, reward lift (oral/spotlight rate), citation impact, openness, entry cost, author concentration and an arXiv leading indicator, combined into an **opportunity score** with weights you control. |
| **Finds gaps** | Sentences where authors admit open problems, position-paper claims, method x domain combinations rarer than expected, and neighbouring topics that rarely meet. |
| **Checks your idea** | A novelty score, the topics the idea lands in and their trends, the closest papers, nearby open problems and a tiered reading list. |
| **Stays current** | `radar update` fetches new papers, re-analyses and reports what changed. A GitHub Actions workflow can run it twice a week. |
| **Optional LLM** | Any OpenAI-compatible endpoint, including free local ones (Ollama, LM Studio), for readable topic names and for refining an idea into a research question and a cheap falsifying experiment. |

## Quickstart

Requires Python 3.11 or newer.

```bash
git clone https://github.com/khalidhasan7343/research-radar.git
cd research-radar
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

**1. Build a corpus** (needs network; a few minutes per venue-year):

```bash
radar ingest venues --venues iclr,icml --years 2023-2025
radar status        # papers per venue-year, plus warnings if coverage looks wrong
```

**2. Analyse and explore:**

```bash
radar analyze       # embed -> cluster -> gaps -> trends -> terms -> ideas
radar serve         # dashboard at http://127.0.0.1:8000
radar report        # reports/TREND_REPORT.md and .html
```

**3. Check an idea:**

```bash
radar novelty "test-time scaling for diffusion language models"
radar reading "test-time scaling for diffusion language models"
```

No network? Import any file with a `title` column:
`radar ingest file my_papers.csv --venue neurips --year 2025`.

> **Tip:** for better topics and idea checks, install the semantic extra and use
> neural embeddings: `pip install -e ".[semantic]"` then
> `radar analyze --backend fastembed`.

## The dashboard

| Page | What you do there |
| --- | --- |
| **Overview** | See top opportunities, what is growing and cooling, and what is new since the last update |
| **Landscape map** | Explore every paper in 2-D; zoom, filter by theme or year |
| **Topics & scores** | Sort topics by any metric; re-weight the opportunity score live |
| **Topic page** | Read papers, open problems, position claims and a reading list |
| **Emerging terms** | See words and phrases rising or fading in titles |
| **Gaps & transplants** | Find untried method x domain pairs and under-connected topics |
| **Ideas / Idea lab** | Browse generated seeds, or test your own idea |
| **Search** | Find any paper |

Details: [docs/dashboard.md](docs/dashboard.md).

## Data sources

| Source | Provides | Default |
| --- | --- | --- |
| [Semantic Scholar](https://www.semanticscholar.org/product/api) | Full proceedings, abstracts, authors, citations | Yes |
| [OpenAlex](https://openalex.org) | Citations, institutions, topics | Yes |
| [arXiv](https://info.arxiv.org/help/api/) | Recent preprints (leading indicator) | Opt-in: `radar ingest arxiv` or `radar track --arxiv` |
| [OpenReview](https://openreview.net) | Oral/spotlight/poster decisions | Opt-in. It currently blocks anonymous API clients, so reward lift needs the [RTanalysis](https://github.com/Faysal-star/RTanalysis) import. |

Every response is cached in `data/cache/`, so interrupted crawls resume and
re-runs are free. See [docs/data-sources.md](docs/data-sources.md).

## Staying up to date

Every full ingest is tracked. Then:

```bash
radar update                      # fetch new papers, re-analyse, write reports/CHANGES.md
radar changes                     # print the last "what's new"
radar track --arxiv cs.LG,cs.CL   # also follow arXiv categories
```

The included workflow [`.github/workflows/update.yml`](.github/workflows/update.yml)
runs `radar update` every Monday and Thursday. When new papers arrive, it opens
an issue with the summary. The paper database is kept in the Actions cache,
never committed. Setup, cron and Windows Task Scheduler instructions are in
[docs/updating.md](docs/updating.md).

## How it works

1. **Embed**: each paper becomes a vector (TF-IDF + SVD by default; fastembed,
   sentence-transformers or Ollama optional).
2. **Cluster**: k-means on papers with abstracts defines topics. Title-only
   papers are placed by title.
3. **Gaps**: lexicons find open-problem sentences, position claims and
   method x domain pairs.
4. **Trends**: share-based metrics per topic over a balanced venue panel,
   leaving out venue-years that are still being indexed.
5. **Terms**: words and phrases that rose or fell in the latest year.
6. **Ideas**: seeds generated from gaps and trends, each scored for novelty.

Every metric is defined exactly in [docs/how-it-works.md](docs/how-it-works.md).

## Limitations

- The numbers describe **your corpus**, not the whole field. Use them to rank
  and compare topics, then read the papers behind them.
- Lexicon-based signals (open problems, entry cost, methods, domains) are
  keyword heuristics: pointers to read, not exact counts.
- The default TF-IDF embeddings match words, not meaning. Use
  `--backend fastembed` when checking ideas.
- Metrics without data (for example, reward lift without oral/spotlight
  decisions) show as "–" and drop out of the opportunity score.
- The opportunity score is a judgement. Its weights are visible and adjustable
  for that reason.

More in [docs/faq.md](docs/faq.md).

## Documentation

| Page | Covers |
| --- | --- |
| [User manual](docs/user-manual.md) | **Start here.** Every everyday task on one page |
| [Getting started](docs/getting-started.md) | A full first session, step by step |
| [CLI reference](docs/cli.md) | Every command and flag |
| [Dashboard](docs/dashboard.md) | Each page and what to do on it |
| [How it works](docs/how-it-works.md) | Pipeline stages and exact metric definitions |
| [Updating](docs/updating.md) | Tracking, `radar update`, GitHub Actions, cron |
| [Configuration](docs/configuration.md) | Settings, environment variables, embedding backends, LLMs |
| [Data sources](docs/data-sources.md) | What each source provides, rate limits, terms of use |
| [Architecture](docs/architecture.md) | Module map, database tables, extending the code |
| [FAQ](docs/faq.md) | Caveats and common errors |

## Data and terms of use

This repository contains no paper data. Research Radar downloads metadata from
Semantic Scholar, OpenAlex, arXiv and OpenReview when you run it. You are
responsible for following each source's terms. The database it builds
(`data/radar.db`) contains abstracts owned by their authors and publishers, so
do not publish it. See [docs/data-sources.md](docs/data-sources.md).

## Credits

Research Radar is built on [RTanalysis](https://github.com/Faysal-star/RTanalysis)
by Faysal Mahmud ([Faysal-star](https://github.com/Faysal-star)). RTanalysis came
first and introduced the core approach: measuring a field from its accepted
papers, share-based momentum, reward lift, entry cost and concentration,
open-problem mining, transplant analysis and tiered reading lists. Some code is
adapted from it with his permission. [CREDITS.md](CREDITS.md) lists exactly
what came from RTanalysis, along with the data sources, libraries and methods
this project relies on.

## Contributing

Bug reports, fixes, and new venues or data sources are welcome. See
[CONTRIBUTING.md](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md).
To cite the project, see [CITATION.cff](CITATION.cff).

## License

[MIT](LICENSE). Copyright (c) 2026 MD Khalid Hasan.
