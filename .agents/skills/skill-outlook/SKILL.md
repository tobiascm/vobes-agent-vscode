---
name: skill-outlook
description: "Outlook COM Skill: Mails suchen (freie Suche, Thread-Sicht, verwandte Mails), einzelne Mail vollstaendig lesen. Trigger: Mail suchen Outlook, verwandte Mails, Thread-Mails, Mail-Kontext, wer hat noch ueber X geschrieben, Outlook Suche, Mail vollstaendig lesen, Mail-Body anzeigen, alle Empfaenger, Mail nachladen."
---

# Skill: Outlook

Outlook-Skill ueber **Outlook COM** (lokales Postfach).
Deckt Suche, Thread-Sicht, verwandte Mails und vollstaendiges Lesen einzelner Mails ab.

Script: `.agents/skills/skill-outlook/scripts/outlook_search_tools.py`

Adress-Cache: `.agents/skills/skill-outlook/scripts/outlook_address_cache.py`

## Wann verwenden?

- User sucht **Mails zu einem Thema** im lokalen Outlook
- User moechte den **Thread** einer Mail sehen
- User moechte **verwandte Mails** ausserhalb des Threads finden
- User fragt: **wer hat noch ueber X geschrieben**, **Mail-Kontext erweitern**
- User moechte den **vollstaendigen Inhalt** einer Mail sehen (Body, alle To/Cc)
- User hat eine **Entry-ID** und will die Mail nachladen

## Wann NICHT verwenden?

| Aufgabe | Stattdessen |
|---------|-------------|
| Mails per Graph API suchen | `$skill-m365-copilot-mail-search` |
| Dateien in SharePoint suchen | `$skill-m365-copilot-file-search` |

## Voraussetzungen

- **Outlook** muss lokal installiert und geoeffnet sein (COM-Zugriff)
- Fuer Thread/verwandte Mails: **Entry-ID** und optional **Store-ID** der Seed-Mail
- Fuer Namens-/Adressfilter nutzt der Skill zusaetzlich einen lokalen Adress-Cache unter `userdata/outlook/address_cache.db`

## Adress-Cache

- Bei `--sender` und `--recipient` wird **zuerst** der lokale Address-Cache befragt
- Ist der Cache leer, wird automatisch ein Vollaufbau gestartet
- Gibt es einen Cache-Miss und der letzte erfolgreiche Lauf ist **aelter als 1 Tag**, wird automatisch ein inkrementeller Update-Lauf gestartet
- Erst wenn danach weiter kein Treffer vorliegt, bleibt die Suche bei den normalen Outlook-Filtern

Manueller Lauf:

```bash
python .agents/skills/skill-outlook/scripts/outlook_address_cache.py
```

Kompletter Neuaufbau:

```bash
python .agents/skills/skill-outlook/scripts/outlook_address_cache.py --force-full
```

Nur letzte 7 Tage:

```bash
python .agents/skills/skill-outlook/scripts/outlook_address_cache.py --days 7
```

## CLI-Referenz

### search — Hintergrundsuche (Standard)

```bash
python .agents/skills/skill-outlook/scripts/outlook_search_tools.py search \
  --keyword "Bordnetz" \
  --keyword "Spezifikation" \
  --sender "max.mustermann@volkswagen.de" \
  --search-days 90 \
  --max-results 25
```

| Parameter | Beschreibung |
|-----------|-------------|
| `--query` | Freitext-Suche |
| `--keyword` | Suchbegriffe (mehrfach moeglich, AND-verknuepft) |
| `--sender` | Absender-Filter (mehrfach moeglich) |
| `--recipient` | Empfaenger-Filter |
| `--subject-must` | Pflicht-Begriffe im Betreff |
| `--exclude-term` | Ausschlussbegriffe |
| `--search-days` | Zeitraum in Tagen (Default: 90) |
| `--max-results` | Max. Treffer (Default: 25) |
| `--search-ui` | Explorer/UI-Suchpfad statt Hintergrundsuche (Opt-in) |

Mindestens `--query`, `--keyword`, `--sender` oder `--subject-must` muss angegeben werden.

### read-email — Einzelne Mail vollstaendig laden

```bash
python .agents/skills/skill-outlook/scripts/outlook_search_tools.py read-email \
  --entry-id "ENTRY_ID" --store-id "STORE_ID"
```

| Parameter | Beschreibung |
|-----------|-------------|
| `--entry-id` | Outlook EntryID der Mail (Pflicht) |
| `--store-id` | Optionale Outlook StoreID |
| `--no-body` | Body nicht mit ausgeben (nur Metadaten) |

### inspect-selection — Aktuell markierte Mail inspizieren

```bash
python .agents/skills/skill-outlook/scripts/outlook_search_tools.py inspect-selection
```

Liefert EntryID, StoreID, Folder-Pfad und Store-Details der aktuell in Outlook markierten Mail.

## Workflow

### 1. Freie Mailsuche

Direkt `search` aufrufen:

```bash
python .agents/skills/skill-outlook/scripts/outlook_search_tools.py search \
  --keyword "Bordnetz" --sender "max@volkswagen.de" --search-days 90
```

### 2. Mail vollstaendig lesen

```bash
python .agents/skills/skill-outlook/scripts/outlook_search_tools.py read-email \
  --entry-id "ENTRY_ID_HIER"
```

Liefert den **kompletten Body** und **vollstaendige To/Cc-Listen** (nicht gekuerzt).

