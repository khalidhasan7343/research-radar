# Configuration

Settings are defined in `radar/config.py` (the `Settings` dataclass). The
defaults run the whole pipeline on a laptop CPU with no API keys, so you only
need to configure what you want to change.

## Where settings come from

Later sources override earlier ones:

1. Defaults in `radar/config.py`.
2. `radar.toml` in the current folder, or the file given with
   `radar --config path/to/file.toml`.
3. Environment variables `RADAR_<SETTING>` (for example `RADAR_N_CLUSTERS=60`).
4. Command-line flags: `--data` sets `data_dir`; `radar analyze --backend`,
   `--clusters` and `--layout` set `embed_backend`, `n_clusters` and `layout`.

Start from the example file:

```bash
cp radar.toml.example radar.toml
```

`radar.toml` is in `.gitignore` because it can hold your email address and API
keys. Do not commit it.

## Settings

| Setting | Environment variable | Default | Meaning |
| --- | --- | --- | --- |
| `data_dir` | `RADAR_DATA_DIR` | `data` | Folder for the database (`radar.db`), embeddings and HTTP cache. Relative paths are relative to the current folder. |
| `embed_backend` | `RADAR_EMBED_BACKEND` | `tfidf` | `tfidf`, `fastembed`, `sentence-transformers` (or `sbert`), `ollama`. See below. |
| `embed_model` | `RADAR_EMBED_MODEL` | `""` | Model name for the backend; empty uses the backend's default. |
| `embed_dim` | `RADAR_EMBED_DIM` | `256` | Number of SVD dimensions for the `tfidf` backend. |
| `n_clusters` | `RADAR_N_CLUSTERS` | `0` | Number of topics; `0` chooses `clip(round(sqrt(n / 3)), 12, 150)`. |
| `n_themes` | `RADAR_N_THEMES` | `0` | Number of themes; `0` chooses `clip(round(topics / 8), 4, 8)`. |
| `layout` | `RADAR_LAYOUT` | `tsne` | 2-D map layout: `tsne`, `umap` (needs the `umap` extra) or `pca`. |
| `llm_base_url` | `RADAR_LLM_BASE_URL` | `""` | Base URL of an OpenAI-compatible API, e.g. `http://localhost:11434/v1`. |
| `llm_model` | `RADAR_LLM_MODEL` | `""` | Chat model name. LLM features are on only when both `llm_base_url` and `llm_model` are set. |
| `llm_api_key` | `RADAR_LLM_API_KEY` | `""` | Sent as a Bearer token. Not needed for Ollama or LM Studio. |
| `contact_email` | `RADAR_CONTACT_EMAIL` | `""` | If set, sent in the User-Agent header of every request to OpenAlex, Semantic Scholar, OpenReview and arXiv (`research-radar/1.0 (mailto:...)`). |
| `s2_api_key` | `RADAR_S2_API_KEY` | `""` | Semantic Scholar API key, sent as the `x-api-key` header. |
| `weights` | (none) | see below | Opportunity score weights. Only settable in `radar.toml`, under `[weights]`. |

`embed_dim` and `n_themes` are not in `radar.toml.example` but can be added to
`radar.toml` like any other setting.

### Weights

```toml
[weights]
momentum = 1.0
acceleration = 0.5
reward = 1.0
impact = 0.75
openness = 0.75
low_competition = 0.5
low_entry_cost = 0.75
low_concentration = 0.5
```

Keys you leave out keep their default. A weight of 0 removes that component.
The score is defined in [how-it-works.md](how-it-works.md#opportunity-score).
After changing weights, re-run `radar analyze --from trends` (the stored scores,
the report and the dashboard's default sliders use the weights from the last
trends run). On the dashboard you can also try weights live without saving
them.

## Embedding backends

| Backend | Install | Download | Notes |
| --- | --- | --- | --- |
| `tfidf` | included | none | Fitted on your corpus. Fast on a CPU. Matches words rather than meaning, so paraphrased prior work can be missed. |
| `fastembed` | `pip install -e ".[semantic]"` | model on first use | ONNX models on CPU. Default model `BAAI/bge-small-en-v1.5`; set `embed_model` for another fastembed model. |
| `sentence-transformers` | `pip install -e ".[sbert]"` | model on first use | Any SentenceTransformer model, run on CPU. Default `all-MiniLM-L6-v2`. Installs PyTorch. |
| `ollama` | an [Ollama](https://ollama.com) server | `ollama pull <model>` | Calls `<base>/api/embed`. Default model `nomic-embed-text`. The base URL is `llm_base_url` with `/v1` removed, or `http://localhost:11434`. |

Neural backends are slower to embed than TF-IDF but better at finding papers
that describe the same idea in different words, which matters most for the
Idea lab, `radar novelty` and search.

To switch backend for good, set it in `radar.toml` and re-embed:

```toml
embed_backend = "fastembed"
```

```bash
radar analyze      # re-embeds because the backend changed
```

For example, with Ollama:

```bash
ollama pull nomic-embed-text
RADAR_EMBED_BACKEND=ollama radar analyze
```

## Free LLM setup (optional)

Every feature works without an LLM. With one:

- topics get readable names and a two-sentence summary (during the cluster
  stage);
- the dashboard shows *Refine* buttons on the Ideas page and in the Idea lab,
  which turn an idea into a research question, a falsifiable hypothesis, a
  "killing experiment", a first-week plan, the main risk, how to differ from the
  closest papers and a verdict.

Any OpenAI-compatible chat endpoint (`<base>/chat/completions`) works. The
model's answer must contain a JSON object; `<think>` blocks from reasoning
models are removed first.

### Ollama

```bash
# install Ollama from https://ollama.com, then:
ollama pull qwen2.5:7b
export RADAR_LLM_BASE_URL=http://localhost:11434/v1
export RADAR_LLM_MODEL=qwen2.5:7b
radar analyze --from cluster      # relabels topics, then re-runs later stages
radar serve                       # "Refine" buttons appear
```

Or in `radar.toml`:

```toml
llm_base_url = "http://localhost:11434/v1"
llm_model = "qwen2.5:7b"
```

### LM Studio

Load a model in [LM Studio](https://lmstudio.ai) and start its local server,
then:

```bash
export RADAR_LLM_BASE_URL=http://localhost:1234/v1
export RADAR_LLM_MODEL=<the model name shown in LM Studio>
```

### Hosted endpoints

Hosted OpenAI-compatible services work the same way; set `llm_api_key` (or
`RADAR_LLM_API_KEY`) as well. Check the provider's pricing and terms, and note
that your idea text, topic keywords, paper titles and open-problem sentences
from your corpus are sent to it.

If a request fails, topic labelling keeps the keyword labels and the dashboard
shows the error instead of a refinement.
