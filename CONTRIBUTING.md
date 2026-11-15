# Contributing

Thank you for helping improve Research Radar. Bug reports, documentation fixes,
new venues, new data sources and new metrics are all welcome.

By taking part you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Development setup

```bash
git clone https://github.com/khalidhasan7343/research-radar.git
cd research-radar
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Python 3.11 or newer is required.

## Running the tests

```bash
python -m pytest -q
```

The tests do not use the network. They check the API parsers against recorded
response shapes, the deduplication rules, a full pipeline run on a small
synthetic corpus, the dashboard API, the report, the HTTP cache and the update
diff. Please add a test for any change in behaviour.

To try the CLI without network access, import a file of made-up papers with
`radar ingest file` (see [docs/getting-started.md](docs/getting-started.md))
and use a separate data folder, for example `radar --data /tmp/radar-test ...`.

## Style

- Follow the style of the surrounding code: type hints on public functions,
  short docstrings that say *why*, and comments only where the reason is not
  obvious.
- Keep the default install CPU-only and free of API keys. Heavier
  dependencies go in an optional extra in `pyproject.toml`.
- Every metric must be documented with its exact definition in
  [docs/how-it-works.md](docs/how-it-works.md). If you change a definition,
  update the docs in the same pull request.
- The dashboard is plain JavaScript with no build step. Please keep it that way.
- Keep documentation plain and specific. Do not add numbers you have not
  measured.
- If you adapt code from another project, say where it came from in a comment
  and in [CREDITS.md](CREDITS.md), and make sure its license allows it.

## Data

- Never commit paper data: no databases, no `data/` folder, no exported corpora,
  no abstracts in tests or examples beyond a short sentence. Use synthetic text
  in tests.
- Never commit `radar.toml`, API keys or email addresses.
- New data sources must respect the source's terms of use and rate limits, and
  be documented in [docs/data-sources.md](docs/data-sources.md).

## Pull requests

1. Open an issue first for anything larger than a small fix, so we can agree on
   the approach.
2. Create a branch from the default branch and make focused commits with clear
   messages.
3. Run `python -m pytest -q` and make sure it passes.
4. Update the documentation and [CHANGELOG.md](CHANGELOG.md) (under
   "Unreleased") if behaviour changes.
5. Open the pull request and fill in the template.

## Reporting bugs and requesting features

Use the issue templates. For a bug, include the command you ran, the full
output or traceback, your Python version and operating system, and the output
of `radar status` if relevant. Do not paste your `radar.toml` with keys or your
email in it.

Security problems: see [SECURITY.md](SECURITY.md) instead of opening a public
issue.
