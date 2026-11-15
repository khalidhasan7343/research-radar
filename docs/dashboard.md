# Dashboard

Start it with `radar serve` and open <http://127.0.0.1:8000>. The dashboard is
a single page (vanilla JavaScript, no build step) served by FastAPI from
`radar/web/`. It reads the analysis from the database when the server starts.
If there is no analysis yet, every page shows the commands to create one.

<!-- TODO: add screenshots under docs/img/ (overview.png and one per page). -->

The left sidebar links to every page and shows the corpus size and whether an
LLM is connected. Clicking any paper title opens a side panel with its venue,
authors, topic, abstract, any open-problem sentences it contains, links to the
paper and arXiv, and *Find related*, which sends the title to the Idea lab.
Press Escape to close it.

## Overview

What the field looks like now.

- Corpus size, years and venues, and when the analysis last ran.
- Counts: topics and themes, "sweet spot" or "niche gem" topics, extracted open
  problems, idea seeds.
- **What's new**: the last update's new releases, grown venue-years, new topics,
  biggest movers and new terms (see [updating.md](updating.md)).
- **Highest opportunity**: top topics with their signal tag, momentum and score.
- **New & rising vocabulary**: click a term to see its curve on the Emerging
  terms page.
- **Fastest growing share** and **Cooling**: topics with at least 30 papers,
  by momentum.
- At the bottom, the validity checks (AMI and title agreement), when available.

What to do: get a first sense of direction, then open a topic that catches your
eye.

## Landscape map

Every paper with an abstract placed in 2-D by its embedding (the layout set by
`layout`; t-SNE by default). Points are shaded by the opportunity score of their
topic; orals and spotlights are drawn slightly larger.

- Scroll to zoom, drag to pan, hover for the title and topic, click to open the
  paper.
- Filters: theme, year, orals and spotlights only, topic labels on/off.

What to do: see which topics are neighbours, find dense and sparse regions, and
spot papers that sit between topics.

## Topics & scores

A sortable table of every topic: signal tag, papers in the latest year,
momentum, last-year growth, reward lift, impact, openness, entry cost,
repeat-author share, arXiv lead, opportunity, and a sparkline of its share over
the years. Columns with no data are hidden.

- **Opportunity weights**: one slider per score component (0 to 2 in steps of
  0.25). Moving a slider re-scores every topic on the server and re-sorts the
  table. Slider changes are not saved: reloading the page goes back to the
  weights from the last analysis. To change the defaults, edit `[weights]` in
  `radar.toml` and re-run `radar analyze --from trends`.
- Filter by text, theme or signal. Click a column header to sort, a row to open
  the topic.

What to do: set the weights to match your situation (for example, raise
`low_entry_cost` with little compute, or `reward` if you care about what
committees highlight), then shortlist a handful of topics.

## Topic page

Everything about one topic (`#/topic/<number>`).

- Summary (if an LLM labelled it), keywords, and tiles for opportunity, momentum,
  papers in the latest year, reward lift, openness, entry cost, projected
  papers next year and repeat-author share.
- **Share of papers per year**: chart of the topic's share at the panel venues.
- **Neighbouring topics** by centroid similarity, and the most active authors.
- Tabs:
  - *Papers*: central (most typical), highlighted (oral/spotlight), most cited,
    most recent;
  - *Open problems*: sentences from abstracts that admit a gap, with their kind;
  - *Position claims*: what position papers in this topic argue;
  - *Bridge papers*: papers almost equally close to this topic and another;
  - *Reading list*: the tiered list for this topic.

What to do: read the open problems and position claims; they are where
directions come from. Check the bridge papers for topics that are starting to
merge.

## Emerging terms

Words and phrases in titles whose frequency in the latest year rose or fell
compared with all earlier years, with their status (new, rising, fading), the
z-score and per-year counts.

- Type any term and press *Plot* to see how many titles per 1,000 papers
  contained it each year. Click a row to plot that term.

What to do: catch new vocabulary before it becomes a topic, and check whether a
term you care about is rising or fading.

## Gaps & transplants

- **Method x domain heatmap**: each cell compares the papers that combine a
  method and a domain with the number expected from how common each is. Red is
  rarer than expected, blue is more common, grey is as expected; the number is
  the observed count. Hover for details; click a cell to test that combination
  in the Idea lab.
- **Biggest untried combinations**: pairs observed at no more than 40% of the
  expected count, with the method's recent growth. Click a row to test it.
- **Under-connected neighbours**: topic pairs that are close in meaning but share
  fewer in-between papers than expected.
- **Admitted open problems**: search all extracted sentences and filter by kind.
- **What position papers argue**: every extracted position claim.

What to do: an empty cell is a question, not an answer. Some combinations are
empty for good reasons. Read a few papers on each side before deciding.

## Ideas

The idea seeds from the last analysis, filterable by kind (transplant, open
problem, bridge, low-cost entry). Each card shows the rationale (the
measurement it came from), a novelty bar and the closest existing paper.

- *Open in lab* sends the seed to the Idea lab.
- *Refine* (only with an LLM configured) asks the model for a research question,
  a falsifiable hypothesis, a "killing experiment", a first-week plan, the main
  risk, how to differ from the closest papers, and a verdict.

What to do: use the seeds as prompts. The novelty score only says how far the
seed is from papers in your corpus.

## Idea lab

Describe an idea in a sentence or two.

- *Check idea*: novelty score and verdict, similarity to the closest paper, the
  three topics the idea lands in with their signal, momentum and size, the
  closest existing papers, and up to 10 open-problem sentences from the two
  nearest topics, ranked by how similar their paper is to your text.
- *Reading list*: the tiered reading list for your idea.
- *Refine with LLM* (only with an LLM configured): the same refinement as on the
  Ideas page.

What to do: iterate on the wording, look at the closest papers, and read the
"closest to your idea" tier before committing.

## Search

Semantic search over every paper with an abstract (the 40 most similar to your
query). With the default TF-IDF backend this is closer to keyword search; see
[configuration.md](configuration.md#embedding-backends).
