"""Registry of venues and how each source names them.

`s2`         Semantic Scholar `venue` filter value
`openalex`   search string used to resolve the OpenAlex source id (cached)
`openreview` OpenReview v2 venue id template, where the venue uses OpenReview
`area`       coarse field label, shown by `radar venues`
"""
from __future__ import annotations

VENUES: dict[str, dict] = {
    # --- core ML
    "neurips": {"name": "NeurIPS", "s2": "NeurIPS", "openalex": "Neural Information Processing Systems",
                "openreview": "NeurIPS.cc/{year}/Conference", "area": "ml"},
    "icml": {"name": "ICML", "s2": "ICML", "openalex": "International Conference on Machine Learning",
             "openreview": "ICML.cc/{year}/Conference", "area": "ml"},
    "iclr": {"name": "ICLR", "s2": "ICLR", "openalex": "International Conference on Learning Representations",
             "openreview": "ICLR.cc/{year}/Conference", "area": "ml"},
    "aistats": {"name": "AISTATS", "s2": "AISTATS", "openalex": "International Conference on Artificial Intelligence and Statistics",
                "openreview": "", "area": "ml"},
    "uai": {"name": "UAI", "s2": "UAI", "openalex": "Uncertainty in Artificial Intelligence", "openreview": "auai.org/UAI/{year}/Conference", "area": "ml"},
    "colt": {"name": "COLT", "s2": "COLT", "openalex": "Conference on Learning Theory", "openreview": "", "area": "ml"},
    "tmlr": {"name": "TMLR", "s2": "Trans. Mach. Learn. Res.", "openalex": "Transactions on Machine Learning Research",
             "openreview": "TMLR", "area": "ml"},
    "colm": {"name": "COLM", "s2": "COLM", "openalex": "Conference on Language Modeling", "openreview": "colmweb.org/COLM/{year}/Conference", "area": "nlp"},
    # --- vision
    "cvpr": {"name": "CVPR", "s2": "CVPR", "openalex": "Computer Vision and Pattern Recognition", "openreview": "", "area": "cv"},
    "iccv": {"name": "ICCV", "s2": "ICCV", "openalex": "International Conference on Computer Vision", "openreview": "", "area": "cv"},
    "eccv": {"name": "ECCV", "s2": "ECCV", "openalex": "European Conference on Computer Vision", "openreview": "", "area": "cv"},
    # --- NLP
    "acl": {"name": "ACL", "s2": "ACL", "openalex": "Annual Meeting of the Association for Computational Linguistics", "openreview": "", "area": "nlp"},
    "emnlp": {"name": "EMNLP", "s2": "EMNLP", "openalex": "Empirical Methods in Natural Language Processing", "openreview": "", "area": "nlp"},
    "naacl": {"name": "NAACL", "s2": "NAACL", "openalex": "North American Chapter of the Association for Computational Linguistics", "openreview": "", "area": "nlp"},
    # --- AI general
    "aaai": {"name": "AAAI", "s2": "AAAI", "openalex": "AAAI Conference on Artificial Intelligence", "openreview": "", "area": "ai"},
    "ijcai": {"name": "IJCAI", "s2": "IJCAI", "openalex": "International Joint Conference on Artificial Intelligence", "openreview": "", "area": "ai"},
    # --- data mining / IR
    "kdd": {"name": "KDD", "s2": "KDD", "openalex": "Knowledge Discovery and Data Mining", "openreview": "", "area": "dm"},
    "www": {"name": "WWW", "s2": "WWW", "openalex": "The Web Conference", "openreview": "", "area": "dm"},
    "sigir": {"name": "SIGIR", "s2": "SIGIR", "openalex": "Research and Development in Information Retrieval", "openreview": "", "area": "dm"},
    # --- robotics
    "corl": {"name": "CoRL", "s2": "CoRL", "openalex": "Conference on Robot Learning", "openreview": "robot-learning.org/CoRL/{year}/Conference", "area": "robotics"},
    "icra": {"name": "ICRA", "s2": "ICRA", "openalex": "International Conference on Robotics and Automation", "openreview": "", "area": "robotics"},
    "rss": {"name": "RSS", "s2": "Robotics: Science and Systems", "openalex": "Robotics: Science and Systems", "openreview": "", "area": "robotics"},
    # --- preprints
    "arxiv": {"name": "arXiv", "s2": "arXiv", "openalex": "", "openreview": "", "area": "preprint"},
}

# arXiv categories that cover ML broadly.
ARXIV_ML_CATEGORIES = ["cs.LG", "cs.AI", "cs.CL", "cs.CV", "cs.RO", "stat.ML", "cs.IR", "cs.MA", "cs.NE"]


def venue_key(name: str) -> str:
    n = (name or "").strip().lower()
    if n in VENUES:
        return n
    for k, v in VENUES.items():
        if n in (v["name"].lower(), v["s2"].lower(), v["openalex"].lower()):
            return k
    return n.replace(" ", "_") or "unknown"


def venue_area(key: str) -> str:
    return VENUES.get(key, {}).get("area", "other")


def classify_presentation(text: str) -> str:
    t = (text or "").lower()
    for tier in ("oral", "spotlight", "poster"):
        if tier in t:
            return tier
    return ""
