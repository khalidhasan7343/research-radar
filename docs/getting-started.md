# Getting started

This guide takes you from an empty folder to a ranked list of topics, a set of
idea seeds and a reading list for an idea of your own.

## 1. Install

You need Python 3.11 or newer.

```bash
git clone https://github.com/khalidhasan7343/research-radar.git
cd research-radar
python3 -m venv .venv && source .venv/bin/activate    # optional but recommended
pip install -e .
```

On Windows, activate the environment with `.venv\Scripts\activate`.

Optional extras:

| Extra | Command | What it adds |
| --- | --- | --- |
| `semantic` | `pip install -e ".[semantic]"` | `fastembed`: neural embeddings on CPU (`--backend fastembed`). Downloads a model the first time it runs. |
| `sbert` | `pip install -e ".[sbert]"` | `sentence-transformers`: any SentenceTransformer model (`--backend sentence-transformers`). Installs PyTorch. |
| `umap` | `pip install -e ".[umap]"` | `umap-learn`: UMAP layout for the map (`--layout umap`). |
| `dev` | `pip install -e ".[dev]"` | `pytest` and `httpx` for the test suite. |

Check the install:

```bash
radar --help
radar venues      # the 22 registered venues plus arXiv
```

All commands read and write relative to the folder you run them in: the
database and caches go in `./data/`, reports in `./reports/`, and settings are
read from `./radar.toml` if it exists. Run commands from the same folder each
time (or use `--data` and `--config`, see [cli.md](cli.md)).

## 2. Build a first corpus

Optional but recommended before you crawl: copy the settings file and put your
email in `contact_email`. OpenAlex asks API users to identify themselves this
way (see [data-sources.md](data-sources.md)).

```bash
cp radar.toml.example radar.toml
# edit radar.toml: contact_email = "you@example.org"
```

### From the open APIs (needs network)

Start small. `--limit` fetches at most that many papers per venue, year and
source, which is enough to see the whole pipeline work:

```bash
radar ingest venues --venues iclr --years 2024-2025 --sources openalex,openreview --limit 300
```

When that works, fetch the real thing. Full venue-years take much longer
because requests are rate-limited; every response is cached in `data/cache/`,
so an interrupted crawl resumes where it stopped.

```bash
radar ingest venues --venues neurips,icml,iclr --years 2022-2025 --sources openalex,openreview
radar ingest arxiv --start 2025-06-01 --categories cs.LG,cs.CL   # optional: recent preprints
```

Ingests made with `--limit` are not added to the tracked venues; full ingests
are (see [updating.md](updating.md)).

### From a file (no network)

Any CSV, JSON, JSONL or parquet file with a title column works. Recognised
column names (case-insensitive):

| Field | Column names looked for |
| --- | --- |
| title (required) | `title`, `paper_title`, `name` |
| abstract | `abstract`, `summary`, `abstracttext` |
| authors | `authors`, `author`, `author_list` (a list, or a string split on `;`, `and` or commas) |
| year | `year`, `publication_year` |
| venue | `venue`, `conference`, `journal`, `source` |
| citations | `citations`, `citationcount`, `cited_by_count`, `n_citations` |
| presentation | `presentation`, `decision`, `track`, `type` (text containing "oral", "spotlight" or "poster") |
| url | `url`, `link`, `pdf` |

```bash
radar ingest file my_papers.csv --venue neurips --year 2025
```

`--venue` and `--year` are used only for rows where the file has no venue or
year value.

### From RTanalysis (needs a local clone)

If you have a clone of [RTanalysis](https://github.com/Faysal-star/RTanalysis),
you can import the ICML/ICLR corpus committed there, or import it and run the
whole analysis in one step:

```bash
radar ingest rtanalysis ../RTanalysis
radar demo ../RTanalysis           # import + analyze + report
```

### Check what you have

```bash
radar status
```

prints papers per venue and year, how many have abstracts, citations and
oral/spotlight decisions, and a summary of the last analysis.

Trend metrics need at least two years per venue; acceleration needs three.
Abstracts matter: topics are defined from papers that have them.

## 3. Run the analysis

```bash
radar analyze
```

This runs six stages in order: embed, cluster, gaps, trends, terms, ideas. Each
stage prints what it did. The defaults run on a CPU without downloads. Useful
variations:

```bash
radar analyze --from trends          # re-run from one stage onward
radar analyze --clusters 60          # fix the number of topics
radar analyze --backend fastembed    # neural embeddings (semantic extra; network on first use)
```

Then write the report:

```bash
radar report       # reports/TREND_REPORT.md and reports/TREND_REPORT.html
```

The report states the corpus, validity checks, the highest-opportunity,
fastest-growing and cooling topics, what committees reward, emerging terms,
untried method x domain combinations, under-connected topics and idea seeds.

## 4. Open the dashboard

```bash
radar serve                      # http://127.0.0.1:8000
radar serve --port 8080          # another port
```

The dashboard reads the database once at start-up. If you re-run the analysis
while it is open, either restart `radar serve` or ask the server to reload and
then refresh the browser tab:

```bash
curl -X POST http://127.0.0.1:8000/api/reload
```

[dashboard.md](dashboard.md) describes every page.

## 5. A typical research-direction workflow

1. **Map the field.** On *Overview*, look at what is growing and cooling. On
   *Topics & scores*, sort by momentum, reward lift or opportunity, and move
   the weight sliders to match what you care about (for example, raise
   `low_entry_cost` if you have little compute). Open the *Landscape map* to see
   which topics sit next to each other.
2. **Look for gaps.** On a topic page, read the *Open problems* and *Position
   claims* tabs. On *Gaps & transplants*, look at the red cells of the method x
   domain heatmap and at under-connected neighbouring topics.
3. **Read the idea seeds.** *Ideas* lists seeds generated from the gaps, each
   with the measurement it came from and a novelty score. Treat them as
   prompts, not recommendations.
4. **Test your own idea.** In the *Idea lab*, describe an idea in one or two
   sentences. You get a novelty score, the topics it falls into and how they are
   trending, the closest existing papers and nearby open problems. If close
   papers already do it, reword the idea or drop it.
5. **Build a reading list.** Press *Reading list* in the Idea lab (or open the
   *Reading list* tab of a topic). Read the "closest to your idea" tier before
   committing to anything.

The same steps work from the terminal:

```bash
radar novelty "conformal prediction for LLM agents that call tools"
radar reading "conformal prediction for LLM agents that call tools"
radar reading --cluster 12
```

Topic numbers (`--cluster`) are shown in dashboard URLs (`#/topic/12`); they
change whenever clustering re-runs.

## Next

- Keep the corpus current: [updating.md](updating.md)
- Understand every number: [how-it-works.md](how-it-works.md)
- Tune settings and connect a free LLM: [configuration.md](configuration.md)
