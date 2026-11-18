#!/usr/bin/env python3
"""Content-Ideen fürs KI-Trend-Radar.

Liest data/news.json und data/github.json (Format: docs/data-contract.md),
bündelt die Beiträge zu Themen, wählt die fünf heißesten und schreibt für jedes
Thema eine Idee für einen Short, ein Karussell und ein langes Video nach
data/ideas.json.

Standard ist der Vorlagen-Modus: keine API, kein Schlüssel, nur Python-Standardbibliothek.
Optional können die Ideen von Claude geschrieben werden (siehe docs/ideas.md,
Abschnitt „Claude-Modus“). Schlägt das fehl, greifen automatisch die Vorlagen.

Aufruf vom Repo-Wurzelverzeichnis:  python scripts/ideas.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_NEWS = ROOT / "data" / "news.json"
DEFAULT_GITHUB = ROOT / "data" / "github.json"
DEFAULT_OUT = ROOT / "data" / "ideas.json"

TOPIC_COUNT = 5
MAX_SOURCES_PER_TOPIC = 5

# --------------------------------------------------------------------------
# Themen-Katalog
# --------------------------------------------------------------------------
# Jeder Eintrag: Anzeigename, Suchmuster (Regex, ohne Groß/Kleinschreibung)
# und ein Blickwinkel, der in die Vorlagen einfließt. Reihenfolge = Vorrang
# bei Gleichstand. Ein Beitrag zählt nur zu einem Thema (dem mit den meisten Treffern).

@dataclass(frozen=True)
class TopicDef:
    name: str
    patterns: tuple[str, ...]
    angle: str          # Warum das Publikum das interessiert
    audience: str       # Für wen das Thema relevant ist


CATALOG: tuple[TopicDef, ...] = (
    TopicDef("Claude & Anthropic",
             (r"\bclaude\b", r"\banthropic\b", r"\bsonnet\b", r"\bopus\b", r"\bhaiku\b", r"claude[- ]code"),
             "was sich für alle ändert, die täglich mit Claude arbeiten", "Claude-Nutzer"),
    TopicDef("OpenAI & ChatGPT",
             (r"\bopenai\b", r"\bchatgpt\b", r"\bgpt-?\d", r"\bsora\b", r"\baltman\b", r"\bcodex\b"),
             "was OpenAI gerade vorhat und was davon wirklich neu ist", "ChatGPT-Nutzer"),
    TopicDef("Google Gemini",
             (r"\bgemini\b", r"\bdeepmind\b", r"\bgemma\b", r"\bveo\b", r"google (ai|labs)"),
             "wo Google im KI-Rennen gerade steht", "Google-Nutzer"),
    TopicDef("KI-Agenten",
             (r"\bagents?\b", r"\bagentic\b", r"multi-agent", r"\bautonomous\b", r"\blanggraph\b", r"\bcrewai\b", r"\bautogen\b"),
             "was KI-Agenten heute schon selbstständig erledigen können", "Leute, die Arbeit automatisieren wollen"),
    TopicDef("Programmieren mit KI",
             (r"\bcoding\b", r"\bcopilot\b", r"\bcursor\b", r"\bide\b", r"vibe[- ]coding", r"code (review|assistant|generation)",
              r"\bprogramm(ing|er)", r"\bswe-bench\b", r"\bdevelopers?\b", r"\bcli\b"),
             "wie sich Softwareentwicklung durch KI gerade verändert", "Entwickler"),
    TopicDef("MCP & Tool-Anbindung",
             (r"\bmcp\b", r"model context protocol", r"tool[- ]use", r"function calling", r"\bplugins?\b"),
             "wie man KI mit eigenen Tools und Daten verbindet", "Bastler und Entwickler"),
    TopicDef("Open-Source-Modelle",
             (r"\bllama\b", r"\bmistral\b", r"\bqwen\b", r"\bdeepseek\b", r"open[- ]weights?", r"open[- ]source (model|llm)",
              r"hugging ?face", r"\bkimi\b", r"\bphi-\d"),
             "ob offene Modelle mit den großen Anbietern mithalten", "Technik-Interessierte"),
    TopicDef("Lokale KI",
             (r"\bollama\b", r"llama\.cpp", r"\bgguf\b", r"on-device", r"\blocal(ly)?\b", r"self-host", r"\bmlx\b"),
             "wie man KI ohne Cloud auf dem eigenen Rechner nutzt", "Datenschutz-Bewusste"),
    TopicDef("RAG & Wissensdatenbanken",
             (r"\brag\b", r"\bretrieval\b", r"vector (db|database|store|search)", r"\bembeddings?\b", r"knowledge (base|graph)"),
             "wie KI zuverlässig mit eigenen Dokumenten arbeitet", "Teams mit viel Wissen in Dokumenten"),
    TopicDef("Bild- & Video-KI",
             (r"image generat", r"video generat", r"\bdiffusion\b", r"\bmidjourney\b", r"\bflux\b", r"text-to-(image|video)",
              r"\bimagen\b", r"\brunway\b"),
             "was Bild- und Video-KI inzwischen kann und wo die Grenzen sind", "Kreative"),
    TopicDef("Sprach- & Audio-KI",
             (r"\bvoice\b", r"\bspeech\b", r"\btts\b", r"\bwhisper\b", r"\baudio\b", r"\bpodcast\b"),
             "wie natürlich KI-Stimmen inzwischen klingen", "Creator und Podcaster"),
    TopicDef("KI-Sicherheit & Risiken",
             (r"\bsafety\b", r"\balignment\b", r"\bjailbreak", r"prompt injection", r"\bsecurity\b", r"\bhallucinat",
              r"\bvulnerab", r"\bdeepfake"),
             "welche Risiken real sind und welche übertrieben", "alle, die KI im Alltag nutzen"),
    TopicDef("KI-Regulierung & Recht",
             (r"\bregulat", r"ai act", r"\blawsuit\b", r"\bcopyright\b", r"\bcourt\b", r"\bcongress\b", r"\bgovernment\b",
              r"\bpolicy\b", r"\bban(s|ned)?\b", r"\beu\b", r"\blaw\b"),
             "welche Regeln für KI kommen und was sie konkret bedeuten", "Selbstständige und Unternehmen"),
    TopicDef("KI-Chips & Rechenzentren",
             (r"\bnvidia\b", r"\bgpus?\b", r"\bchips?\b", r"\btpus?\b", r"data ?cent(er|re)s?", r"\bamd\b", r"\bh100\b",
              r"\bb200\b", r"\bcompute\b"),
             "wer die Hardware hinter dem KI-Boom liefert und was das kostet", "Technik- und Börseninteressierte"),
    TopicDef("KI & Arbeitswelt",
             (r"\bjobs?\b", r"\blayoffs?\b", r"\bworkers?\b", r"\bemploy", r"\bhiring\b", r"\bproductivity\b", r"\bcareers?\b"),
             "wie KI Jobs und Arbeitsalltag verändert", "Berufstätige"),
    TopicDef("KI-Forschung & Benchmarks",
             (r"\bpaper\b", r"\bbenchmarks?\b", r"\barxiv\b", r"\bresearch(ers)?\b", r"\breasoning\b", r"\bstudy\b", r"\beval(s|uation)?\b"),
             "was neue Forschung wirklich zeigt, ohne Hype", "Wissenshungrige"),
    TopicDef("Robotik",
             (r"\brobots?\b", r"\brobotics\b", r"\bhumanoid", r"\bself-driving\b", r"\bwaymo\b", r"\btesla bot\b"),
             "wann KI-Roboter im Alltag ankommen", "Zukunftsinteressierte"),
    TopicDef("KI-Startups & Geld",
             (r"\bfunding\b", r"\braises?\b", r"\bvaluation\b", r"\bipo\b", r"\bacqui(res|sition)\b", r"\bstartups?\b",
              r"\bbillion\b", r"\$\d"),
             "wohin das Geld im KI-Markt gerade fließt", "Gründer und Investoren"),
)

_COMPILED = [(t, [re.compile(p, re.IGNORECASE) for p in t.patterns]) for t in CATALOG]
_BY_NAME = {t.name: t for t in CATALOG}

# Subreddits, deren Beiträge ohne Treffer trotzdem einem Thema zugeordnet werden.
SOURCE_DEFAULT_TOPIC = {"r/claudeai": "Claude & Anthropic"}

_STOPWORDS = set("""
the a an and or of to in on for with from by at is are was be this that it its how why what
your you we our new show hn ask i my can now just using use via vs about into than more not
ai llm llms model models open source
""".split())


# --------------------------------------------------------------------------
# Daten laden
# --------------------------------------------------------------------------

@dataclass
class Entry:
    kind: str           # "news" oder "repo"
    source: str         # hackernews, r/ClaudeAI, r/artificial, github
    title: str
    text: str           # Text für die Themenerkennung
    url: str
    link: str           # bevorzugter Link für "sources" (Diskussion bzw. Repo)
    points: int = 0
    comments: int = 0
    stars_week: int = 0
    heat: float = 0.0


def _int(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _load_json(path: Path, label: str):
    if not path.exists():
        print(f"Hinweis: {label} fehlt ({path}), wird übersprungen.", file=sys.stderr)
        return None
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_news(path: Path) -> list[Entry]:
    data = _load_json(path, "news.json")
    if not data:
        return []
    out = []
    for it in data.get("items", []):
        title = (it.get("title") or "").strip()
        if not title:
            continue
        url = it.get("url") or it.get("discussion_url") or ""
        out.append(Entry(
            kind="news",
            source=str(it.get("source") or "unbekannt"),
            title=title,
            text=title,
            url=url,
            link=it.get("discussion_url") or url,
            points=_int(it.get("points")),
            comments=_int(it.get("comments")),
        ))
    return out


def load_github(path: Path) -> list[Entry]:
    data = _load_json(path, "github.json")
    if not data:
        return []
    out = []
    for it in data.get("repos", []):
        name = (it.get("name") or "").strip()
        if not name:
            continue
        desc = (it.get("description") or "").strip()
        repo_words = name.split("/")[-1].replace("-", " ").replace("_", " ")
        url = it.get("url") or f"https://github.com/{name}"
        out.append(Entry(
            kind="repo",
            source="github",
            title=name,
            text=f"{repo_words} {desc}",
            url=url,
            link=url,
            stars_week=_int(it.get("stars_week")),
        ))
    return out


# --------------------------------------------------------------------------
# Hitze und Themen
# --------------------------------------------------------------------------

def score_entries(entries: list[Entry]) -> None:
    """Hitze je Eintrag, 0..1, innerhalb der eigenen Quelle normiert.

    Hacker News, Reddit und GitHub haben völlig unterschiedliche Größenordnungen.
    Deshalb wird jede Quelle für sich auf ihren Spitzenwert bezogen und logarithmisch
    gedämpft, damit ein einzelner Ausreißer nicht alles dominiert.
    """
    by_source: dict[str, list[Entry]] = {}
    for e in entries:
        by_source.setdefault(e.source, []).append(e)
    for items in by_source.values():
        if items[0].kind == "repo":
            top = max(math.log1p(e.stars_week) for e in items) or 1.0
            for e in items:
                e.heat = math.log1p(e.stars_week) / top
        else:
            top_p = max(math.log1p(e.points) for e in items) or 1.0
            top_c = max(math.log1p(e.comments) for e in items) or 1.0
            for e in items:
                e.heat = 0.6 * math.log1p(e.points) / top_p + 0.4 * math.log1p(e.comments) / top_c


def classify(entry: Entry) -> str | None:
    best, best_hits = None, 0
    for topic, regexes in _COMPILED:
        hits = sum(1 for rx in regexes if rx.search(entry.text))
        if hits > best_hits:
            best, best_hits = topic.name, hits
    if best is None:
        best = SOURCE_DEFAULT_TOPIC.get(entry.source.lower())
    return best


def _keywords(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9.+-]{2,}", text)
    return {w.strip(".-").lower() for w in words if w.lower() not in _STOPWORDS}


@dataclass
class Topic:
    name: str
    entries: list[Entry] = field(default_factory=list)
    definition: TopicDef | None = None

    @property
    def raw_heat(self) -> float:
        sources = {e.source for e in self.entries}
        # Bonus, wenn das Thema in mehreren Quellen gleichzeitig auftaucht.
        return sum(e.heat for e in self.entries) * (1 + 0.15 * (len(sources) - 1))

    @property
    def sorted_entries(self) -> list[Entry]:
        return sorted(self.entries, key=lambda e: e.heat, reverse=True)


def build_topics(entries: list[Entry]) -> list[Topic]:
    topics: dict[str, Topic] = {}
    leftovers: list[Entry] = []
    for e in entries:
        name = classify(e)
        if name is None:
            leftovers.append(e)
            continue
        topics.setdefault(name, Topic(name, definition=_BY_NAME.get(name))).entries.append(e)

    # Nicht zugeordnete Beiträge: gemeinsames Schlagwort in mindestens zwei Beiträgen
    # (z. B. ein neuer Produktname) wird zu einem eigenen Thema.
    counts = Counter(k for e in leftovers for k in _keywords(e.text))
    for word, n in counts.most_common():
        if n < 2:
            break
        group = [e for e in leftovers if word in _keywords(e.text)]
        if len(group) < 2:
            continue
        label = next((m for m in re.findall(r"[A-Za-z][A-Za-z0-9.+-]{2,}", " ".join(e.text for e in group))
                      if m.lower() == word), word)
        topics.setdefault(label, Topic(label)).entries.extend(group)
        leftovers = [e for e in leftovers if e not in group]

    ranked = sorted(topics.values(), key=lambda t: t.raw_heat, reverse=True)

    # Vertrag verlangt genau fünf Themen. Reichen die Bündel nicht, werden die
    # stärksten übrigen Einzelbeiträge zu eigenen Themen.
    if len(ranked) < TOPIC_COUNT:
        for e in sorted(leftovers, key=lambda x: x.heat, reverse=True):
            if len(ranked) >= TOPIC_COUNT:
                break
            ranked.append(Topic(_shorten(e.title, 40), [e]))
    return ranked[:TOPIC_COUNT]


# --------------------------------------------------------------------------
# Vorlagen
# --------------------------------------------------------------------------

def _shorten(text: str, limit: int) -> str:
    text = re.sub(r"^(Show|Ask|Tell) HN:\s*", "", text.strip())
    return text if len(text) <= limit else text[: limit - 1].rstrip(" ,.;:-") + "…"


def _pick(options: list[str], seed: str) -> str:
    """Deterministische Auswahl: gleicher Tag + gleiches Thema = gleiche Vorlage."""
    h = int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16)
    return options[h % len(options)]


def _facts(topic: Topic) -> dict:
    ents = topic.sorted_entries
    news = [e for e in ents if e.kind == "news"]
    repos = [e for e in ents if e.kind == "repo"]
    lead = ents[0]
    d = topic.definition
    source_names = {"hackernews": "Hacker News", "github": "GitHub"}
    srcs = sorted({source_names.get(e.source, e.source) for e in ents})
    return {
        "topic": topic.name,
        "lead": _shorten(lead.title, 90),
        "second": _shorten(ents[1].title, 90) if len(ents) > 1 else None,
        "third": _shorten(ents[2].title, 90) if len(ents) > 2 else None,
        "repo": repos[0].title if repos else None,
        "repo_stars": repos[0].stars_week if repos else 0,
        "comments": sum(e.comments for e in news),
        "points": sum(e.points for e in news),
        "count": len(ents),
        "sources": " und ".join([", ".join(srcs[:-1]), srcs[-1]]) if len(srcs) > 1 else srcs[0],
        "angle": d.angle if d else f"was hinter „{topic.name}“ steckt",
        "audience": d.audience if d else "KI-Interessierte",
    }


def _buzz(f: dict) -> str:
    parts = [f"{f['count']} Beiträge"]
    if f["points"]:
        parts.append(f"{f['points']:,} Punkte".replace(",", "."))
    if f["comments"]:
        parts.append(f"{f['comments']:,} Kommentare".replace(",", "."))
    if f["repo_stars"]:
        parts.append(f"{f['repo_stars']:,} neue GitHub-Sterne".replace(",", "."))
    return ", ".join(parts)


def idea_short(f: dict, seed: str) -> str:
    hook = _pick([
        f"„{f['topic']}“ ist heute das Thema, über das alle reden. Hier ist der Grund in 30 Sekunden.",
        f"Das hast du heute über {f['topic']} verpasst.",
        f"Eine Schlagzeile, {f['comments'] or 'viele'} Kommentare: Warum {f['topic']} gerade explodiert.",
        f"Stopp. Wenn du {f['audience'].split(' und ')[0]} bist, musst du das zu {f['topic']} wissen.",
    ], seed + "short-hook")
    lines = [
        f"Hook: {hook}",
        f"Inhalt: Die Schlagzeile „{f['lead']}“ in einem Satz erklären, dann zeigen, {f['angle']}.",
    ]
    if f["repo"]:
        lines.append(f"Beweis im Bild: das Repository {f['repo']} mit {f['repo_stars']:,} neuen Sternen diese Woche.".replace(",", "."))
    else:
        lines.append(f"Beweis im Bild: Screenshot der Diskussion ({_buzz(f)}).")
    lines.append(_pick([
        "Schluss: „Würdest du das nutzen? Schreib’s in die Kommentare.“",
        "Schluss: „Folgen, wenn du morgen das nächste KI-Thema in 30 Sekunden willst.“",
        "Schluss: Eine klare Meinung in einem Satz, dann Frage an die Zuschauer.",
    ], seed + "short-cta"))
    return "\n".join(lines)


def idea_carousel(f: dict, seed: str) -> str:
    title = _pick([
        f"{f['topic']}: Was diese Woche wirklich passiert ist",
        f"5 Dinge, die du über {f['topic']} jetzt wissen musst",
        f"{f['topic']} erklärt – in 7 Folien",
        f"Hype oder echt? {f['topic']} im Faktencheck",
    ], seed + "carousel-title")
    slides = [
        f"Titel: {title}",
        f"Folie 2: Die Schlagzeile – „{f['lead']}“",
        f"Folie 3: Warum gerade jetzt? {_buzz(f)} (Quellen: {f['sources']})",
    ]
    if f["second"]:
        slides.append(f"Folie 4: Zweiter Blickwinkel – „{f['second']}“")
    else:
        slides.append("Folie 4: Die wichtigsten Begriffe einfach erklärt")
    if f["repo"]:
        slides.append(f"Folie 5: Selbst ausprobieren – {f['repo']} auf GitHub")
    else:
        slides.append("Folie 5: Was du heute schon damit machen kannst (ein konkretes Beispiel)")
    slides += [
        f"Folie 6: Einordnung – {f['angle']}",
        "Folie 7: Deine Meinung + „Speichern für später“",
    ]
    return "\n".join(slides)


def idea_long(f: dict, seed: str) -> str:
    title = _pick([
        f"{f['topic']} verstehen: Was hinter dem Hype steckt",
        f"Ich habe mir {f['topic']} genau angesehen – das ist mein Fazit",
        f"{f['topic']}: Die ganze Geschichte, einfach erklärt",
        f"Warum gerade alle über {f['topic']} reden (und was du daraus machst)",
    ], seed + "long-title")
    parts = [
        f"Titel: {title} (10–15 Min.)",
        f"1. Einstieg (0–1 Min.): „{f['lead']}“ – warum die Community gerade darüber diskutiert ({_buzz(f)}).",
        f"2. Hintergrund (1–4 Min.): Wie es dazu kam und welche Begriffe man kennen muss.",
    ]
    if f["second"]:
        parts.append(f"3. Die Debatte (4–7 Min.): Was in den Kommentaren steht, dazu „{f['second']}“.")
    else:
        parts.append("3. Die Debatte (4–7 Min.): Die stärksten Pro- und Contra-Argumente aus den Kommentaren.")
    if f["repo"]:
        parts.append(f"4. Praxis-Demo (7–11 Min.): {f['repo']} live ausprobieren und zeigen, was es kann.")
    else:
        parts.append("4. Praxis (7–11 Min.): Ein konkretes Beispiel durchspielen, Schritt für Schritt.")
    parts += [
        f"5. Einordnung (11–13 Min.): {f['angle'][0].upper() + f['angle'][1:]}.",
        f"6. Fazit (13–15 Min.): Was {f['audience']} jetzt tun sollten, plus Frage an die Community.",
    ]
    return "\n".join(parts)


def template_ideas(topics: list[Topic], day: str) -> list[dict]:
    out = []
    for t in topics:
        f = _facts(t)
        seed = f"{day}|{t.name}|"
        out.append({
            "topic": _shorten(t.name, 40),
            "short": idea_short(f, seed),
            "carousel": idea_carousel(f, seed),
            "long_video": idea_long(f, seed),
        })
    return out


# --------------------------------------------------------------------------
# Optional: Claude schreibt die Ideen
# --------------------------------------------------------------------------
# Standardmäßig AUS. Aktiv nur, wenn IDEAS_ENGINE=claude gesetzt ist und
# ANTHROPIC_API_KEY vorhanden ist (z. B. als GitHub-Secret). Bei jedem Fehler
# fällt das Skript auf die Vorlagen zurück, die Datei wird trotzdem geschrieben.

CLAUDE_MODEL = os.environ.get("IDEAS_MODEL", "claude-opus-5-5")

_IDEA_SCHEMA = {
    "type": "object",
    "properties": {
        "topics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "short": {"type": "string"},
                    "carousel": {"type": "string"},
                    "long_video": {"type": "string"},
                },
                "required": ["topic", "short", "carousel", "long_video"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["topics"],
    "additionalProperties": False,
}

_CLAUDE_PROMPT = """Du schreibst Content-Ideen auf Deutsch für einen Creator, der über KI berichtet.
Unten stehen die fünf heißesten KI-Themen von heute mit den Schlagzeilen und Repositories, aus denen sie stammen.

