# How it works

This page describes what `radar analyze` computes, as implemented in `radar/`.
File references point to the code that does it.

The pipeline has six stages. Each reads from and writes to the SQLite database
(`data/radar.db`), so any stage can be re-run on its own with
`radar analyze --from <stage>` or `--only <stages>`.

```text
embed -> cluster -> gaps -> trends -> terms -> ideas
```

Two terms used throughout:

- **Conference papers**: every paper whose venue is not `arxiv`.
- **Rich papers**: papers with an abstract of at least 200 characters.

## 1. Embed (`radar/embed.py`)

Each paper gets two vectors:

- **full**: `"<title>. <abstract>"`, or just the title when there is no abstract;
- **title**: the title alone.

LaTeX between `$...$` is removed and whitespace collapsed first. All vectors are
L2-normalised, so a dot product is a cosine similarity.

| Backend | What it does | Default model |
| --- | --- | --- |
| `tfidf` (default) | TF-IDF of 1-2 word n-grams (`min_df=3`, `max_df=0.4`, sublinear TF, English + domain stop words, at most 120,000 features), reduced with truncated SVD to `embed_dim` dimensions (default 256) | none (fitted on your corpus) |
| `fastembed` | ONNX sentence embeddings on CPU | `BAAI/bge-small-en-v1.5` |
| `sentence-transformers` (alias `sbert`) | any SentenceTransformer model, on CPU | `all-MiniLM-L6-v2` |
| `ollama` | a local Ollama embedding model via `/api/embed` | `nomic-embed-text` |

The TF-IDF backend is fitted only on rich papers, unless fewer than
max(500, 15% of the corpus) papers are rich, in which case it is fitted on all
papers. Embeddings are cached in `data/embeddings/` and rebuilt only when the
backend, model, dimension, the set of papers or their text lengths change (or
with `--force-embed`).

## 2. Cluster (`radar/cluster.py`)

**Topics.** k-means (`n_init=4`, fixed seed) on the full vectors of rich
conference papers. If there are 500 or fewer conference papers, arXiv papers
are used too. The number of topics is `n_clusters` if set, otherwise
`clip(round(sqrt(n / 3)), 12, 150)` where `n` is the number of papers clustered.
Topic centroids are the normalised mean of their members.

**Placing papers.** Every rich paper, including arXiv preprints, is assigned to
the most similar topic centroid. Each paper records:

- `cluster`: best topic; `cluster2`: runner-up topic;
- `confidence`: cosine similarity to the best centroid;
- `margin`: similarity to the best minus similarity to the runner-up;
- `space`: `full`.

**Title-only papers.** Papers that are not rich are placed in title space: a
title centroid is built for each topic from the title vectors of its rich
members, and the paper goes to the most similar title centroid (`space` =
`title`). No paper is left unassigned.