Ohne Body (nur Metadaten):
```bash
python .agents/skills/skill-outlook/scripts/outlook_search_tools.py read-email \
  --entry-id "ENTRY_ID_HIER" --no-body
```

### 3. Thread-Mails finden (Agent-Orchestrierung)

Ziel: Alle Mails im selben Conversation-Thread wie eine bekannte Seed-Mail.

**Schritt A** — Seed-Mail laden und Metadaten extrahieren:

```bash
python .agents/skills/skill-outlook/scripts/outlook_search_tools.py read-email \
  --entry-id "ENTRY_ID" --store-id "STORE_ID"
```

Aus der Ausgabe extrahieren: `subject`, `conversation_id`, `sender`, `to_recipients`.

**Schritt B** — Betreff-Kernbegriffe ableiten:

Praefixe entfernen (`Re:`, `Aw:`, `Wg:`, `Fwd:`, `WG:`, `AW:`), dann die ersten 3-5 Kernwoerter als `--subject-must` verwenden.

**Schritt C** — Suche ausfuehren:

```bash
python .agents/skills/skill-outlook/scripts/outlook_search_tools.py search \
  --subject-must "Kernbegriff1" \
  --subject-must "Kernbegriff2" \
  --search-days 180 \
  --max-results 50
```

**Schritt D** — Ergebnisse filtern:

Aus den Treffern nur diejenigen behalten, deren `conversation_id` mit der Seed-Mail uebereinstimmt. Ergebnis chronologisch sortiert ausgeben.

### 4. Verwandte Mails finden (Agent-Orchestrierung)

Ziel: Thematisch aehnliche Mails **ausserhalb** des Threads.

**Schritt A** — Seed-Mail laden (wie oben, falls nicht schon geschehen).

**Schritt B** — Suche mit Themen-Keywords:

```bash
python .agents/skills/skill-outlook/scripts/outlook_search_tools.py search \
  --keyword "Kernbegriff aus Subject" \
  --sender "seed.sender@volkswagen.de" \
  --search-days 180 \
  --max-results 30
```

Optional `--recipient` ergaenzen, falls die Teilnehmer-Ueberlappung relevant ist.

**Schritt C** — Ergebnisse bewerten und filtern:

- Treffer mit gleicher `conversation_id` wie Seed aussortieren (die sind Thread, nicht verwandt)
- Verbleibende Treffer bewerten nach:
  - Betreff-Aehnlichkeit (gemeinsame Kernwoerter)
  - Teilnehmer-Ueberlappung (gleiche Sender/Empfaenger)
  - Domain-Match (gleiche Absender-Domain)
- Treffer mit hoher Relevanz zuerst ausgeben

## Ausgabeformat

### search

```json
{
  "mode": "search",
  "engine": "advanced_search",
  "query": { "keywords": [...], "sender": [...], ... },
  "stores": [{ "store_name": "...", "indexed": true, ... }],
  "matches": [
    {
      "reasons": ["keyword hits: ...", "advanced search matched"],
      "email": {
        "entry_id": "...",
        "store_id": "...",
        "subject": "...",
        "sender": "...",
        "to_recipients": ["... max 10 ..."],
        "cc_recipients": ["... max 10 ..."],
        "received": "2026-04-01T10:30:00+00:00",
        "conversation_id": "...",
        "body_preview_lines": ["... max 10 Zeilen ..."],
        "body_has_more": true
      }
    }
  ],
  "warnings": []
}
```

### read-email

| Feld | Beschreibung |
|------|-------------|
| `entry_id` | Eindeutige Mail-ID |
| `store_id` | Outlook-Store |
| `subject` | Betreff |
| `sender` | Absender-Adresse |
| `sender_name` | Absender-Name |
| `to_recipients` | Vollstaendige To-Liste |
| `cc_recipients` | Vollstaendige Cc-Liste |
| `received` | Empfangszeitpunkt (ISO) |
| `conversation_id` | Outlook Conversation-ID |
| `has_attachments` | Boolean |
| `body_preview_lines` | Erste 10 Zeilen des Body |
| `body_has_more` | Ob Body laenger als 10 Zeilen |
| `body` | Kompletter Body (nur ohne `--no-body`) |

## Typischer Ablauf

1. **Suche starten** → `search` mit passenden Filtern
2. **Ergebnisse sichten** → Kompakte Ausgabe mit Metadaten und Preview
3. **Details nachladen** → `read-email` fuer vollstaendigen Body einer bestimmten Mail
4. **Thread/Kontext erweitern** → Seed-Mail per `read-email` laden, dann erneut `search` mit extrahierten Metadaten

## Fehlerbehandlung

| Problem | Loesung |
|---------|---------|
| `Outlook not running` | Outlook starten |
| `Item not found` | Entry-ID pruefen, ggf. mit Store-ID versuchen |
| Keine Treffer | Suchbegriffe anpassen, `--search-days` erhoehen |
| Timeout bei AdvancedSearch | Outlook ist ueberlastet — kurz warten und erneut versuchen |
| `search requires at least one positive filter` | Mindestens `--keyword` oder `--sender` angeben |
| Leerer Body | Mail hat keinen Text-Body (evtl. nur HTML) |

## Hinweis: Inline-Bilder

Outlook COM extrahiert **keine Inline-Bilder** (cid:-Bilder im HTML-Body).
Fuer Mails mit Inline-Bildern (z.B. Screenshots, Diagramme im Mailtext) besser
`$skill-m365-copilot-mail-search` verwenden — dort werden Inline-Bilder automatisch
per LLM beschrieben und die Beschreibung direkt in den Mail-Body eingebettet.
