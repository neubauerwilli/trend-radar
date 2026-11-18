# trend-radar
KI-Trend-Radar: Beispiel für Claude Projects

Tägliches Dashboard mit den heißesten KI-Themen aus Hacker News, r/ClaudeAI, r/artificial
und den GitHub-Trends der Woche, plus Content-Ideen für die fünf größten Themen.

## Aufbau

| Pfad | Inhalt |
|---|---|
| `site/` | Das Dashboard (statisches HTML/CSS/JS, keine Abhängigkeiten) |
| `data/` | `news.json`, `github.json`, `ideas.json` (bis die Skripte laufen: Beispieldaten) |
| `scripts/` | `news.py`, `github_trends.py`, `ideas.py` erzeugen die Daten |
| `docs/data-contract.md` | Verbindliches Format der drei JSON-Dateien |
| `.github/workflows/update.yml` | Tägliche Aktualisierung und Deployment auf GitHub Pages |

## Einmalige Einrichtung

1. Repository **Settings → Pages → Build and deployment → Source: „GitHub Actions“** wählen.
2. Unter **Actions → Trend-Radar aktualisieren → Run workflow** einmal manuell starten.

Danach ist das Dashboard unter `https://<user>.github.io/trend-radar/` erreichbar.

## Zeitplan

Der Workflow startet täglich um 6:30 Uhr Wiener Zeit (Sommer: 04:30 UTC, Winter: 05:30 UTC),
damit die Daten trotz möglicher Verzögerungen bei geplanten GitHub-Läufen um 7 Uhr bereitstehen.
Beide UTC-Termine sind eingetragen; der Workflow prüft per `TZ=Europe/Vienna`, welcher gerade gilt,
und beendet den anderen sofort. Jeder Push auf `main`, der `site/` oder `data/` ändert, deployt ebenfalls neu.

## Lokal ansehen

```bash
python3 -m http.server 8000
# dann http://localhost:8000/site/ öffnen
```
