# Credits

## RTanalysis by Faysal Mahmud

Research Radar is built on [RTanalysis](https://github.com/Faysal-star/RTanalysis)
by Faysal Mahmud ([Faysal-star](https://github.com/Faysal-star)). RTanalysis came
first: it turned the ICML and ICLR 2024-2026 papers into a trend report, a set
of open problems and a tiered reading list. Research Radar extends that work to
more venues and sources, an interactive dashboard and automatic updates. It
uses ideas and some code from RTanalysis with his permission.

Thank you, Faysal. The core of this project is his way of approaching the
problem.

### Ideas and approach that come from RTanalysis

- Measuring a field from its accepted papers before choosing a research
  direction, instead of reasoning only from the papers you have already read.
- Share-based momentum: a topic's share of all papers in a year, compared over
  time, rather than raw counts (venues grow every year).
- Reward lift: the oral/spotlight rate of a topic compared with the rate its own
  venue mix predicts.
- Entry cost (compute-heavy versus analysis or training-free language in
  abstracts) and author concentration (repeat authors) as metrics.
- Mining abstracts for sentences that admit open problems or limitations, and
  collecting the claims made by position papers.
- The method x domain "transplant" analysis: method and domain pairs that are
  each common but rarely appear together, compared with the count expected if
  they were independent.
- Tiered reading lists, including a tier of the papers closest to your idea, to
  read before committing to it.
- Keeping measurement separate from judgement: the metrics are reported as they
  are, and any weighting is done in the open, where it can be argued with.
- Two embedding spaces: topics are defined from title + abstract, and papers
  that only have a title are placed by comparing title vectors with title
  centroids, so trend counts compare like with like across years.
- Assigning every paper to its nearest topic rather than dropping it, and
  checking the topics against the venue's official taxonomy with adjusted
  mutual information (AMI).
- Labelling topics with class-based TF-IDF keyphrases.

### Code adapted from RTanalysis (used with his permission)

| Research Radar | Adapted from (RTanalysis) |
| --- | --- |
| `EXPENSIVE` and `CHEAP` entry-cost lexicon in `radar/trends.py` | `20_pipeline/s06_trends.py` |
| `OPEN_PATTERNS` open-problem phrases in `radar/gaps.py` | `GAP_PATTERNS` in `20_pipeline/s07_gaps.py` |
| `METHODS` and `DOMAINS` lexicons and the observed-versus-expected count in `radar/gaps.py` | `METHODS`, `DOMAINS` and `occurrence_matrix` in `20_pipeline/s07_gaps.py` |

Each of these places in the code carries a comment pointing to RTanalysis.

### What Research Radar adds

- 22 registered venues (ML, vision, NLP, AI, data mining, robotics) plus arXiv
  and your own CSV/JSON/JSONL/parquet files.
- Ingestion from OpenAlex, Semantic Scholar, OpenReview and arXiv, with cached,
  resumable, rate-limited requests and cross-source deduplication.
- A CPU-only default (TF-IDF embeddings), with optional neural embedding
  backends.
- Every paper kept with a confidence and a runner-up topic; topics grouped into
  themes; papers between two topics surfaced as bridges.
- More trend metrics: acceleration, a one-year forecast, citation impact,
  openness, an arXiv leading indicator, a balanced venue panel, a guard against
  half-published years, a composite opportunity score with visible weights, and
  signal tags.
- Typed open problems, statistically scored transplants with method growth,
  and under-connected neighbouring topics.
- Generated idea seeds, novelty scoring against the corpus, and optional LLM
  refinement.
- A web dashboard, a Markdown/HTML report and a CLI.
- `radar update` and a scheduled GitHub Actions workflow that report what
  changed.

Side by side:

| Aspect | RTanalysis | Research Radar |
| --- | --- | --- |
| Venues | ICML, ICLR | 22 registered venues, plus arXiv and your own files |
| Sources | Crawled conference sites; arXiv matching | OpenAlex, Semantic Scholar, OpenReview, arXiv; cached, resumable, rate-limited; cross-source deduplication |
| Embeddings | SPECTER sentence embeddings on a GPU | TF-IDF + SVD on a CPU by default; neural backends optional |
| Clustering | UMAP + HDBSCAN; noise points reassigned to the nearest topic and flagged | k-means; every paper kept with a confidence and runner-up topic; topics grouped into themes; bridge papers surfaced |
| Title-only years | Placed by title centroids; all years counted in title space | Same approach |
| Trend metrics | Momentum, reward lift, entry cost, concentration, fit to chosen areas | Adds acceleration, forecast, citation impact, openness, arXiv lead, balanced venue panel, partial-year guard, opportunity score with visible weights, signal tags |
| Gaps | Position papers, open-problem sentences, transplants | Adds typed open problems, transplant gap z-scores with method growth, under-connected neighbouring topics |
| Ideas | Manual, with a scoring rubric and dossier templates | Generated seeds, novelty scoring, tiered reading lists, optional LLM refinement |
| Output | Markdown and PDF report | Web dashboard, Markdown/HTML report, CLI |
| Staying current | Re-run by hand | `radar update` and a scheduled GitHub Actions workflow |

### The RTanalysis corpus

`radar ingest rtanalysis <path>` and `radar demo <path>` read the paper corpus
committed in the RTanalysis repository (`10_corpus/clean/papers.parquet` and
`10_corpus/clean/titles_by_year.parquet`) from a local clone. That corpus is not
included in this repository.

## Data sources

Research Radar downloads metadata from these services at your request. It does
not include or redistribute any of their data. See
[docs/data-sources.md](docs/data-sources.md).

- [OpenAlex](https://openalex.org)
- [Semantic Scholar](https://www.semanticscholar.org/product/api)
- [OpenReview](https://openreview.net)
- [arXiv](https://arxiv.org) (thank you to arXiv for use of its open access
  interoperability)

## Libraries

- [scikit-learn](https://scikit-learn.org): TF-IDF, SVD, k-means, agglomerative
  clustering, t-SNE, PCA, AMI
- [pandas](https://pandas.pydata.org) and [NumPy](https://numpy.org)
- [FastAPI](https://fastapi.tiangolo.com) and [uvicorn](https://www.uvicorn.org)
  for the dashboard server
- Also: SciPy, PyArrow, requests, joblib; optional fastembed,
  sentence-transformers and umap-learn

## Methods

- Emerging and fading terms use the log-odds ratio with an informative
  Dirichlet prior from Monroe, B. L., Colaresi, M. P., and Quinn, K. M. (2008),
  "Fightin' Words: Lexical Feature Selection and Evaluation for Identifying the
  Content of Political Conflict", *Political Analysis* 16(4).
  <https://doi.org/10.1093/pan/mpn018>
- Topic labels use class-based TF-IDF (c-TF-IDF) as introduced in Grootendorst,
  M. (2022), "BERTopic: Neural topic modeling with a class-based TF-IDF
  procedure", arXiv:2203.05794. <https://arxiv.org/abs/2203.05794>
