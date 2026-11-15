# Staying up to date

Proceedings appear in OpenAlex and OpenReview over several weeks, and arXiv grows
every day. Research Radar remembers what you follow and can refresh it with one
command, locally or on GitHub Actions.

## Tracking

Every `radar ingest venues` run without `--limit` adds its venues and sources
to the tracked set. Every `radar ingest arxiv` run adds its categories. The
tracked set is stored in the database (`meta` table, key `tracking`).

```bash
radar track                                    # show what is tracked
radar track --venues cvpr,acl --sources openalex --from-year 2024
radar track --arxiv cs.LG,cs.CL                # follow arXiv categories
radar track --remove acl                       # stop tracking a venue
```

Venues, sources and arXiv categories are added to what is already tracked. Only
venues can be removed from the CLI.

## radar update (network)

```bash
radar update
```

1. For every tracked venue, fetches the current year and the previous year
   (`--years-back N` re-checks N earlier years) from the tracked sources
   (OpenAlex if none are tracked). Cached responses for the current and
   previous year are re-fetched once they are older than 5 days; older years are
   served from the cache. This means `--years-back` values above 1 only fetch
   pages that were never cached (see [faq.md](faq.md#known-issues)).
2. For tracked arXiv categories, fetches from two days before the last date
   fetched until today (or the last 30 days the first time).
3. If no new papers arrived and an analysis already exists, stops there (unless
   `--force`) and records a "no change" entry.
4. Otherwise re-runs the full analysis, compares it with the previous one,
   and writes `reports/CHANGES.md`, `reports/changes.json`,
   `reports/TREND_REPORT.md` and `reports/TREND_REPORT.html` (`--out` changes
   the folder).

If nothing is tracked, it stops with:

```text
Nothing is tracked yet. Ingest something first (it is tracked automatically), or run
  radar track --venues neurips,icml,iclr --sources openalex,openreview --from-year 2023
```

`radar changes` prints the last summary again. The dashboard shows it on the
Overview page.

## What the "what's new" report contains

Computed by `diff` in `radar/update.py`, comparing the database before and after:

| Section | Meaning |
| --- | --- |
| New papers | total papers now minus total before |
| New releases | venue-years that had no papers before (for example a new NeurIPS year) |
| Updated | venue-years whose paper count grew |
| New topics | topics where fewer than 30% of the papers existed before, or whose old papers came mostly from different old topics (the largest share from a single old topic is under 40%) |
| Biggest movers | other topics, matched to the old topic they share most papers with, where \|change in opportunity\| + 10 x \|change in momentum\| is at least 3, or whose signal tag changed; at most 15, largest change first |
| New terms | up to 20 new or rising terms that were not on the previous list |

Topic numbers change every time clustering re-runs, so old and new topics are
matched by the papers they share, not by number.

The first analysis has nothing to compare with and says so.

**Partial years.** A venue-year that is still being indexed (fewer than half the
previous year's papers at that venue) is left out of trend metrics until it
fills in, so that a half-published conference does not make all its topics look
like they collapsed. The trend report lists venue-years held back this way.

## GitHub Actions

`.github/workflows/update.yml` runs `radar update` on GitHub's servers every
Monday and Thursday at 03:17 UTC, commits the refreshed reports, and opens an
issue with the "what's new" summary whenever new papers arrived. GitHub notifies
you about new issues according to your notification settings.

### What is stored where

- **Committed to the repository**: only `reports/CHANGES.md`,
  `reports/TREND_REPORT.md`, `reports/TREND_REPORT.html` and
  `reports/changes.json`. The reports contain topic labels, terms, counts and,
  in the idea-seed rationales, single quoted sentences from abstracts.
- **Not committed**: the `data/` folder (database, embeddings and HTTP cache).
  The database contains paper abstracts owned by their authors and publishers,
  so it must not be published in a public repository. It is kept between runs
  in the repository's
  [Actions cache](https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/caching-dependencies-to-speed-up-workflows),
  which only workflows of the repository can read.
- **Workflow artifact**: each run also uploads `reports/` as an artifact named
  `trend-report`.

GitHub removes caches that have not been used for 7 days, and the total cache
size per repository is limited. Running twice a week keeps the cache in use.
If the cache is lost anyway (for example because the workflow was disabled),
the next run finds no database and rebuilds it from the repository variables
below. Without those variables it fails with "Nothing is tracked yet", and you
need to start it again by hand.

### Setup

1. Push the repository to GitHub and make sure Actions are enabled
   (*Settings > Actions > General*). The workflow needs permission to push
   commits and open issues; it requests `contents: write` and `issues: write`.
   If your repository or organisation restricts the default `GITHUB_TOKEN`,
   allow read and write permissions there.
2. Under *Settings > Secrets and variables > Actions*:

   | Kind | Name | Needed | Purpose |
   |---|---|---|---|
   | Variable | `RADAR_VENUES` | recommended | Venues to rebuild from if the cache is lost, e.g. `neurips,icml,iclr` |
   | Variable | `RADAR_YEARS` | recommended | Years to rebuild, e.g. `2023-2025` |
   | Variable | `RADAR_SOURCES` | optional | Sources for the rebuild; default `openalex,openreview` |
   | Variable | `RADAR_ARXIV` | optional | arXiv categories to follow after a rebuild, e.g. `cs.LG,cs.CL` |
   | Variable | `RADAR_CONTACT_EMAIL` | optional | Your contact email for the OpenAlex polite pool (see [data-sources.md](data-sources.md)) |
   | Variable | `RADAR_EMBED_BACKEND` | optional | Embedding backend; default `tfidf` |
   | Secret | `RADAR_S2_API_KEY` | optional | Semantic Scholar API key |

3. Start the first run: *Actions > Research Radar update > Run workflow*, and
   fill in the venues and years to start from (for example
   `neurips,icml,iclr,cvpr,acl` and `2023-2025`), the sources, and optionally
   arXiv categories. If you set `RADAR_VENUES` and `RADAR_YEARS`, you can leave
   the inputs empty: with no cached database, the run backfills from the
   variables.

After that it runs on schedule by itself. The *force* input re-runs the analysis
even if nothing new arrived.

To change the schedule, edit the `cron` line in the workflow. Keep at least one
run every 7 days, or the cached database will expire.

### Looking at the results

The reports are in the repository (`reports/TREND_REPORT.md` renders on
GitHub). The dashboard needs the database, which stays in the Actions cache and
is not downloadable. To use the dashboard, build the same corpus locally with
`radar ingest venues ...` and `radar analyze`, or run `radar update` on your
own computer as below.

## On your own computer

### Linux and macOS (cron)

Run `crontab -e` and add a line such as (every Monday at 09:00):

```text
0 9 * * 1 cd /path/to/research-radar && /path/to/research-radar/.venv/bin/radar update >> reports/update.log 2>&1
```

Use the full path to `radar` inside your virtual environment, because cron does
not load your shell's `PATH`. The `cd` matters: `radar` uses `./data`,
`./reports` and `./radar.toml`.

### Windows (Task Scheduler)

1. Open *Task Scheduler* and choose *Create Basic Task*.
2. Name it "Research Radar update" and choose *Weekly*.
3. Action: *Start a program*.
   - Program/script: the full path to `radar.exe` in your environment, for
     example `C:\path\to\research-radar\.venv\Scripts\radar.exe`.
   - Add arguments: `update`
   - Start in: your project folder, for example `C:\path\to\research-radar`.
4. Finish, and run the task once by hand to check it works.
