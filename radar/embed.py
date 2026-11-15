"""Text embeddings with swappable backends.

  tfidf                  TF-IDF (1-2 grams, sublinear) -> TruncatedSVD (LSA).
                         No download, ~30 s for 30k papers on a laptop CPU.
                         Default.
  fastembed              ONNX models on CPU (pip install fastembed); default
                         BAAI/bge-small-en-v1.5. Better semantics, ~5-10 min / 30k.
  sentence-transformers  any SBERT model (pip install sentence-transformers);
                         default 'all-MiniLM-L6-v2'.
  ollama                 a local Ollama embedding model, default nomic-embed-text.

Two vectors are stored per paper: `full` (title + abstract) and `title`.
Title-only papers (older years) are placed by comparing their *title* vector
against cluster centroids built from the *titles* of papers that have
abstracts, so both kinds of paper are compared like-for-like.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import joblib
import numpy as np

from .config import SEED, Settings
from .text import stopwords


def _l2(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x, axis=1, keepdims=True)
    n[n == 0] = 1
    return (x / n).astype(np.float32)


class TfidfBackend:
    name = "tfidf"

    def __init__(self, dim: int = 256):
        self.dim = dim
        self.vec = None
        self.svd = None

    def fit(self, texts: list[str]):
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.vec = TfidfVectorizer(
            ngram_range=(1, 2), min_df=3, max_df=0.4, sublinear_tf=True,
            stop_words=stopwords(), max_features=120_000, dtype=np.float32,
            token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z0-9\-]+\b",
        )
        X = self.vec.fit_transform(texts)
        k = max(2, min(self.dim, X.shape[1] - 1, X.shape[0] - 1))
        self.svd = TruncatedSVD(n_components=k, random_state=SEED, algorithm="randomized", n_iter=6)
        self.svd.fit(X)
        return self

    def encode(self, texts: list[str]) -> np.ndarray:
        return _l2(self.svd.transform(self.vec.transform(texts)))


class FastEmbedBackend:
    name = "fastembed"

    def __init__(self, model: str = ""):
        from fastembed import TextEmbedding

        self.model_name = model or "BAAI/bge-small-en-v1.5"
        self.model = TextEmbedding(self.model_name)

    def fit(self, texts):
        return self

    def encode(self, texts):
        return _l2(np.array(list(self.model.embed(texts, batch_size=64))))

    def __getstate__(self):
        return {"model_name": self.model_name}

    def __setstate__(self, st):
        self.__init__(st["model_name"])


class SbertBackend:
    name = "sentence-transformers"

    def __init__(self, model: str = ""):
        from sentence_transformers import SentenceTransformer

        self.model_name = model or "all-MiniLM-L6-v2"
        self.model = SentenceTransformer(self.model_name, device="cpu")

    def fit(self, texts):
        return self

    def encode(self, texts):
        return _l2(self.model.encode(texts, batch_size=64, show_progress_bar=len(texts) > 500))

    def __getstate__(self):
        return {"model_name": self.model_name}

    def __setstate__(self, st):
        self.__init__(st["model_name"])


class OllamaBackend:
    name = "ollama"

    def __init__(self, model: str = "", base_url: str = "http://localhost:11434"):
        self.model_name = model or "nomic-embed-text"
        self.base = base_url.replace("/v1", "").rstrip("/")

    def fit(self, texts):
        return self

    def encode(self, texts):
        import requests

        out = []
        for i in range(0, len(texts), 64):
            r = requests.post(f"{self.base}/api/embed", json={"model": self.model_name, "input": texts[i:i + 64]}, timeout=300)
            r.raise_for_status()
            out.extend(r.json()["embeddings"])
        return _l2(np.array(out))


def make_backend(s: Settings):
    b = s.embed_backend
    if b == "tfidf":
        return TfidfBackend(s.embed_dim)
    if b == "fastembed":
        return FastEmbedBackend(s.embed_model)
    if b in ("sentence-transformers", "sbert"):
        return SbertBackend(s.embed_model)
    if b == "ollama":
        return OllamaBackend(s.embed_model, s.llm_base_url or "http://localhost:11434")
    raise ValueError(f"unknown embed backend {b}")


class EmbeddingStore:
    """Embeddings on disk, aligned to a list of paper keys."""

    def __init__(self, s: Settings):
        self.s = s
        self.dir = s.emb_dir

    def _sig(self, keys: list[str], texts: list[str]) -> str:
        h = hashlib.sha1(self.s.embed_backend.encode() + self.s.embed_model.encode() + str(self.s.embed_dim).encode())
        for k, t in zip(keys, texts):
            h.update(k.encode())
            h.update(str(len(t)).encode())
        return h.hexdigest()

    def build(self, keys: list[str], full_texts: list[str], title_texts: list[str],
              fit_mask: np.ndarray | None = None, force: bool = False, log=print):
        sig = self._sig(keys, full_texts)
        meta_p = self.dir / "meta.json"
        if not force and meta_p.exists() and json.loads(meta_p.read_text()).get("sig") == sig:
            log("  embeddings up to date")
            return self.load()
        self.dir.mkdir(parents=True, exist_ok=True)
        backend = make_backend(self.s)
        fit_texts = [t for t, m in zip(full_texts, fit_mask if fit_mask is not None else [True] * len(keys)) if m]
        log(f"  fitting {backend.name} on {len(fit_texts):,} documents")
        backend.fit(fit_texts)
        log(f"  encoding {len(keys):,} full texts")
        full = backend.encode(full_texts)
        log(f"  encoding {len(keys):,} titles")
        title = backend.encode(title_texts)
        np.save(self.dir / "full.npy", full)
        np.save(self.dir / "title.npy", title)
        joblib.dump(backend, self.dir / "backend.joblib")
        meta_p.write_text(json.dumps({"sig": sig, "keys": keys, "backend": backend.name}))
        return keys, full, title

    def load(self):
        meta = json.loads((self.dir / "meta.json").read_text())
        return meta["keys"], np.load(self.dir / "full.npy"), np.load(self.dir / "title.npy")

    def backend(self):
        return joblib.load(self.dir / "backend.joblib")

    def exists(self) -> bool:
        return (self.dir / "meta.json").exists()


def encode_query(s: Settings, texts: list[str]) -> np.ndarray:
    return EmbeddingStore(s).backend().encode(texts)
