"""Polite HTTP client: retries with backoff, rate limiting and an on-disk
response cache, so every crawl is resumable and re-runs cost nothing."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import requests


class HttpError(RuntimeError):
    pass


class Client:
    def __init__(self, cache_dir: Path, min_interval: float = 0.2, user_agent: str = "",
                 headers: dict | None = None, max_retries: int = 5):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval = min_interval
        self.max_retries = max_retries
        self._last = 0.0
        self.s = requests.Session()
        self.s.headers["User-Agent"] = user_agent or "research-radar/1.0 (+https://github.com/khalidhasan7343/research-radar)"
        if headers:
            self.s.headers.update(headers)

    def _key(self, url: str, params: dict | None) -> Path:
        raw = url + "?" + json.dumps(params or {}, sort_keys=True)
        return self.cache_dir / (hashlib.sha1(raw.encode()).hexdigest() + ".txt")

    # Cached responses older than this (seconds) are fetched again. None = keep
    # forever. Set per call-site: old years never change, the current one does.
    max_age: float | None = None

    def get(self, url: str, params: dict | None = None, use_cache: bool = True) -> str:
        path = self._key(url, params)
        if use_cache and path.exists():
            fresh = self.max_age is None or (time.time() - path.stat().st_mtime) < self.max_age
            if fresh:
                return path.read_text(encoding="utf-8")
        delay = 2.0
        for attempt in range(self.max_retries):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                r = self.s.get(url, params=params, timeout=60)
            except requests.RequestException as e:
                err = str(e)
            else:
                if r.status_code == 200:
                    if use_cache:
                        path.write_text(r.text, encoding="utf-8")
                    return r.text
                err = f"HTTP {r.status_code}: {r.text[:200]}"
                if r.status_code in (400, 401, 403, 404):
                    raise HttpError(f"{url} -> {err}")
                ra = r.headers.get("Retry-After")
                if ra and ra.isdigit():
                    delay = max(delay, float(ra))
            time.sleep(delay)
            delay = min(delay * 2, 120)
        raise HttpError(f"{url} failed after {self.max_retries} attempts: {err}")

    def get_json(self, url: str, params: dict | None = None, use_cache: bool = True) -> dict:
        return json.loads(self.get(url, params, use_cache))
