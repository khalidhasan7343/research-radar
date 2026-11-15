# FAQ

## Limitations and caveats

**How much should I trust the numbers?**
They are measurements of *your* corpus under the definitions in
[how-it-works.md](how-it-works.md), not facts about the field. They are most
useful for ranking and comparing topics. Before acting on a number, open the
topic and read the papers and sentences behind it.

**The lexicons are heuristics.**
Entry cost, open problems, position claims, methods and domains are detected
with regular expressions over titles and abstracts. They miss paraphrases and
sometimes match the wrong sense of a word (for example "agent" or "graph"). An
empty method x domain cell can be empty for a good reason. Treat these as
pointers to read, not as counts to report.

**TF-IDF versus semantic embeddings.**
The default TF-IDF backend needs no download and is fast, but it compares
words, not meaning. Two papers describing the same idea in different words can
look unrelated, which affects topics, search, novelty and reading lists. For
checking ideas, install the `semantic` extra and set
`embed_backend = "fastembed"` (see
[configuration.md](configuration.md#embedding-backends)).

**Some metrics need data you may not have.**
- Reward lift needs oral/spotlight/poster decisions: OpenReview venues or the
  RTanalysis import.
- Impact needs citation counts for more than 30% of conference papers: OpenAlex
  or Semantic Scholar.
- The arXiv lead needs more than 200 arXiv papers.
- Acceleration needs three years; momentum needs two.
- Concentration needs at least 10 recent papers with author lists per topic.

Missing metrics show as "–" and drop out of the opportunity score for that
topic, so scores computed from different sets of metrics are not strictly
comparable.

**Novelty is relative to the corpus.**
A high novelty score means the idea is far from the papers you ingested. It can
also mean your corpus does not cover the area, or that the idea is worded
differently from the papers that already do it. Always read the "closest to
your idea" tier of the reading list, and search outside Research Radar too.

**Citations favour older papers.**
Impact uses a percentile within each venue and year to correct for this, but
very recent papers have few citations and noisy percentiles.

**Topic numbers change.**
Topics are renumbered every time clustering runs. Use labels, or the dashboard
links of the current run.

**The opportunity score is a judgement.**
It is a weighted mean of percentile ranks. The weights are not learned from
anything; they are defaults you are expected to change.

## Known issues

These are behaviours of the current code that you should know about:

- **Openness counts more papers in the numerator than the denominator.** The
  numerator counts papers with open-problem sentences from the whole corpus
  (including arXiv preprints and venue-years held back as incomplete), while the
  denominator counts only the topic's rich conference papers. In a corpus with
  many arXiv papers, openness is inflated for topics that are popular on arXiv.
- **`radar update --years-back N` with N > 1** re-reads years older than the
  previous year from the HTTP cache, so it only picks up pages that were never
  cached. To force a re-fetch of an older year, delete the corresponding cache
  files in `data/cache/` or re-ingest after clearing the cache.
- **AMI mixes taxonomies** when the corpus combines sources: the `topic` field
  holds OpenReview primary areas, OpenAlex topics or arXiv categories depending
  on where the paper came from.
- **The map's subtitle says "t-SNE"** even when `layout` is `umap` or `pca`.

## Common errors

**`The database is empty. Run 'radar ingest ...' first.`**
`radar analyze` found no papers. Check that you are in the folder where you
ingested (or pass the same `--data`), and run `radar status`.

**`Nothing is tracked yet. ...`**
`radar update` needs tracked venues or arXiv categories. Run a full
`radar ingest venues ...` (without `--limit`), or `radar track --venues ...`.

**`FileNotFoundError` for `data/embeddings/...` from `radar novelty` or `radar reading`.**
These commands need a completed analysis. Run `radar analyze` first.

**The dashboard says "No analysis yet."**
Same cause: run `radar analyze`, then restart `radar serve` (or
`curl -X POST http://127.0.0.1:8000/api/reload` and refresh the page).

**An ingest prints `skipped (... HTTP 403 ...)` for OpenReview.**
OpenReview sometimes challenges scripted requests. The other sources still
run. Try again later, or use OpenAlex and Semantic Scholar for that venue.

**An ingest is slow.**
Requests are deliberately rate-limited (see
[data-sources.md](data-sources.md)). Semantic Scholar without a key is the
slowest. Use `--limit` to test, and let long crawls run; interrupted crawls
resume from the cache.

**`openalex: no source found for <venue>`, or a venue has far too few papers.**
The OpenAlex name search did not find the right source. Check the `openalex`
string for that venue in `radar/ingest/venues.py`.

**`ModuleNotFoundError: No module named 'fastembed'` (or `sentence_transformers`).**
Install the extra: `pip install -e ".[semantic]"` or `pip install -e ".[sbert]"`.

**`unknown embed backend ...`**
`embed_backend` must be `tfidf`, `fastembed`, `sentence-transformers`, `sbert`
or `ollama`.

**The Refine buttons do not appear.**
Both `llm_base_url` and `llm_model` must be set when you start `radar serve`.
If they are set and refinement fails, the dashboard shows the error returned by
the endpoint (for example, the server is not running or the model name is
wrong).

**Topic labels did not change after configuring an LLM.**
Labels are generated during the cluster stage. Run
`radar analyze --from cluster`.

**`radar: command not found`.**
The package is not installed in the active environment. Activate your virtual
environment, or run `python -m radar ...` from the project folder after
`pip install -e .`.
