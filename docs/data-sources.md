# Data sources

Research Radar does not ship any paper data. When you run `radar ingest` or
`radar update`, it downloads metadata from the services below and stores it in
your local database (`data/radar.db`).

## Your responsibilities

- **Follow each source's terms of use.** Read them before you crawl; they can
  change, and they are what governs your use of the data, not this project's
  license. Links are below.
- **Do not publish the database.** `data/radar.db` (and any copy or export of it)
  contains paper abstracts, which are owned by their authors and publishers.
  Keep it on your own machine or in private storage. The included GitHub
  Actions workflow keeps it in the Actions cache and commits only reports (see
  [updating.md](updating.md)).
- **Be polite.** Set `contact_email` so API operators can reach you, keep the
  built-in rate limits, and do not run several crawls against the same service
  in parallel.
- Reports and screenshots you share should quote at most short excerpts.

## Summary

| Source | Used by | API key | What it provides to Research Radar |
| --- | --- | --- | --- |
| OpenAlex | `ingest venues --sources openalex` | no | abstracts, authors, institutions, citation counts, DOI, arXiv id, OpenAlex primary topic, publication date |
| Semantic Scholar | `ingest venues --sources s2` | optional | abstracts (when available), authors, citation counts, DOI, arXiv id, publication date |
| OpenReview | `ingest venues --sources openreview` | no | accepted papers with abstracts, authors, oral/spotlight/poster decision, primary area, position papers |
| arXiv | `ingest arxiv`, `update` | no | preprints with abstracts, authors, categories, submission date |
| RTanalysis | `ingest rtanalysis`, `demo` | no | the ICML/ICLR corpus committed in that repository (read from your local clone) |
| Your files | `ingest file` | no | whatever columns your file has |

## How requests are made

All HTTP requests go through `radar/ingest/http.py`:

- **Cache.** Every response is stored in `data/cache/<source>/`. Re-running an
  ingest reads from the cache, so an interrupted crawl resumes where it stopped.
  Responses for the current and previous year are re-fetched once they are more
  than 5 days old; arXiv responses always are. Older responses are kept until
  you delete the cache folder.
- **Rate limiting.** A minimum interval between requests per source (below).
- **Retries.** Up to 5 attempts with exponential back-off starting at 2 seconds
  (at most 120 seconds), honouring a numeric `Retry-After` header. HTTP 400,
  401, 403 and 404 are not retried; that source is skipped for that venue-year
  and the others still run.
- **User-Agent.** `research-radar/1.0 (mailto:<contact_email>)` when
  `contact_email` is set. Your email is then sent to all four services.

The intervals below are what Research Radar uses. They are not the services'
official limits, which you should check in their documentation.

## OpenAlex

- API: `https://api.openalex.org`. Documentation:
  <https://docs.openalex.org>; rate limits and authentication:
  <https://docs.openalex.org/how-to-use-the-api/rate-limits-and-authentication>.
- How it is used: the venue is resolved to an OpenAlex source by a search on the
  venue's name (the result is cached in the database), then works are listed
  with `primary_location.source.id` and `publication_year` filters, 200 per
  page. Abstracts are rebuilt from OpenAlex's inverted index.
- Interval: 0.12 s between requests.
- Contact email: OpenAlex asks API users to identify themselves and gives
  identified clients better service. Set `contact_email`.
- Caveat: if the name search resolves to the wrong source, the venue's papers
  will be wrong or missing. Check `radar status` after a first ingest.

## Semantic Scholar

- API: `https://api.semanticscholar.org/graph/v1`, bulk paper search filtered by
  venue and year. Documentation and license:
  <https://www.semanticscholar.org/product/api> and
  <https://www.semanticscholar.org/product/api/license>.
- Interval: 1.1 s without a key, 0.2 s with `s2_api_key`.
- API key: optional; request one from Semantic Scholar to raise your limit. Keep
  it in `radar.toml` or the `RADAR_S2_API_KEY` environment variable, never in
  the repository.
- Caveat: many records have no abstract.

## OpenReview

- API: `https://api2.openreview.net` (API v2), notes filtered by
  `content.venueid`. Documentation: <https://docs.openreview.net>. Terms:
  <https://openreview.net/legal/terms>.
- Only venues with an OpenReview id in `radar/ingest/venues.py` are fetched
  (`radar venues` shows `openreview=yes`). Submissions marked submitted,
  withdrawn or rejected are skipped. The presentation tier is read from the
  venue string (oral, spotlight, poster), and titles starting with "Position:"
  are marked as position papers.
- Interval: 0.5 s.
- Caveat: OpenReview sometimes answers scripts with an HTTP 403 challenge. When
  that happens the source is skipped and the others still run. Without OpenReview
  (or the RTanalysis import), reward lift has no data.

## arXiv

- API: `https://export.arxiv.org/api/query`. Documentation:
  <https://info.arxiv.org/help/api/index.html>. Terms of use:
  <https://info.arxiv.org/help/api/tou.html>.
- Queries by category and submission date, in 7-day windows, 200 results per
  request, up to `--max-per-week` (default 2,000) per window.
- Interval: 3.1 s, because arXiv asks for at least 3 seconds between requests.
- Default categories: `cs.LG`, `cs.AI`, `cs.CL`, `cs.CV`, `cs.RO`, `stat.ML`,
  `cs.IR`, `cs.MA`, `cs.NE`.
- Thank you to arXiv for use of its open access interoperability.

## RTanalysis

`radar ingest rtanalysis <path>` reads `10_corpus/clean/papers.parquet` and
`10_corpus/clean/titles_by_year.parquet` from a local clone of
<https://github.com/Faysal-star/RTanalysis>. The corpus is not included in this
repository. It brings ICML and ICLR papers with oral/spotlight decisions, and
title-only records for earlier years.

## Deduplication across sources

The same paper from several sources is merged into one record (see
[architecture.md](architecture.md#deduplication)). For every field the richer
value is kept: the longer text, the longer author list, the higher citation
count. A preprint merges into its venue version, and the venue record's venue
and year win.