**Trend assignment.** When the corpus has title-only papers, a second
assignment `cluster_trend` places *every* paper (rich or not) by its title
against the title centroids. Trend counts use `cluster_trend`. Otherwise
`cluster_trend` equals `cluster`. See [Title-only papers](#title-only-papers-and-trend-counts)
below for why.

**Themes.** Topic centroids are grouped with agglomerative clustering (Ward
linkage). The number of themes is `n_themes` if set, otherwise
`clip(round(k / 8), 4, 8)`, never more than the number of topics.

**Labels.** c-TF-IDF keyphrases: all texts of a topic are joined into one
document; 1-3 word n-grams that occur at least 5 times in total are kept; each
term's frequency within the topic is weighted by `log(1 + A / f)`, where `A` is
the average number of words per topic and `f` the term's total frequency. The
top 12 terms (minus near-duplicates such as plural forms and sub-phrases) are
the topic's keywords. The label joins up to three of them with ` · `,
preferring multi-word phrases. Themes get two-keyword labels the same way. If
an LLM is configured, each topic is then renamed and given a two-sentence
summary (`radar/llm.py`); on any LLM error the keyword labels are kept.

**Map.** The 2-D map shows rich papers (a random sample of 20,000 if there are
more), laid out with t-SNE on 50 PCA components (default), UMAP (needs
`umap-learn`) or plain PCA, set by `layout`.

**Representative papers.** The five rich members with the highest confidence.

## 3. Gaps (`radar/gaps.py`)

All gap extraction uses every paper in the corpus, including arXiv preprints.

**Open problems.** Each abstract is split into sentences (longer than 20
characters). A sentence is tagged with the first of these kinds whose pattern
matches, and stored with its paper and topic (truncated to 600 characters):

| Kind | Example phrases |
| --- | --- |
| `open_question` | "remains open / unclear / unknown", "open problem", "little is known", "poorly understood", "under-explored" |
| `limitation` | "fails to", "struggles to", "suffers from", "bottleneck", "does not generalize / scale", "limited to" |
| `missing_eval` | "no existing benchmark", "lack of standardized evaluation", "evaluation remains challenging" |
| `future_work` | "future work", "future research directions", "we call for", "research agenda" |

**Position claims.** For papers with `paper_type = position` or a title starting
with "Position:", every abstract sentence containing "we argue", "we contend",
"we advocate", "we call", "should", "must", "need(s) to" or "it is time".

**Transplants (method x domain).** Text is title + abstract of papers with an
abstract longer than 200 characters (or of all papers, if there are 500 or fewer
such papers). A paper "uses" a method or domain if the text matches the
method's or domain's regular expression (32 methods, 30 domains, defined in
`METHODS` and `DOMAINS`). For each pair:

- `observed` = papers matching both;
- `expected` = (papers matching the method) x (papers matching the domain) / N;
- `gap_z` = (expected - observed) / sqrt(expected);
- `ratio` = (observed + 0.5) / (expected + 0.5);
- `method_growth` = (share of conference-paper titles matching the method in the
  latest year + 0.002) / (share in all earlier years + 0.002).

Only pairs with `expected >= 2` are kept, sorted by `gap_z`.

**Under-connected topics (bridges).** Bridge papers are papers placed in full
space with `margin < 0.03` and a runner-up topic. For every pair of topics whose
centroid similarity is in the top 15% of all pairs:

- `n_bridge` = bridge papers between the two topics;
- `expected` = rate x sqrt(size_a x size_b) x similarity, with
  rate = (total bridge papers over these pairs + 1) / sum of sqrt(size_a x size_b) x similarity;
- `underconnected` = (expected - n_bridge) / sqrt(expected + 1).

The 60 most under-connected pairs are kept, plus up to 3,000 bridge papers.

## 4. Trends (`radar/trends.py`)

### Which papers are counted

1. Only conference papers enter trend metrics. arXiv papers are used only for
   the arXiv lead.
2. **Partial-year guard.** A venue-year with fewer than half as many papers as
   the same venue's previous year is treated as still being indexed and is left
   out of all trend metrics. The trend report and `radar status`
   (`trend_info.incomplete_venue_years`) list the venue-years held back.
3. `first` and `last` are the earliest and latest remaining years.
4. **Balanced panel.** Share calculations use only venues present in both
   `first` and `last` (if no venue is, all venues are used). The report lists
   the panel venues.

Let `n(c, y)` be the number of panel papers in topic `c` (by `cluster_trend`) in
year `y`, and `N(y)` the number of panel papers in year `y`. The smoothed share is

```text
share(c, y) = (n(c, y) + 0.5) / N(y)
```

### Metrics per topic

| Column | Definition |
| --- | --- |
| `n_total` | conference papers in the topic (by `cluster_trend`), all venues and years |
| `competition` | `n(c, last)`: panel papers in the latest year |
| `momentum` | `share(c, last) / share(c, first)`; 1.0 if there is only one year |
| `recent_growth` | `share(c, last) / share(c, previous year)` |
| `acceleration` | `ln(share(last) / share(prev)) - ln(share(prev) / share(prev2))`; needs 3 years |
| `forecast_share` | least-squares line through `ln(share)` against year, extrapolated one year past `last`, capped at 3 x `share(last)`, in percent |
| `forecast_n` | `forecast_share` x `N(last)`, rounded |
| `share_last` | `n(c, last) / N(last)` in percent (unsmoothed) |
| `highlight_rate` | percent of the topic's papers with a known tier that are oral or spotlight |
| `reward_lift` | `(observed + 1) / (expected + 1)`, see below |
| `impact` | mean within-venue-year citation percentile x 100, see below |
| `median_citations` | median citation count of the topic's papers that have one |
| `openness` | share of the topic's rich conference papers with an open-problem sentence, see below |
| `n_open_problems` | open-problem sentences of kind `open_question`, `limitation` or `missing_eval` in the topic |
| `entry_cost` | mean over rich conference papers of `[EXPENSIVE matches] - [CHEAP matches]` (each 0 or 1) |
| `entry_cost_label` | `cheap` / `moderate` / `expensive` by tertile of `entry_cost` across topics |
| `concentration` | share of recent papers with at least one author who has 3 or more recent papers in the topic |
| `median_team` | median number of authors of recent papers |
| `arxiv_lead` | `(arXiv share + 0.0001) / (venue share + 0.0001)`, see below |
| `arxiv_recent` | arXiv papers in the topic in the last 365 days of arXiv data |
| `mean_year` | mean publication year of the topic's conference papers |
| `opportunity` | weighted score, see below |
| `tag` | signal label, see below |

Momentum, recent growth, acceleration, forecast, competition and `n_total`
count papers by `cluster_trend` (title placement). Reward lift, impact,
openness, entry cost, concentration and the arXiv share use `cluster`
(abstract placement where available), because they depend on abstracts,
decisions or authors.

**Reward lift.** Uses conference papers whose presentation is known (`oral`,
`spotlight` or `poster`). For each venue-year, `rate` = the fraction of those
papers that are oral or spotlight; venue-years with a rate of 0 are skipped.
For a topic, `observed` = its oral and spotlight papers and `expected` = the sum
of `rate` over its papers. Lift > 1 means committees highlighted the topic more
than its venue mix predicts. Empty if no venue-year reports tiers.

**Impact.** Computed only if more than 30% of conference papers have a citation
count. Each paper's citations are converted to a percentile rank within its
venue and year (so older papers are not favoured), and the topic's mean
percentile is multiplied by 100.

**Openness.** Numerator: distinct papers in the topic with at least one
open-problem sentence of kind `open_question`, `limitation` or `missing_eval`
(`future_work` is not counted). Denominator: the topic's rich conference papers.
Note that the numerator is taken from all extracted sentences, which include
arXiv papers and papers from held-back venue-years, while the denominator does
not; see [faq.md](faq.md#known-issues).

**Entry cost.** `EXPENSIVE` matches phrases such as "pre-training", "from
scratch", "billion-parameter", "GPU hours", "RLHF", "trillion tokens"; `CHEAP`
matches phrases such as "training-free", "we prove", "theorem", "zero-shot",
"closed-form", "regret bound". Both are matched against the abstract.

**Concentration.** "Recent" means conference papers from the last two years.
Computed only if the topic has at least 10 recent papers with author lists.

**arXiv lead.** Computed only if the corpus has more than 200 arXiv papers. The
arXiv share is the topic's fraction of arXiv papers dated within 365 days of
the newest arXiv paper; the venue share is `n(c, last) / N(last)`. A value
above 1 means the topic is more common on arXiv now than at the venues in the
latest year.

### Opportunity score

For each component, every topic gets a percentile rank among topics where the
metric is known (`rank(pct=True)` in pandas). For "lower is better"
components, the percentile is `1 - p + 1/n`, where `n` is the number of topics
with a value.

| Weight name | Column | Direction | Default weight |
| --- | --- | --- | --- |
| `momentum` | `momentum` | higher is better | 1.0 |
| `acceleration` | `acceleration` | higher is better | 0.5 |
| `reward` | `reward_lift` | higher is better | 1.0 |
| `impact` | `impact` | higher is better | 0.75 |
| `openness` | `openness` | higher is better | 0.75 |
| `low_competition` | `competition` | lower is better | 0.5 |
| `low_entry_cost` | `entry_cost` | lower is better | 0.75 |
| `low_concentration` | `concentration` | lower is better | 0.5 |

```text
opportunity = 100 x sum(w_i x p_i) / sum(w_i)
```

summed over the components that are known for that topic, so a metric with no
data drops out instead of counting as zero. The score is relative to the other
topics in the same corpus. Weights are set in `radar.toml` and can be changed
live on the dashboard's Topics page.

### Tags

Evaluated in this order (first match wins), with `rising` = momentum >= 1.25,
`falling` = momentum <= 0.8, `crowded` = the topic's `low_competition`
percentile is below 0.3 (roughly the 30% of topics with the most papers in the
latest year), `rewarded` = reward lift >= 1.15:

1. falling: `cooling`
2. rising, rewarded and not crowded: `sweet spot`
3. rising and crowded: `hot & crowded`
4. rising: `rising`
5. rewarded and not crowded: `niche gem`
6. crowded: `mainstream`
7. otherwise: `steady`

## 5. Terms (`radar/terms.py`)

Emerging and fading words and phrases are counted in **titles** of conference
papers (all papers, if there are 500 or fewer conference papers). Titles exist
for every year; abstracts may not.

- Vocabulary: 1-3 word n-grams, counted once per title, appearing in at least 8
  titles, stop words removed.
- `y1` = count in the latest year; `y0` = count in all earlier years.
- Prior: `a = 0.1 x (y1 + y0) + 0.01` per term; `a0` = sum of `a`.
- Log-odds: `l1 = ln((y1 + a) / (n1 + a0 - y1 - a))`, `l0` the same for the
  earlier years, where `n1`, `n0` are total counts.
- `z = (l1 - l0) / sqrt(1 / (y1 + a) + 1 / (y0 + a))`.

This is the log-odds ratio with an informative Dirichlet prior (Monroe,
Colaresi & Quinn 2008), which does not over-reward rare words the way a raw
ratio does. The top 150 terms by `z` and the bottom 75 are kept. Status:
`new` if `z > 0`, the term appeared in at most 2 earlier titles and in at least
8 latest-year titles; `rising` for other positive `z`; `fading` otherwise. A
term is dropped if a longer phrase containing it has the same status and at
least 90% of its |z|.

The term lookup on the dashboard counts titles containing the typed text, per
year, per 1,000 papers.

## 6. Ideas (`radar/ideas.py`)

Seeds come from four rules. Each records the measurement it came from.

| Kind | Rule | `evidence_score` |
| --- | --- | --- |
| `transplant` | method x domain pairs with `observed <= 0.35 x expected`; top 15 by score | `gap_z x clip(method_growth, 0.5, 3)` |
| `open problem` | for each of the 12 highest-opportunity topics with `open_question` or `missing_eval` sentences, the most recent such sentence | `opportunity / 20` |
| `bridge` | from the 25 most under-connected topic pairs, skipping pairs where both topics have momentum below 1; at most 12 | `underconnected` |
| `low-cost entry` | topics with momentum >= 1.3 and entry cost `cheap`; top 8 by opportunity | `opportunity / 20` |

Scores are on different scales, so kinds are interleaved round-robin (best of
each kind, then second best of each kind, and so on) and the first 40 are kept.
Each seed is then scored for novelty using its title plus the first sentence of
its rationale.

## Novelty scoring

Used by the Idea lab, `radar novelty` and the idea seeds (`Index.novelty` in
`radar/ideas.py`).

1. The searchable set is papers with an abstract longer than 100 characters (all
   papers, if fewer than 100 qualify).
2. The idea text is embedded with the same backend as the corpus. `best` = its
   highest cosine similarity to any searchable paper.
3. A reference distribution: 400 searchable papers are sampled (fixed seed) and,
   for each, the similarity to its nearest *other* searchable paper is computed.
4. `novelty = 100 x (fraction of reference papers whose nearest-neighbour
   similarity is greater than best)`.

So 0 means the idea is closer to an existing paper than any sampled paper is to
its own nearest neighbour; 100 means it is further from everything than all of
them. Verdicts: below 25 "crowded", below 55 "incremental", below 85
"distinct", otherwise "far from the corpus: check it is in scope, or reword
it". The three most similar topic centroids are reported as the topics the idea
lands in.

Novelty is relative to the corpus. A high score can mean the idea is new, or
that the corpus does not cover its area, or that it is worded very differently
from papers that do it (more likely with the TF-IDF backend).

## Reading lists

`reading_list` in `radar/ideas.py` builds tiers from a pool of searchable papers
in the idea's topics (up to three distinct topics among its 20 nearest papers)
or in one topic (`--cluster`).

- relevance: similarity to the idea, or to the topic centroid;
- prominence: within-year citation percentile if more than 30% of the pool has
  citations, otherwise 1.0 for orals, 0.7 for spotlights, 0 otherwise;
- score = 0.55 x relevance percentile + 0.45 x prominence.

| Tier | Contents (up to 12 each, 24 for T2) |
| --- | --- |
| T0 foundational | prominent conference papers, by score |
| T1 recent work at the frontier | conference papers from the last two years, by score |
| T2 closest to your idea | the nearest papers to the idea (only for an idea, not a topic) |
| T3 latest preprints | arXiv papers in the pool, newest first |

No paper appears in two tiers.

## Title-only papers and trend counts

Older venue-years often have titles but no abstracts (for example, papers
imported from title lists). Two problems follow:

- A title-only paper cannot be placed with the same vector as a paper that has
  an abstract. So it is placed by comparing its title with title centroids built
  from papers that have both.
- Title placement and abstract placement do not always agree. If recent years
  (with abstracts) were placed by abstract and older years (without) by title,
  a topic whose abstracts are more distinctive than its titles would look like
  it is growing purely because of the change in method.

So all trend counts use title placement (`cluster_trend`) for **every** year,
and the comparison is like-for-like. The agreement between title and abstract
placement, for papers that have both, is reported as a validity check (see
below). This two-space approach comes from
[RTanalysis](https://github.com/Faysal-star/RTanalysis).

## Validity checks

These are stored in the database, shown by `radar status`, printed in the
trend report and shown at the bottom of the dashboard Overview page:

- **AMI against an official taxonomy** (`cluster_info.ami_vs_official_topics`):
  adjusted mutual information between topics and the `topic` field, when at
  least 200 papers have one. The `topic` field holds OpenReview's
  `primary_area`, OpenAlex's primary topic, RTanalysis's primary topic, or the
  arXiv category list, depending on the source, so in a mixed corpus the AMI
  compares against a mix of taxonomies. Moderate agreement is expected: topics
  should refine the taxonomy, not copy it.
- **Title agreement** (`cluster_info.title_agreement`): share of rich papers
  whose title placement matches their abstract placement. Only computed when
  there are title-only papers.
- **Panel venues** (`trend_info.panel_venues`) and **held-back venue-years**
  (`trend_info.incomplete_venue_years`).
- `cluster_info.title_only_assigned`: number of papers placed by title.
