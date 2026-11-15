"""Settings for Research Radar.

Everything can be overridden with environment variables (prefix RADAR_) or a
`radar.toml` file in the working directory. Defaults are chosen so the whole
pipeline runs on a laptop CPU with no API keys.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

SEED = 20261115


@dataclass
class Settings:
    data_dir: Path = Path("data")
    # Embedding backend: "tfidf" (default, no download), "fastembed",
    # "sentence-transformers", or "ollama".
    embed_backend: str = "tfidf"
    embed_model: str = ""  # backend-specific; empty = backend default
    embed_dim: int = 256  # used by the tfidf backend (SVD components)

    # Clustering
    n_clusters: int = 0  # 0 = choose automatically from corpus size
    n_themes: int = 0  # 0 = choose automatically
    layout: str = "tsne"  # "tsne", "umap" (if installed) or "pca"

    # Optional LLM (any OpenAI-compatible endpoint: Ollama, LM Studio, Groq, OpenRouter...)
    llm_base_url: str = ""  # e.g. http://localhost:11434/v1 for Ollama
    llm_model: str = ""  # e.g. llama3.1:8b, qwen2.5:7b
    llm_api_key: str = ""  # not needed for Ollama / LM Studio

    # Polite crawling
    contact_email: str = ""  # sent to OpenAlex / arXiv as recommended ("polite pool")
    s2_api_key: str = ""  # optional Semantic Scholar key (higher rate limit)

    # Opportunity score weights (see trends.py). Visible and arguable on purpose.
    weights: dict = field(
        default_factory=lambda: {
            "momentum": 1.0,
            "acceleration": 0.5,
            "reward": 1.0,
            "impact": 0.75,
            "openness": 0.75,  # density of admitted open problems
            "low_competition": 0.5,
            "low_entry_cost": 0.75,
            "low_concentration": 0.5,
        }
    )

    @property
    def db_path(self) -> Path:
        return self.data_dir / "radar.db"

    @property
    def emb_dir(self) -> Path:
        return self.data_dir / "embeddings"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_base_url and self.llm_model)

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.emb_dir, self.cache_dir):
            p.mkdir(parents=True, exist_ok=True)


def _coerce(value: str, current):
    if isinstance(current, bool):
        return value.lower() in {"1", "true", "yes", "on"}
    if isinstance(current, int):
        return int(value)
    if isinstance(current, Path):
        return Path(value)
    return value


def load_settings(path: str | Path | None = None, **overrides) -> Settings:
    s = Settings()
    toml_path = Path(path) if path else Path("radar.toml")
    if toml_path.exists():
        cfg = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        for f in fields(s):
            if f.name in cfg:
                cur = getattr(s, f.name)
                val = cfg[f.name]
                if f.name == "weights":
                    cur.update(val)
                    continue
                setattr(s, f.name, _coerce(str(val), cur) if not isinstance(val, type(cur)) else val)
    for f in fields(s):
        env = os.environ.get("RADAR_" + f.name.upper())
        if env is not None and f.name != "weights":
            setattr(s, f.name, _coerce(env, getattr(s, f.name)))
    for k, v in overrides.items():
        if v is not None and hasattr(s, k):
            setattr(s, k, _coerce(str(v), getattr(s, k)) if isinstance(v, str) else v)
    if isinstance(s.data_dir, str):
        s.data_dir = Path(s.data_dir)
    return s
