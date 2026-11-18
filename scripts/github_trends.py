#!/usr/bin/env python3
"""GitHub-Trends der Woche: die zehn KI-Repositories mit den meisten neuen Sternen.

Datenquelle: die öffentliche Seite https://github.com/trending?since=weekly
(plus einige Sprach-Unterseiten, damit genug KI-Kandidaten zusammenkommen).
Kein Login und kein API-Schlüssel nötig. Nur die Python-Standardbibliothek.

Was zählt als "KI"?
    Ein Repository gilt als KI-Repository, wenn sein Name oder seine
    Beschreibung mindestens einen Begriff aus AI_KEYWORDS enthält (ohne
    Groß-/Kleinschreibung, nur ganze Wörter bzw. Wortanfänge, siehe unten).
    Optional: Ist die Umgebungsvariable GITHUB_TOKEN gesetzt (in GitHub
    Actions automatisch vorhanden), werden für Repos ohne Treffer zusätzlich
    die GitHub-Topics geprüft. Ohne Token läuft das Skript genauso, nur ohne
    diese zweite Prüfung.

Sortierung: nach "stars this week" absteigend, die ersten zehn.
Ausgabeformat: siehe docs/data-contract.md (Abschnitt data/github.json).
Findet das Skript keine zehn KI-Repos oder schlägt der Abruf fehl, bleibt die
alte data/github.json unverändert und der Exit-Code ist 1.

Aufruf:
    python scripts/github_trends.py                    # schreibt data/github.json
    python scripts/github_trends.py --out pfad.json
    python scripts/github_trends.py --html datei.html  # offline aus gespeicherter Seite
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

TRENDING_URL = "https://github.com/trending{lang}?since=weekly"

# Gesamtliste plus Sprachen, in denen KI-Projekte üblicherweise landen.
# Jede Seite liefert bis zu 25 Repos; zusammen ergibt das genug Kandidaten,
# damit nach dem KI-Filter verlässlich zehn übrig bleiben.
LANGUAGES = ["", "python", "typescript", "jupyter-notebook", "rust", "go", "c%2B%2B"]

TOP_N = 10
USER_AGENT = "trend-radar/1.0 (+https://github.com/neubauerwilli/trend-radar)"

# Begriffe, die ein Repo als KI-Projekt markieren. Groß-/Kleinschreibung egal.
# Einträge ohne "*" müssen als ganzes Wort vorkommen ("ai" trifft "AI-powered",
# aber nicht "maintain"). Einträge mit "*" am Ende matchen Wortanfänge
# ("fine-tun*" trifft "fine-tuning", "fine-tune").
AI_KEYWORDS = [
    # allgemein
    "ai", "artificial intelligence", "genai", "generative",
    "machine learning", "deep learning", "neural network*", "ml",
    # Modelle und Technik
    "llm*", "large language model*", "language model*", "gpt*", "transformer*",
    "diffusion", "stable diffusion", "multimodal", "vision-language", "vlm*",
    "embedding*", "vector database*", "rag", "retrieval-augmented",
    "fine-tun*", "lora", "inference", "quantiz*", "tokenizer*",
    "reinforcement learning", "rlhf",
    # Agenten und Werkzeuge
    "agent", "agents", "agentic", "ai agent*", "mcp", "model context protocol",
    "copilot*", "chatbot*", "prompt*", "langchain", "llamaindex", "autogen",
    # Anbieter und Modellfamilien
    "openai", "chatgpt", "anthropic", "claude", "gemini", "llama*", "ollama",
    "mistral", "qwen*", "deepseek*", "hugging ?face", "whisper",
    # Frameworks
    "pytorch", "tensorflow", "jax", "onnx", "vllm", "llama.cpp",
    # Anwendungsfelder
    "text-to-speech", "tts", "speech recognition", "asr", "computer vision",
    "object detection", "image generation", "video generation", "ocr",
]

# GitHub-Topics, die (nur mit GITHUB_TOKEN) zusätzlich als KI zählen.
AI_TOPICS = {
    "ai", "artificial-intelligence", "machine-learning", "deep-learning", "llm",
    "llms", "large-language-models", "generative-ai", "genai", "gpt", "openai",
    "chatgpt", "anthropic", "claude", "agents", "ai-agents", "agent", "rag",
    "mcp", "nlp", "computer-vision", "pytorch", "tensorflow", "transformers",
    "diffusion", "stable-diffusion", "ollama", "langchain", "llama",
}


def _keyword_pattern(keywords: list[str]) -> re.Pattern[str]:
    parts = []
    for kw in keywords:
        prefix = kw.endswith("*")
        kw = kw.rstrip("*")
        # "hugging ?face" ist bewusst ein Mini-Regex; alles andere wörtlich.
        body = re.escape(kw).replace(r"\ \?", " ?").replace(r"\ ", r"[\s_-]")
        parts.append(body + (r"\w*" if prefix else ""))
    return re.compile(r"(?<![\w.])(?:" + "|".join(parts) + r")(?![\w])", re.IGNORECASE)


AI_PATTERN = _keyword_pattern(AI_KEYWORDS)


# Wendungen, die KI-Begriffe enthalten, aber nichts mit KI zu tun haben.
NOT_AI_PATTERN = re.compile(r"user[\s_-]?agents?|build[\s_-]?agents?|ssh[\s_-]?agents?", re.IGNORECASE)


def ai_match(text: str) -> str | None:
    """Gibt den ersten gefundenen KI-Begriff zurück, sonst None."""
    m = AI_PATTERN.search(NOT_AI_PATTERN.sub(" ", text))
    return m.group(0).lower() if m else None


# ---------------------------------------------------------------- Abruf


def fetch(url: str, headers: dict[str, str] | None = None, retries: int = 3) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError) as err:
            last_err = err
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Abruf fehlgeschlagen: {url}: {last_err}")


# ---------------------------------------------------------------- Parsen

_ARTICLE_RE = re.compile(r'<article class="Box-row">(.*?)</article>', re.S)
_NAME_RE = re.compile(r'<h2[^>]*>.*?<a[^>]*href="/([^"/]+/[^"/]+)"', re.S)
_DESC_RE = re.compile(r'<p class="col-9[^"]*">(.*?)</p>', re.S)
_LANG_RE = re.compile(r'itemprop="programmingLanguage">(.*?)</span>', re.S)
_TOTAL_RE = re.compile(r'href="/[^"]+/stargazers"[^>]*>(.*?)</a>', re.S)
_WEEK_RE = re.compile(r'([\d,.]+)\s+stars?\s+this\s+week', re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def _text(fragment: str) -> str:
    return " ".join(html.unescape(_TAG_RE.sub(" ", fragment)).split())


def _int(s: str) -> int:
    digits = re.sub(r"[^\d]", "", s)
    return int(digits) if digits else 0


def parse_trending(page: str) -> list[dict]:
    repos = []
    for block in _ARTICLE_RE.findall(page):
        name_m = _NAME_RE.search(block)
        week_m = _WEEK_RE.search(block)
        if not name_m or not week_m:
            continue
        name = name_m.group(1).strip()
        desc_m = _DESC_RE.search(block)
        lang_m = _LANG_RE.search(block)
        total_m = _TOTAL_RE.search(block)
        repos.append({
            "name": name,
            "url": f"https://github.com/{name}",
            "description": (_text(desc_m.group(1)) if desc_m else "") or None,
            "stars_week": _int(week_m.group(1)),
            "stars_total": _int(_text(total_m.group(1))) if total_m else None,
            "language": _text(lang_m.group(1)) if lang_m else None,
        })
    return repos


# ---------------------------------------------------------------- Topics (optional)


def fetch_topics(name: str, token: str) -> list[str]:
    try:
        data = json.loads(fetch(
            f"https://api.github.com/repos/{name}/topics",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            retries=1,
        ))
        return data.get("names", [])
    except Exception:  # Topics sind nur ein Zusatz; Fehler ignorieren.
        return []


# ---------------------------------------------------------------- Ablauf


def collect(pages: list[str], token: str | None) -> tuple[list[dict], int]:
    seen: dict[str, dict] = {}
    for page in pages:
        for repo in parse_trending(page):
            # Dasselbe Repo kann auf mehreren Sprachseiten stehen.
            if repo["name"] not in seen or repo["stars_week"] > seen[repo["name"]]["stars_week"]:
                seen[repo["name"]] = repo

    candidates = sorted(seen.values(), key=lambda r: r["stars_week"], reverse=True)
    picked = []
    for repo in candidates:
        hit = ai_match(f'{repo["name"].replace("/", " ")} {repo["description"] or ""}')
        if hit:
            repo["ai_match"] = f"keyword:{hit}"
        elif token:
            topics = set(fetch_topics(repo["name"], token)) & AI_TOPICS
            if topics:
                repo["ai_match"] = f"topic:{sorted(topics)[0]}"
        if "ai_match" in repo:
            picked.append(repo)
        if len(picked) == TOP_N:
            break

    for i, repo in enumerate(picked, 1):
        repo["rank"] = i
    return picked, len(candidates)


def build_output(repos: list[dict], candidates: int, sources: list[str]) -> dict:
    keys = ["rank", "name", "url", "description", "stars_week", "stars_total", "language", "ai_match"]
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "period": "weekly",
        "sources": sources,
        "candidates_checked": candidates,
        "ai_filter": (
            "Name oder Beschreibung enthält einen KI-Begriff (siehe AI_KEYWORDS in "
            "scripts/github_trends.py); mit GITHUB_TOKEN zusätzlich GitHub-Topics."
        ),
        "repos": [{k: r.get(k) for k in keys} for r in repos],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "data" / "github.json"))
    ap.add_argument("--html", nargs="*", help="Gespeicherte Trending-Seite(n) statt Live-Abruf")
    args = ap.parse_args(argv)

    if args.html:
        sources = [str(p) for p in args.html]
        pages = [Path(p).read_text(encoding="utf-8") for p in args.html]
    else:
        sources, pages = [], []
        for lang in LANGUAGES:
            url = TRENDING_URL.format(lang=f"/{lang}" if lang else "")
            try:
                pages.append(fetch(url))
                sources.append(url)
            except RuntimeError as err:
                print(f"Warnung: {err}", file=sys.stderr)
            time.sleep(1)  # GitHub freundlich behandeln

    token = os.environ.get("GITHUB_TOKEN") if not args.html else None
    repos, candidates = collect(pages, token)

    if len(repos) < TOP_N:
        # Datenvertrag: genau 10 Repos. Lieber die alte Datei behalten als
        # das Dashboard mit unvollständigen Daten zu füllen.
        print(f"Fehler: nur {len(repos)} KI-Repos unter {candidates} Kandidaten gefunden, "
              f"{args.out} bleibt unverändert.", file=sys.stderr)
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Erst in eine temporäre Datei schreiben, dann atomar umbenennen.
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(build_output(repos, candidates, sources), ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    os.replace(tmp, out)
    print(f"{len(repos)} KI-Repos aus {candidates} Kandidaten -> {out}")
    for r in repos:
        print(f'  {r["rank"]:>2}. {r["name"]:<45} +{r["stars_week"]:>6}  ({r["ai_match"]})')
    return 0


if __name__ == "__main__":
    sys.exit(main())
