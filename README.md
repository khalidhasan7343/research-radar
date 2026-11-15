# Research Radar

Research Radar maps a research field from its conference papers. It downloads
paper metadata from open sources, groups the papers into topics, measures which
topics are growing or cooling, finds gaps the field admits to, and lets you
check your own research idea against everything already published. It runs on
a laptop CPU with no API keys and comes with a web dashboard.

Built on [RTanalysis](https://github.com/Faysal-star/RTanalysis) by Faysal
Mahmud. See [CREDITS.md](CREDITS.md) for exactly what comes from it.

<!-- TODO: add a dashboard screenshot at docs/img/overview.png and show it here:
![Research Radar overview page](docs/img/overview.png) -->

## What it does

- **Builds a corpus** from 22 registered venues (NeurIPS, ICML, ICLR, CVPR, ACL,
  EMNLP, AAAI, KDD, CoRL and others; run `radar venues` for the list), recent
  arXiv preprints, and your own CSV/JSON/JSONL/parquet files. Sources are
  OpenAlex, Semantic Scholar, OpenReview and arXiv. Duplicates across sources
  are merged.
- **Groups papers into topics and themes** and places every paper on a 2-D map.
  No paper is discarded; papers that sit between two topics are flagged as
  bridges.
- **Measures each topic**: share growth (momentum), acceleration, a one-year
  forecast, oral/spotlight rate relative to the venue mix (reward lift),
  citation impact, how often abstracts admit open problems (openness),
  compute-heaviness (entry cost), repeat-author concentration, and an arXiv
  leading indicator. These are combined into an opportunity score whose weights
  you can change.
- **Finds gaps**: sentences in abstracts that admit open problems or
  limitations, what position papers argue, method x domain combinations that
  are much rarer than expected, and neighbouring topics that rarely meet.
- **Generates idea seeds** from those measurements and scores each for novelty
  against the corpus.
- **Checks your idea** (the Idea lab): a novelty score, the topics it lands in
  and how they are trending, the closest papers, nearby open problems, and a
  tiered reading list.
- **Stays up to date**: `radar update` fetches new papers for tracked venues,
  re-runs the analysis and reports what changed. A GitHub Actions workflow can
  run it on a schedule.
- **Optional LLM features** through any OpenAI-compatible endpoint, including
  free local ones (Ollama, LM Studio): readable topic names, and idea refinement
  into a research question, hypothesis and a cheap experiment that could
  falsify it.

## Quickstart

Requires Python 3.11 or newer.

```bash
git clone https://github.com/khalidhasan7343/research-radar.git
cd research-radar
pip install -e .
```

Build a corpus (needs network access). OpenAlex gives abstracts and citations;
OpenReview gives oral/spotlight decisions for venues that use it.

```bash
radar ingest venues --venues iclr,icml --years 2023-2025 --sources openalex,openreview
radar status
```

No network, or have your own list of papers? Import a file with at least a
`title` column:

```bash
radar ingest file my_papers.csv --venue neurips --year 2025
```

Analyse and open the dashboard:

```bash
radar analyze      # embed -> cluster -> gaps -> trends -> terms -> ideas
radar report       # writes reports/TREND_REPORT.md and .html
radar serve        # http://127.0.0.1:8000
```

From the terminal:

```bash
radar novelty "test-time scaling for diffusion language models"
radar reading "test-time scaling for diffusion language models"
```

[docs/getting-started.md](docs/getting-started.md) walks through a full
session, from an empty folder to a reading list.

## Staying up to date

Every venue you ingest with `radar ingest venues` is tracked. Then:

```bash
radar update     # needs network: fetch new papers, re-analyse, write reports/CHANGES.md
radar changes    # print the last "what's new"
radar track      # show or change what is tracked
```

The "what's new" report lists new venue releases, venue-years that grew, new
topics, the topics whose scores moved most, and new terms on the emerging list.

The included workflow `.github/workflows/update.yml` runs `radar update` on
GitHub Actions every Monday and Thursday. The paper database is kept in the
Actions cache, not committed, because it contains abstracts owned by their
authors and publishers. Only the reports are committed. When new papers arrive,
the workflow opens an issue with the summary, and GitHub notifies you. Setup,
cron and Windows Task Scheduler instructions are in
[docs/updating.md](docs/updating.md).

## How it works

1. **Embed**: each paper becomes a vector, once from title + abstract and once
   from the title alone. The default is TF-IDF + SVD (no download); fastembed,
   sentence-transformers and Ollama backends are optional.
2. **Cluster**: k-means on papers with abstracts defines the topics. Papers
   without abstracts are placed by their title. For trend counts, every paper is
   placed by title, so that years with and without abstracts are counted the
   same way.
3. **Gaps**: regular-expression lexicons find open-problem sentences, position
   claims and method x domain pairs.
4. **Trends**: share-based metrics per topic, computed only over venues present
   in both the first and last year, and leaving out venue-years that are still
   being indexed.
5. **Terms**: words and phrases in titles that rose or fell in the latest year.
6. **Ideas**: seeds generated from the gaps and trends, each scored for novelty.

Every metric and score is defined precisely in
[docs/how-it-works.md](docs/how-it-works.md).

## Limitations

- The lexicons (entry cost, open problems, methods, domains) are keyword
  heuristics. They rank topics reasonably but do not give exact counts. Read the
  sentences behind a number before acting on it.
- The default TF-IDF embeddings match words, not meaning. For checking ideas,
  `radar analyze --backend fastembed` (after `pip install -e ".[semantic]"`)
  finds paraphrased prior work better.
- Reward lift needs oral/spotlight decisions (OpenReview or the RTanalysis
  import). Impact needs citations (OpenAlex or Semantic Scholar). Metrics
  without data show as "–" and drop out of the opportunity score.
- Novelty is distance to the papers in *your* corpus, not to all of science.
  Always read the "closest to your idea" tier of the reading list.
- The opportunity score is a judgement. Its weights are visible and adjustable
  for that reason.

More in [docs/faq.md](docs/faq.md).

## Documentation

| Page | Covers |
| --- | --- |
| [Getting started](docs/getting-started.md) | Install, first corpus, first analysis, a typical workflow |
| [How it works](docs/how-it-works.md) | Pipeline stages and exact metric definitions |
| [CLI reference](docs/cli.md) | Every command and flag |
| [Dashboard](docs/dashboard.md) | Each page and what to do on it |
| [Updating](docs/updating.md) | Tracking, `radar update`, GitHub Actions, cron |
| [Configuration](docs/configuration.md) | Settings, environment variables, embedding backends, LLMs |
| [Data sources](docs/data-sources.md) | What each source provides, rate limits, terms of use |
| [Architecture](docs/architecture.md) | Module map, database tables, extending the code |
| [FAQ](docs/faq.md) | Caveats and common errors |

## Data and terms of use

This repository contains no paper data. Research Radar downloads metadata from
OpenAlex, Semantic Scholar, OpenReview and arXiv when you run it, and you are
responsible for following each source's terms. The database it builds
(`data/radar.db`) contains abstracts owned by their authors and publishers:
do not publish it. See [docs/data-sources.md](docs/data-sources.md).

## Credits

Research Radar is built on [RTanalysis](https://github.com/Faysal-star/RTanalysis)
by Faysal Mahmud ([Faysal-star](https://github.com/Faysal-star)), which came
first and introduced the core approach: measuring a field from its accepted
papers, share-based momentum, reward lift, entry cost and concentration,
open-problem mining, transplant analysis and tiered reading lists. Some code is
adapted from it with his permission. [CREDITS.md](CREDITS.md) lists exactly
what came from RTanalysis, along with the data sources, libraries and methods
this project relies on.

## License

[MIT](LICENSE). Copyright (c) 2026 MD Khalid Hasan.

## Contributing

Bug reports, fixes and new venues or data sources are welcome. See
[CONTRIBUTING.md](CONTRIBUTING.md) and the
[Code of Conduct](CODE_OF_CONDUCT.md). To cite the project, see
[CITATION.cff](CITATION.cff).
