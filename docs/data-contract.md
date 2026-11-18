# Datenvertrag: KI-Trend-Radar

Das Dashboard (`site/`) liest drei JSON-Dateien aus `data/`. Jedes Skript in `scripts/`
schreibt genau eine davon. Diese Datei ist die verbindliche Schnittstelle zwischen
Skripten und Dashboard. Änderungen bitte hier zuerst eintragen.

## Allgemeine Regeln

- Kodierung UTF-8, gültiges JSON, Einrückung egal.
- Jede Datei ist ein Objekt mit `generated_at` (ISO 8601 in UTC, z. B. `"2026-11-19T05:31:12Z"`)
  und genau einer Liste (`items`, `repos` bzw. `topics`).
- Ganzzahlen als JSON-Zahlen, nicht als Strings.
- Pflichtfelder sind immer vorhanden. Unbekannte Werte: `null` (nur wo erlaubt).
- Zusätzliche Felder sind erlaubt, das Dashboard ignoriert sie.
- Schlägt ein Skript fehl, darf es die bestehende Datei **nicht** überschreiben
  (erst in eine temporäre Datei schreiben, dann umbenennen). Das Dashboard zeigt
  dann die Daten vom Vortag mit einem Hinweis an.
- Nur öffentliche Endpunkte, keine Logins, keine API-Schlüssel.
- Die Skripte laufen ohne Argumente vom Repo-Wurzelverzeichnis aus:
  `python scripts/news.py`, `python scripts/github_trends.py`, `python scripts/ideas.py`
  (in dieser Reihenfolge). Python 3.12. Zusätzliche Pakete in `requirements.txt`
  eintragen; der Workflow installiert sie automatisch.

## data/news.json (scripts/news.py)

```json
{
  "generated_at": "2026-11-19T05:31:12Z",
  "items": [
    {
      "source": "hackernews",
      "title": "Show HN: Ein Agent, der ...",
      "url": "https://example.com/artikel",
      "points": 412,
      "comments": 187,
      "discussion_url": "https://news.ycombinator.com/item?id=12345",
      "created_at": "2026-11-18T19:02:00Z"
    }
  ]
}
```

| Feld | Typ | Pflicht | Bedeutung |
|---|---|---|---|
| `source` | string | ja | Genau einer von `"hackernews"`, `"r/ClaudeAI"`, `"r/artificial"` |
| `title` | string | ja | Titel des Beitrags |
| `url` | string | ja | Ziel-Link (bei Text-Posts der Link zur Diskussion) |
| `points` | int | ja | HN-Punkte bzw. Reddit-Score |
| `comments` | int | ja | Anzahl Kommentare |
| `discussion_url` | string \| null | nein | Link zur HN- bzw. Reddit-Diskussion |
| `created_at` | string \| null | nein | Zeitpunkt des Beitrags, ISO 8601 UTC |

Umfang: bis zu 30 Einträge pro Quelle, nur KI-relevante Beiträge (bei Hacker News gefiltert).
Sortierung egal, das Dashboard sortiert nach `points`.

## data/github.json (scripts/github_trends.py)

```json
{
  "generated_at": "2026-11-19T05:32:40Z",
  "repos": [
    {
      "name": "owner/repo",
      "url": "https://github.com/owner/repo",
      "description": "Kurzbeschreibung aus GitHub",
      "stars_week": 3120,
      "language": "Python",
      "stars_total": 18450
    }
  ]
}
```

| Feld | Typ | Pflicht | Bedeutung |
|---|---|---|---|
| `name` | string | ja | `owner/repo` |
| `url` | string | ja | Link zum Repository |
| `description` | string \| null | ja | Beschreibung, `null` wenn leer |
| `stars_week` | int | ja | Neue Sterne in den letzten 7 Tagen |
| `language` | string \| null | ja | Hauptsprache, `null` wenn unbekannt |
| `stars_total` | int \| null | nein | Sterne insgesamt |

Umfang: genau die 10 KI-Repositories mit den meisten neuen Sternen der Woche,
absteigend nach `stars_week` sortiert.

## data/ideas.json (scripts/ideas.py)

Liest `data/news.json` und `data/github.json`, bildet die fünf größten Themen und
schreibt je drei Content-Ideen.

```json
{
  "generated_at": "2026-11-19T05:33:05Z",
  "topics": [
    {
      "topic": "Claude Code Agents",
      "short": "Hook + Inhalt für ein 30-60-Sekunden-Video",
      "carousel": "Titel und Folienablauf für ein Karussell",
      "long_video": "Titel und Gliederung für ein 10-15-Minuten-Video",
      "score": 1830,
      "sources": ["https://news.ycombinator.com/item?id=12345"]
    }
  ]
}
```

| Feld | Typ | Pflicht | Bedeutung |
|---|---|---|---|
| `topic` | string | ja | Name des Themas, kurz (max. ca. 40 Zeichen) |
| `short` | string | ja | Idee für einen Short |
| `carousel` | string | ja | Idee für ein Karussell |
| `long_video` | string | ja | Idee für ein langes Video |
| `score` | int \| null | nein | Wie heiß das Thema ist (z. B. Summe aus Punkten und Kommentaren) |
| `sources` | string[] | nein | Links zu den Beiträgen/Repos, aus denen das Thema stammt |

Umfang: genau 5 Themen, absteigend nach Relevanz. Die Ideentexte dürfen Zeilenumbrüche
(`\n`) enthalten, das Dashboard zeigt sie als Absätze an.

## Beispieldaten

Bis die echten Skripte laufen, liegen Beispieldaten in `data/`. Sie haben
`"sample": true` auf oberster Ebene; das Dashboard zeigt dann ein Badge „Beispieldaten“.
Echte Skripte lassen das Feld weg.
