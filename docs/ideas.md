# Content-Ideen (`scripts/ideas.py`)

Läuft als drittes Skript im Morgen-Lauf, nach `news.py` und `github_trends.py`:

```bash
python scripts/ideas.py
```

Liest `data/news.json` und `data/github.json` und schreibt `data/ideas.json` im Format aus
[`docs/data-contract.md`](data-contract.md). Kein Paket, kein Login, kein API-Schlüssel nötig.

## So entstehen die fünf Themen

1. **Hitze pro Beitrag.** Jede Quelle wird für sich bewertet, weil Hacker-News-Punkte,
   Reddit-Upvotes und GitHub-Sterne nicht vergleichbar sind. Ein Beitrag bekommt einen Wert
   zwischen 0 und 1: 60 % Punkte, 40 % Kommentare, jeweils logarithmisch gedämpft und auf den
   stärksten Beitrag derselben Quelle bezogen. Bei Repositories zählen die neuen Sterne der Woche.
2. **Bündeln.** Jeder Beitrag kommt in genau ein Thema aus einem festen Katalog
   (z. B. „Claude & Anthropic“, „KI-Agenten“, „MCP & Tool-Anbindung“, „Lokale KI“). Entscheidend
   sind Schlagwörter im Titel bzw. im Repo-Namen und der Beschreibung. Beiträge aus r/ClaudeAI
   ohne Treffer landen bei „Claude & Anthropic“. Taucht ein unbekanntes Schlagwort (etwa ein neuer
   Produktname) in mindestens zwei übrigen Beiträgen auf, wird daraus ein eigenes Thema.
3. **Rangfolge.** Themen-Hitze = Summe der Beitrags-Hitze, mit 15 % Bonus je zusätzlicher Quelle
   (ein Thema, das auf Hacker News, Reddit und GitHub gleichzeitig läuft, ist heißer).
   `score` im JSON ist diese Hitze relativ zum Spitzenthema (Platz 1 = 100).
4. **Auffüllen.** Gibt es weniger als fünf Bündel, werden die stärksten übrigen Einzelbeiträge
   zu eigenen Themen. Nur wenn insgesamt weniger als fünf Beiträge vorliegen, enthält die Datei
   weniger als fünf Themen.

Den Katalog pflegst du in `CATALOG` oben in `scripts/ideas.py`: Name, Suchmuster und ein
Blickwinkel, der in die Ideen einfließt.

## So entstehen die Ideen (Vorlagen-Modus, Standard)

Für jedes Thema werden echte Schlagzeilen, Zahlen und, falls vorhanden, das passende
Repository in Vorlagen eingesetzt:

- **Short:** Hook, Inhalt, „Beweis im Bild“, Schluss.
- **Karussell:** 7 Folien von der Schlagzeile bis zum Call-to-Action.
- **Langes Video:** Titel und 6 Kapitel mit Minutenangaben für 10–15 Minuten.

Pro Format gibt es mehrere Varianten für Hook und Titel. Welche genommen wird, hängt von
Datum und Thema ab, damit es nicht jeden Tag gleich klingt, ein erneuter Lauf am selben Tag
aber dasselbe Ergebnis liefert.

Das Feld `engine` in `ideas.json` zeigt, welcher Modus gelaufen ist (`template` oder `claude`).
`mentions` ist die Zahl der Beiträge im Thema. Beides sind Zusatzfelder, die das Dashboard
ignorieren darf.

## Claude-Modus (optional, standardmäßig aus)

Die Vorlagen kommen ohne Schlüssel aus, klingen aber zwangsläufig schematisch. Wenn du
bessere, wirklich auf die Schlagzeilen zugeschnittene Ideen willst, kann Claude sie schreiben.
Das ist eine bewusste Ausnahme von „keine API-Schlüssel“ und deshalb nur aktiv, wenn beides gesetzt ist:

| Variable | Wert |
|---|---|
| `IDEAS_ENGINE` | `claude` |
| `ANTHROPIC_API_KEY` | dein Schlüssel, als GitHub-Secret |
| `IDEAS_MODEL` | optional, Standard `claude-opus-5-5` |

Zusätzlich muss `anthropic` in `requirements.txt` stehen. Im Workflow sähe das so aus:

```yaml
- run: python scripts/ideas.py
  env:
    IDEAS_ENGINE: claude
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

Themenfindung und `score` bleiben gleich, nur die Texte kommen von Claude. Schlägt der Aufruf
fehl (kein Guthaben, Netzwerk, unerwartete Antwort), schreibt das Skript die Vorlagen-Ideen
und meldet den Fehler im Log. Ein Lauf kostet mit dem Standardmodell grob 5 bis 15 Cent (Schätzung).

## Tests

```bash
python -m unittest discover tests
```

Beispieldaten für die Tests liegen in `tests/fixtures/`.
