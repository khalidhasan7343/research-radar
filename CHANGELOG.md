# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org).

## [Unreleased]

### Added

- Coverage warnings in `radar status` and after `radar ingest`. They flag
  tracked venues with no papers, venue-years that look partial (`--limit`
  fetches or not yet indexed), years with few abstracts, a corpus with no
  oral/spotlight data, and arXiv outnumbering conference papers.
- `docs/user-manual.md`: a one-page guide to everyday use.
- Ingest warns when a source returns no papers for a venue-year.

### Changed

- The default ingest sources are now `s2,openalex` (CLI, `radar update` hint
  and the GitHub Actions workflow). OpenReview now answers anonymous API
  clients with an HTTP 403 bot challenge, so it is opt-in. On a 401/403 a source
  is reported once and skipped for the rest of the run, instead of failing once
  per venue-year.
- README rewritten: who it is for, a three-step quickstart, dashboard and data
  source tables, and a link to the user manual.

### Fixed

- Openness counted open-problem papers from arXiv and from held-back venue-years
  in its numerator but not in its denominator, inflating it for topics popular on
  arXiv. Both now count only the topic's rich conference papers;
  `n_open_problems` likewise.
- `radar update --years-back N` with N > 1 read older years from the HTTP cache
  and never found new papers in them. Every year it re-checks is now refreshed.
- The AMI validity check compared topics against a mix of taxonomies (OpenReview
  areas, OpenAlex topics, arXiv categories). Papers now record where their topic
  came from (`topic_source`, added automatically to existing databases), merges
  prefer the venue's official taxonomy, and AMI uses official topics only.
- The landscape map subtitle no longer says "t-SNE" when another layout is used.
- Corrected code comments that disagreed with the code (number of topics and
  themes, theme linkage, use of the venue `area` field, where the contact email
  is sent) and the default User-Agent URL.

## [1.0.0] - 2026-11-15

First public release. Research Radar is built on
[RTanalysis](https://github.com/Faysal-star/RTanalysis) by Faysal Mahmud; see
[CREDITS.md](CREDITS.md).

### Added

- Corpus building from 22 registered venues plus arXiv: `radar ingest venues`
  (OpenAlex, Semantic Scholar, OpenReview), `radar ingest arxiv`,
  `radar ingest rtanalysis` and `radar ingest file` (CSV, JSON, JSONL, parquet).
- Cached, resumable, rate-limited HTTP client with retries, and cross-source
  deduplication that merges preprints into their venue versions.
- Analysis pipeline (`radar analyze`): embeddings (TF-IDF by default; fastembed,
  sentence-transformers and Ollama optional), k-means topics with confidence and
  runner-up topic, themes, c-TF-IDF labels, title-space placement for title-only
  papers, 2-D map.
- Gaps: typed open-problem sentences, position-paper claims, method x domain
  transplants with gap z-scores and method growth, under-connected topic pairs
  and bridge papers.
- Trends: momentum, recent growth, acceleration, one-year forecast, reward lift,
  citation impact, openness, entry cost, concentration, arXiv lead, a composite
  opportunity score with configurable weights, and signal tags; balanced venue
  panel.
- Emerging and fading terms (log-odds ratio with an informative Dirichlet
  prior).
- Idea seeds with novelty scores, `radar novelty` and tiered reading lists
  (`radar reading`).
- Optional OpenAI-compatible LLM layer for topic labels and idea refinement.
- Web dashboard (`radar serve`): Overview, Landscape map, Topics & scores with
  live re-weighting, topic pages, Emerging terms, Gaps & transplants, Ideas, Idea
  lab, Search.
- Markdown and HTML trend report (`radar report`).
- Staying current: tracking (`radar track`), `radar update` with a "what's new"
  diff (new releases, grown venue-years, new topics, movers, new terms),
  `radar changes`, a guard that leaves partially indexed venue-years out of
  trend metrics, and a scheduled GitHub Actions workflow that opens an issue
  when new papers arrive.
- Documentation in `docs/`, MIT license, credits, citation file and community
  files.

### Changed

- The GitHub Actions workflow keeps the paper database in the Actions cache
  instead of committing it, commits only the reports, runs twice a week, and
  can rebuild the database from repository variables if the cache is lost.

[Unreleased]: https://github.com/khalidhasan7343/research-radar/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/khalidhasan7343/research-radar/releases/tag/v1.0.0
