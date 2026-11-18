#!/usr/bin/env python3
"""News-Scanner für das KI-Trend-Radar.

Holt die aktuell heißesten KI-Themen von Hacker News und den Subreddits
r/ClaudeAI und r/artificial und schreibt sie nach data/news.json.

Nur öffentliche Endpunkte, keine Logins, keine API-Schlüssel, nur die
Python-Standardbibliothek.

Aufruf (vom Repo-Wurzelverzeichnis):  python scripts/news.py
Format der Ausgabe: siehe docs/data-contract.md.

Fällt eine Quelle aus (z. B. weil Reddit die IP eines GitHub-Runners
sperrt), bleiben die anderen Quellen erhalten. Für die ausgefallene Quelle
werden die Einträge aus dem letzten erfolgreichen Lauf übernommen und im
Block "sources" als stale markiert. Exit-Code 1 nur, wenn gar keine
Quelle Daten liefert.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = (
    "python:trend-radar-news-scanner:1.0 "
    "(+https://github.com/neubauerwilli/trend-radar)"
)
TIMEOUT = 20

# Datenvertrag: bis zu 30 Einträge pro Quelle
HN_LIMIT = 30
REDDIT_LIMIT = 30
SUBREDDITS = ["ClaudeAI", "artificial"]

# Begriffe, an denen ein HN-Titel als KI-Thema erkannt wird.
# Kurze Kürzel (AI, LLM, ...) nur als ganzes Wort, damit z. B. "said" nicht trifft.
AI_PATTERN = re.compile(
    r"""
    \b(
        AI | A\.I\. | AGI | LLMs? | GPT[-\w.]* | ChatGPT | OpenAI | Anthropic
      | Claude | Gemini | Llama[-\w.]* | Mistral | DeepSeek | Qwen | Grok
      | Copilot | Hugging\s?Face | MCP | RAG | GenAI
      | machine[\s-]learning | deep[\s-]learning | neural[\s-]net\w* | transformers?
      | diffusion | embeddings? | fine[\s-]?tun\w* | inference | chatbots?
      | (?:AI|coding|autonomous)[\s-]agents? | agentic | artificial[\s-]intelligence
      | language[\s-]models? | vibe[\s-]coding | prompt\w*
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)


def is_ai_topic(title: str) -> bool:
    return bool(AI_PATTERN.search(title or ""))


def http_get(url: str, accept: str = "application/json") -> bytes:
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": accept}
    )
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            last_err = e
            # 403/404 werden durch Warten nicht besser
            if e.code in (401, 403, 404):
                break
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{url}: {last_err}")


def get_json(url: str):
    return json.loads(http_get(url))


def iso(ts: float | int | None) -> str | None:
    if not ts:
        return None
    return utc_iso(dt.datetime.fromtimestamp(ts, dt.timezone.utc))


