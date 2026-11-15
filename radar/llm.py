"""Optional LLM layer. Talks to any OpenAI-compatible chat endpoint, so the
free options all work:

  Ollama     RADAR_LLM_BASE_URL=http://localhost:11434/v1  RADAR_LLM_MODEL=qwen2.5:7b
  LM Studio  RADAR_LLM_BASE_URL=http://localhost:1234/v1   RADAR_LLM_MODEL=<loaded model>
  Groq / OpenRouter free tiers: set RADAR_LLM_API_KEY as well.

Every feature that uses it has a non-LLM fallback, so nothing breaks without it.
"""
from __future__ import annotations

import json
import re

import requests

from .config import Settings


class LLMUnavailable(RuntimeError):
    pass


def chat(s: Settings, system: str, user: str, temperature: float = 0.3, max_tokens: int = 900) -> str:
    if not s.llm_enabled:
        raise LLMUnavailable("No LLM configured (set RADAR_LLM_BASE_URL and RADAR_LLM_MODEL).")
    headers = {"Content-Type": "application/json"}
    if s.llm_api_key:
        headers["Authorization"] = f"Bearer {s.llm_api_key}"
    try:
        r = requests.post(s.llm_base_url.rstrip("/") + "/chat/completions", headers=headers, timeout=300, json={
            "model": s.llm_model, "temperature": temperature, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        })
        r.raise_for_status()
    except requests.RequestException as e:
        raise LLMUnavailable(f"LLM request failed: {e}") from e
    return r.json()["choices"][0]["message"]["content"]


def chat_json(s: Settings, system: str, user: str, **kw) -> dict:
    text = chat(s, system + "\nReply with a single JSON object and nothing else.", user, **kw)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)  # reasoning models
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise LLMUnavailable(f"LLM did not return JSON: {text[:200]}")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise LLMUnavailable(f"LLM returned malformed JSON: {e}") from e


SYS_RESEARCHER = ("You are a senior ML researcher helping a small academic group pick research directions. "
                  "Be concrete and skeptical. Never invent paper titles or numbers that are not in the prompt.")


def label_cluster(s: Settings, keywords: list[str], titles: list[str]) -> dict:
    user = ("Keywords: " + ", ".join(keywords[:12]) + "\nRepresentative paper titles:\n- " + "\n- ".join(titles[:12]) +
            '\n\nGive {"label": a 2-5 word topic name, "summary": 2 sentences on what this research area works on '
            'and its main open tension}.')
    return chat_json(s, SYS_RESEARCHER, user, max_tokens=300)


def refine_idea(s: Settings, idea: dict, neighbours: list[dict], open_problems: list[str]) -> dict:
    nb = "\n".join(f"- [{n['venue'].upper()} {n['year']}] {n['title']} (similarity {n['similarity']:.2f})" for n in neighbours[:10])
    op = "\n".join(f"- {o}" for o in open_problems[:8])
    user = f"""Raw idea: {idea.get('title')}
Why it came up: {idea.get('rationale', '')}

Closest existing papers:
{nb or '(none)'}

Open problems stated in nearby papers:
{op or '(none)'}

Return {{"research_question": one sentence,
 "hypothesis": one falsifiable sentence,
 "killing_experiment": the cheapest experiment that would show the idea does not work,
 "first_week_plan": 3 short bullet strings,
 "risk": the main reason this might already be done or not matter,
 "differentiation": how to differ from the closest papers above,
 "verdict": "pursue" | "refine" | "drop"}}"""
    return chat_json(s, SYS_RESEARCHER, user, max_tokens=900)


def summarize_cluster_gaps(s: Settings, label: str, open_problems: list[str]) -> str:
    user = (f"Topic: {label}\nSentences from abstracts admitting gaps:\n- " + "\n- ".join(open_problems[:25]) +
            "\n\nGroup these into 3-5 recurring open problems. One line each, most frequent first.")
    return chat(s, SYS_RESEARCHER, user, max_tokens=500)