Schreibe für jedes Thema, in derselben Reihenfolge:
- short: Idee für ein 30-60-Sekunden-Video. Zeilen „Hook: …“, „Inhalt: …“, „Beweis im Bild: …“, „Schluss: …“.
- carousel: Karussell mit 6-8 Folien, je eine Zeile („Titel: …“, „Folie 2: …“ usw.).
- long_video: Video von 10-15 Minuten. Erste Zeile „Titel: … (10–15 Min.)“, danach nummerierte Kapitel mit Minutenangabe.

Beziehe dich konkret auf die Schlagzeilen und Repositories. Erfinde keine Fakten, Zahlen oder Zitate,
die nicht unten stehen. Kurze Sätze, du-Form, kein Clickbait ohne Substanz.
„topic“ ist der Themenname, höchstens 40 Zeichen; du darfst ihn präziser formulieren.
Trenne die Zeilen innerhalb eines Feldes mit \\n.

Themen:
{topics}
"""


def _claude_topic_brief(topics: list[Topic]) -> str:
    blocks = []
    for i, t in enumerate(topics, 1):
        lines = [f"{i}. {t.name}"]
        for e in t.sorted_entries[:6]:
            if e.kind == "repo":
                lines.append(f"   - GitHub-Repo {e.title}: {e.text.strip()} ({e.stars_week} neue Sterne diese Woche)")
            else:
                lines.append(f"   - {e.source}: „{e.title}“ ({e.points} Punkte, {e.comments} Kommentare)")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def claude_ideas(topics: list[Topic]) -> list[dict]:
    import anthropic  # nur im Claude-Modus nötig: pip install anthropic

    client = anthropic.Anthropic()
    response = client.beta.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": _IDEA_SCHEMA}},
        messages=[{"role": "user", "content": _CLAUDE_PROMPT.format(topics=_claude_topic_brief(topics))}],
    )
    if response.stop_reason != "end_turn":
        raise RuntimeError(f"Claude hat nicht normal beendet (stop_reason={response.stop_reason})")
    text = next(b.text for b in response.content if b.type == "text")
    ideas = json.loads(text)["topics"]
    if len(ideas) != len(topics):
        raise RuntimeError(f"Claude lieferte {len(ideas)} statt {len(topics)} Themen")
    for idea in ideas:
        idea["topic"] = _shorten(idea["topic"], 40)
    return ideas


def use_claude() -> bool:
    return os.environ.get("IDEAS_ENGINE", "").lower() == "claude" and bool(os.environ.get("ANTHROPIC_API_KEY"))


# --------------------------------------------------------------------------
# Ausgabe
# --------------------------------------------------------------------------

def build_output(news: list[Entry], repos: list[Entry], now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    entries = news + repos
    if not entries:
        raise RuntimeError("Weder news.json noch github.json enthalten Einträge.")
    score_entries(entries)
    topics = build_topics(entries)
    if not topics:
        raise RuntimeError("Keine Themen gefunden.")

    engine = "template"
    ideas = None
    if use_claude():
        try:
            ideas = claude_ideas(topics)
            engine = "claude"
        except Exception as exc:  # bewusst breit: jeder Fehler -> Vorlagen
            print(f"Claude-Modus fehlgeschlagen, nutze Vorlagen: {exc}", file=sys.stderr)
    if ideas is None:
        ideas = template_ideas(topics, now.strftime("%Y-%m-%d"))

    top = topics[0].raw_heat or 1.0
    out_topics = []
    for t, idea in zip(topics, ideas):
        out_topics.append({
            "topic": idea["topic"],
            "short": idea["short"],
            "carousel": idea["carousel"],
            "long_video": idea["long_video"],
            "score": round(100 * t.raw_heat / top),
            "sources": [e.link for e in t.sorted_entries[:MAX_SOURCES_PER_TOPIC] if e.link],
            "mentions": len(t.entries),
        })
    return {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "engine": engine,
        "topics": out_topics,
    }


def write_atomic(path: Path, data: dict) -> None:
    """Erst in eine Temp-Datei schreiben, dann umbenennen (Datenvertrag)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".ideas-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Content-Ideen aus den Top-KI-Themen erzeugen.")
    ap.add_argument("--news", type=Path, default=DEFAULT_NEWS)
    ap.add_argument("--github", type=Path, default=DEFAULT_GITHUB)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    try:
        result = build_output(load_news(args.news), load_github(args.github))
    except Exception as exc:
        print(f"Fehler: {exc}. {args.out} bleibt unverändert.", file=sys.stderr)
        return 1
    write_atomic(args.out, result)
    print(f"{len(result['topics'])} Themen nach {args.out} geschrieben (Modus: {result['engine']}).")
    for t in result["topics"]:
        print(f"  {t['score']:>3}  {t['topic']}  ({t['mentions']} Beiträge)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