def utc_iso(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- Hacker News

def hn_item(hit_id, title, url, points, comments, created) -> dict:
    discussion = f"https://news.ycombinator.com/item?id={hit_id}"
    return {
        "source": "hackernews",
        "title": title,
        "url": url or discussion,
        "points": int(points or 0),
        "comments": int(comments or 0),
        "discussion_url": discussion,
        "created_at": created,
    }


def fetch_hn_algolia(hours: int) -> list[dict]:
    since = int(time.time()) - hours * 3600
    params = urllib.parse.urlencode(
        {
            "tags": "story",
            "numericFilters": f"created_at_i>{since},points>=10",
            "hitsPerPage": 1000,
        }
    )
    data = get_json(f"https://hn.algolia.com/api/v1/search?{params}")
    items = [
        hn_item(
            h["objectID"], h.get("title"), h.get("url"),
            h.get("points"), h.get("num_comments"), iso(h.get("created_at_i")),
        )
        for h in data.get("hits", [])
        if is_ai_topic(h.get("title", ""))
    ]
    return items


def fetch_hn_firebase(hours: int) -> list[dict]:
    """Fallback: offizielle Firebase-API, Top-Stories einzeln laden."""
    base = "https://hacker-news.firebaseio.com/v0"
    ids = get_json(f"{base}/topstories.json")[:200]
    since = time.time() - hours * 3600

    def load(i):
        try:
            return get_json(f"{base}/item/{i}.json")
        except Exception:
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        stories = list(pool.map(load, ids))
    return [
        hn_item(
            s["id"], s.get("title"), s.get("url"),
            s.get("score"), s.get("descendants"), iso(s.get("time")),
        )
        for s in stories
        if s and s.get("type") == "story" and not s.get("dead")
        and s.get("time", 0) >= since and is_ai_topic(s.get("title", ""))
    ]


def fetch_hackernews(hours: int) -> tuple[list[dict], str]:
    try:
        items, via = fetch_hn_algolia(hours), "algolia"
    except Exception as e:
        print(f"[hn] Algolia fehlgeschlagen ({e}), nutze Firebase", file=sys.stderr)
        items, via = fetch_hn_firebase(hours), "firebase"
    items.sort(key=lambda x: (x["points"], x["comments"]), reverse=True)
    return items[:HN_LIMIT], via


# --------------------------------------------------------------------- Reddit

def reddit_item(sub: str, d: dict) -> dict:
    permalink = "https://www.reddit.com" + d.get("permalink", "")
    url = d.get("url_overridden_by_dest") or d.get("url") or permalink
    return {
        "source": f"r/{sub}",
        "title": d.get("title"),
        "url": url,
        "points": int(d.get("score") or 0),
        "comments": int(d.get("num_comments") or 0),
        "discussion_url": permalink,
        "created_at": iso(d.get("created_utc")),
    }


def fetch_reddit_json(sub: str, host: str) -> list[dict]:
    data = get_json(f"https://{host}/r/{sub}/top.json?t=day&limit=50&raw_json=1")
    posts = [c["data"] for c in data["data"]["children"]]
    return [
        reddit_item(sub, p)
        for p in posts
        if not p.get("stickied") and not p.get("over_18")
    ]


def fetch_subreddit(sub: str) -> tuple[list[dict], str]:
    errors = []
    for host in ("www.reddit.com", "old.reddit.com"):
        try:
            items = fetch_reddit_json(sub, host)
            items.sort(key=lambda x: (x["points"], x["comments"]), reverse=True)
            return items[:REDDIT_LIMIT], f"json:{host}"
        except Exception as e:
            errors.append(str(e))
    raise RuntimeError(" | ".join(errors))


# ----------------------------------------------------------------------- Main

def load_previous(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="data/news.json")
    ap.add_argument("--hours", type=int, default=24,
                    help="Zeitfenster für Hacker News in Stunden (Standard 24)")
    args = ap.parse_args()

    previous = load_previous(args.out)
    prev_items = previous.get("items", [])
    now = utc_iso(dt.datetime.now(dt.timezone.utc))

    jobs = {"hackernews": lambda: fetch_hackernews(args.hours)}
    for sub in SUBREDDITS:
        jobs[f"r/{sub}"] = (lambda s=sub: fetch_subreddit(s))

    items: list[dict] = []
    sources: dict[str, dict] = {}
    any_fresh = False
    for name, job in jobs.items():
        try:
            got, via = job()
            items.extend(got)
            sources[name] = {"ok": True, "via": via, "count": len(got),
                             "fetched_at": now}
            any_fresh = True
            print(f"[ok]   {name}: {len(got)} Einträge via {via}", file=sys.stderr)
        except Exception as e:
            old = [i for i in prev_items if i.get("source") == name]
            items.extend(old)
            prev_src = previous.get("sources", {}).get(name, {})
            sources[name] = {
                "ok": False,
                "error": str(e)[:500],
                "count": len(old),
                "stale": bool(old),
                "fetched_at": prev_src.get("fetched_at") if old else None,
            }
            print(f"[FAIL] {name}: {e} (übernehme {len(old)} alte Einträge)",
                  file=sys.stderr)

    if not any_fresh:
        print("Keine Quelle erreichbar, news.json bleibt unverändert.",
              file=sys.stderr)
        return 1

    out = {"generated_at": now, "sources": sources, "items": items}
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    tmp = args.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, args.out)
    print(f"{len(items)} Einträge nach {args.out} geschrieben.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
