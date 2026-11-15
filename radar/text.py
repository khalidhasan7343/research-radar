"""Small text utilities shared across the pipeline."""
from __future__ import annotations

import re
import unicodedata

_WS = re.compile(r"\s+")
_NONALNUM = re.compile(r"[^a-z0-9 ]+")
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[])")
_LATEX = re.compile(r"\$[^$]*\$")

# Words that are everywhere in ML abstracts and carry no topical signal.
DOMAIN_STOPWORDS = {
    "paper", "propose", "proposed", "proposes", "approach", "approaches", "method",
    "methods", "novel", "results", "result", "show", "shows", "demonstrate",
    "demonstrates", "experiments", "experimental", "performance", "state", "art",
    "existing", "new", "based", "using", "use", "used", "work", "framework",
    "task", "tasks", "problem", "problems", "significantly", "achieve", "achieves",
    "improve", "improves", "improved", "improvement", "extensive", "various",
    "different", "however", "also", "well", "model", "models", "data", "learning",
    "code", "available", "github", "https", "com", "propose", "introduce",
    "introduces", "present", "presents", "study", "studies", "benchmark",
    "benchmarks", "outperforms", "superior", "effective", "efficient", "key",
    "via", "et", "al", "first", "two", "three", "one", "can", "may", "while",
    "thus", "furthermore", "moreover", "e.g", "i.e", "etc", "across", "towards",
    "toward", "position", "anonymous", "remains", "address", "leverage",
    "leverages", "leveraging", "enables", "enable", "significant", "datasets",
    "dataset", "training", "trained", "train", "learn", "learned", "neural",
    "network", "networks", "deep", "tasks", "large", "prior", "recent", "recently",
    "highly", "strong", "robust", "simple", "general", "specific", "able",
}


def normalize_title(title: str) -> str:
    """Lowercase ASCII title with punctuation removed; used for dedupe."""
    t = unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode()
    t = _NONALNUM.sub(" ", t.lower())
    return _WS.sub(" ", t).strip()


def clean_text(text: str) -> str:
    text = _LATEX.sub(" ", text or "")
    return _WS.sub(" ", text).strip()


def sentences(text: str) -> list[str]:
    text = clean_text(text)
    if not text:
        return []
    return [s.strip() for s in _SENT.split(text) if len(s.strip()) > 20]


def doc_text(title: str, abstract: str | None) -> str:
    title = clean_text(title)
    abstract = clean_text(abstract or "")
    return f"{title}. {abstract}" if abstract else title


def stopwords() -> list[str]:
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

    return sorted(set(ENGLISH_STOP_WORDS) | DOMAIN_STOPWORDS)


def openalex_abstract(inverted: dict | None) -> str:
    """Rebuild an abstract from OpenAlex's abstract_inverted_index."""
    if not inverted:
        return ""
    pos = []
    for word, idxs in inverted.items():
        for i in idxs:
            pos.append((i, word))
    pos.sort()
    return " ".join(w for _, w in pos)
