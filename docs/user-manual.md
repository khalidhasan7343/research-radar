# User manual

A short, practical guide to using Research Radar. It covers the everyday tasks
in the order you will meet them. For full details, follow the links at the end
of each section.

## Contents

1. [What you get](#1-what-you-get)
2. [Install](#2-install)
3. [Build your corpus](#3-build-your-corpus)
4. [Check the corpus before you trust it](#4-check-the-corpus-before-you-trust-it)
5. [Analyse and open the dashboard](#5-analyse-and-open-the-dashboard)
6. [Find a research direction](#6-find-a-research-direction)
7. [Test your own idea](#7-test-your-own-idea)
8. [Keep it up to date](#8-keep-it-up-to-date)
9. [Reading the numbers](#9-reading-the-numbers)
10. [Troubleshooting](#10-troubleshooting)
11. [Command cheat sheet](#11-command-cheat-sheet)

---

## 1. What you get

You give Research Radar a set of conferences and years. It downloads the paper
metadata and tells you:

- **What the field is working on**: papers grouped into topics and themes, on a map.
- **What is growing or cooling**: each topic's share of papers over time.
- **Where the openings are**: limitations authors admit, method x domain
  combinations nobody has tried, neighbouring topics that rarely meet.
- **Whether your idea is new**: a novelty score, the closest existing papers,
  and a reading list.

Everything runs on your laptop CPU. No API keys are needed.

## 2. Install

Requires Python 3.11 or newer.

```bash
git clone https://github.com/khalidhasan7343/research-radar.git
cd research-radar
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
radar --help
```

Recommended: copy the settings file and add your email. OpenAlex gives faster,
more reliable access to clients that identify themselves.

```bash
cp radar.toml.example radar.toml
# then set: contact_email = "you@example.org"
```

> Run every `radar` command from the same folder. The database lives in
> `./data/`, reports go to `./reports/`.

## 3. Build your corpus

Pick venues (`radar venues` lists all 22) and years:

```bash
radar ingest venues --venues iclr,icml --years 2023-2025
```

The default sources are **Semantic Scholar** (`s2`, full proceedings with
abstracts) and **OpenAlex** (citations and extra metadata). A full venue-year
takes a few minutes. Responses are cached, so a crawl that is interrupted
resumes where it stopped.

Optional additions:

| Add | Command | Why |
| --- | --- | --- |
| arXiv preprints | `radar ingest arxiv --start 2026-06-01 --categories cs.LG,cs.CL` | An early signal of what is coming next |
| Your own list | `radar ingest file papers.csv --venue neurips --year 2025` | Only a `title` column is required |
| Oral/spotlight data | `radar ingest rtanalysis ../RTanalysis` | Enables the *reward lift* metric |

> `--limit N` is only for trying the tool out. A corpus built with it is
> too small to measure trends.

## 4. Check the corpus before you trust it

```bash
radar status
```

This shows papers per venue and year, how many have abstracts and citations,
and **coverage warnings** when something looks wrong, for example:

```text
Coverage warnings:
  ! iclr: tracked but has no papers. Run `radar ingest venues --venues iclr ...`.
  ! icml 2024: only 103 papers. Either a test fetch (--limit) or the proceedings are not indexed yet ...
  ! arXiv (7,313) outnumbers conference papers (290); topics will mostly reflect arXiv ...
```

Fix these before you rely on the numbers. A major ML conference has
thousands of papers per year. If yours shows a few hundred, the ingest was
partial. A conference from the last few months can be legitimately small
while the sources index it. Trend metrics leave such years out automatically.

## 5. Analyse and open the dashboard

```bash
radar analyze     # embed -> cluster -> gaps -> trends -> terms -> ideas
radar serve       # open http://127.0.0.1:8000
```

For better topics and idea checking, use semantic embeddings (a one-time
download of about 130 MB):

```bash
pip install -e ".[semantic]"
radar analyze --backend fastembed
```

`radar report` writes the same findings to `reports/TREND_REPORT.md` and
`.html`, ready to share.

### Dashboard pages at a glance

| Page | Use it to |
| --- | --- |
| Overview | Get the big picture: top opportunities, what is growing and what is cooling |
| Landscape map | See which topics are neighbours; zoom, filter, click papers |
| Topics & scores | Sort and filter topics; move the weight sliders to match your priorities |
| Topic page | Read a topic's papers, open problems, position claims and reading list |
| Emerging terms | See words and phrases rising or fading in titles |
| Gaps & transplants | Find untried method x domain pairs and topics that rarely meet |
| Ideas | Browse generated idea seeds, each with a novelty score |
| Idea lab | Check your own idea and build a reading list |
| Search | Find papers by text |

More: [dashboard.md](dashboard.md).

## 6. Find a research direction

1. **Overview**: note two or three topics that are growing and catch your eye.
2. **Topics & scores**: adjust the weights. With little compute, raise
   *low entry cost*. To publish at top venues, raise *reward lift*. Sort by
   *opportunity*.
3. **Topic page**: read the *Open problems* tab, the sentences where authors
   say what is still unsolved. This is the most useful tab.
4. **Gaps & transplants**: red cells are methods rarely applied to a domain
   where you would expect them. Check that the reason is not obvious.
5. **Ideas**: treat the seeds as prompts, not recommendations.

## 7. Test your own idea

In the dashboard **Idea lab**, or from the terminal:

```bash
radar novelty "test-time scaling for diffusion language models"
radar reading "test-time scaling for diffusion language models"
```

You get:

- **Novelty**: how far the idea is from everything in your corpus. High
  novelty can also mean your corpus does not cover the area.
- **Topics it lands in**, and whether they are growing.
- **Closest papers**: always read these before you commit.
- **A tiered reading list**: foundations, recent highlights, and the papers
  closest to your idea.

## 8. Keep it up to date

Every full ingest is remembered (tracked). To refresh everything:

```bash
radar update      # fetch new papers, re-analyse, write reports/CHANGES.md
radar changes     # show the last "what's new"
radar track       # show what is tracked
radar track --arxiv cs.LG,cs.CL    # also follow arXiv categories
```

To run it automatically twice a week, use the included GitHub Actions
workflow. See [updating.md](updating.md).

## 9. Reading the numbers

| Metric | Means | Good when |
| --- | --- | --- |
| Momentum | Topic share now vs earlier | > 1 (growing) |
| Reward lift | Oral/spotlight rate vs the venue average | > 1 |
| Impact | Citation percentile within venue and year | High |
| Openness | Share of abstracts that admit open problems | High: room to contribute |
| Entry cost | How compute-heavy the topic looks | Low, if you have little compute |
| Concentration | Share of papers from repeat authors | Low: easier to enter |
| arXiv lead | Topic share on arXiv vs at venues | > 1: more is coming |
| Opportunity | Weighted mix of the above | High |

A metric shown as "–" has no data, and it is left out of that topic's score.
These numbers rank and compare topics. They are not facts about the field:
read the papers behind a number before acting on it. Exact definitions are in
[how-it-works.md](how-it-works.md).

## 10. Troubleshooting

| Problem | Fix |
| --- | --- |
| `openreview refused access (HTTP 401/403, bot challenge)` | OpenReview blocks anonymous API clients. Use the default sources (`s2,openalex`). Reward lift then needs the RTanalysis import. |
| A venue-year has very few papers | It was ingested with `--limit`, or the proceedings are not indexed yet. Re-run `radar ingest venues` without `--limit`. |
| Semantic Scholar is slow or returns HTTP 429 | It is rate-limited without a key. Wait, or set `s2_api_key` in `radar.toml`. |
| Topic labels look like `decision · jev · typed` | Use `--backend fastembed`, or connect an LLM for readable names ([configuration.md](configuration.md)). |
| The dashboard shows old results | Restart `radar serve`, or run `curl -X POST http://127.0.0.1:8000/api/reload`. |
| Topic numbers changed | They are renumbered on every analysis. Refer to topics by label. |

More: [faq.md](faq.md).

## 11. Command cheat sheet

```bash
radar venues                                   # list supported venues
radar ingest venues --venues V --years Y       # download venue papers
radar ingest arxiv --start YYYY-MM-DD          # download arXiv preprints
radar ingest file papers.csv                   # import your own file
radar status                                   # corpus summary + coverage warnings
radar analyze                                  # run the analysis
radar analyze --from trends                    # re-run from one stage
radar serve                                    # web dashboard
radar report                                   # Markdown + HTML report
radar novelty "idea"                           # novelty check
radar reading "idea"                           # reading list
radar update                                   # refresh everything tracked
radar changes                                  # what changed last update
radar track                                    # show / change tracking
```

Every command and flag: [cli.md](cli.md).
