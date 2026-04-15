---
name: skill-orga-ekek1
description: "Zentrale Referenz fuer EKEK/1-Orga, Namen, Rollen, Gremien, wichtige Websites, VOBES-Regeltermine und relevante Confluence-Seiten. Pflicht-Nachschlagequelle fuer EKEK/1- und VOBES-Mailfaelle mit Personen-, Meeting- oder Seitenkontext."
---

# Skill: Orga EKEK/1

Kuratierter Referenzskill fuer den organisatorischen Alltag in `EKEK/1`.

Nutze diesen Skill immer dann, wenn der Agent Namen, Rollen, Gremien, wichtige Websites, Standard-Confluence-Seiten oder EKEK/1-Orga-Kontext sauber einordnen muss.

## Wann verwenden?

- Der User fragt nach Personen, Rollen, Zustaendigkeiten oder Einordnung innerhalb `EKEK/1`, `EKEK`, `EKE` oder `EK`
- Der User nennt Gremien oder Regeltermine und der Agent muss sie zuordnen
- Der User braucht die Standard-Websites oder Confluence-Seiten fuer `EKEK/1` oder `VOBES`
- Ein Mail-Fall enthaelt EKEK/1-, VOBES- oder Regeltermin-Kontext und Namen oder Seiten muessen vor der Analyse eingeordnet werden
- Der Agent braucht schnellen organisatorischen Kontext, ohne erst in mehreren Skills oder Confluence-Seiten zu suchen

## Wann NICHT verwenden?

| Aufgabe | Stattdessen verwenden |
|---|---|
| Fachliche Bordnetz-, VOBES-, Prozess- oder Datenmodellfrage | `$skill-knowledge-bordnetz-vobes` |
| Personensuche ausserhalb des hier gepflegten EKEK/1-Kontexts | `$skill-personensuche-groupfind` |
| Confluence/Jira lesen oder schreiben | `mcp-atlassian` plus passende Skills |
| Allgemeine Standardlinks, Dashboards, HowTos oder Zusatzlinks ohne konkreten EKEK/1-Orga-Bezug | `$skill-important-pages-links-and-urls` |

## Pflichtregel fuer Mail-Agent

Wenn `$skill-m365-mail-agent` einen Fall im `EKEK/1`-, `EKEK`- oder `VOBES`-Umfeld bearbeitet und dabei
- Personen,
- Rollen,
- Gremien,
- Termine,
- Websites,
- Confluence-Seiten oder
- organisatorische Zustaendigkeiten

interpretiert werden muessen, ist **dieser Skill zuerst zu laden**.

Der Mail-Agent darf Namen, Rollen und Regeltermine in diesem Kontext nicht frei interpretieren, wenn diese Referenz hier bereits gepflegt ist.

## Pflichtquellen im Skill-Ordner

Der Agent liest diese Dateien in genau dieser Reihenfolge:

1. `orga.md`
2. `gremien.md`
3. `links-und-termine.md`

### Leseregeln

- `orga.md` ist die primaere Quelle fuer Personen, Rollen, Hierarchie und Delegationskontext.
- `gremien.md` ist die primaere Quelle fuer interne Gremien und deren organisatorische Einordnung.
- `links-und-termine.md` ist die primaere Quelle fuer Websites, Confluence-Seiten, Standardlinks und VOBES-Regeltermine.
- Wenn dieselbe Information mehrfach vorkommt, gilt die spezifischere und kuratierte Darstellung in diesen drei Dateien vor allgemeinen Repo-Dokumenten.

## Standard-Workflow

### 1. Kontext klassifizieren

Pruefe zuerst, ob die Frage oder Mail eines der folgenden Muster enthaelt:

- Person oder Name aus `EKEK/1`, `EKEK`, `EKE`
- Gremium oder Regeltermin
- Hinweis auf bekannte Confluence-Seite oder Standard-Website
- Bitte um Einordnung von Rollen, Assistenzen, Vertretungen oder Delegation

Wenn ja, diesen Skill verwenden.

### 2. Referenzdaten lesen

- Fuer Personen- und Rollenfragen: `orga.md`
- Fuer Gremien- und Regelterminfragen: `gremien.md` und danach `links-und-termine.md`
- Fuer Websites und Seiten: `links-und-termine.md`

### 3. Antwort oder Folgeaktion vorbereiten

- Namen und Rollen kurz, konkret und ohne Spekulation einordnen
- Bei Terminen den kanonischen Seitennamen und die Standardseite nennen
- Bei Mail-Faellen die gewonnene Einordnung als Kontext fuer die Analyse verwenden

### 4. Nur bei Luecken eskalieren

Wenn die benoetigte Information in diesem Skill **nicht** gepflegt ist:

- fuer allgemeine Standardlinks, Dashboards, HowTos und Zusatzseiten: `$skill-important-pages-links-and-urls`
- fuer fachliche VOBES-Inhalte: `$skill-knowledge-bordnetz-vobes`
- fuer Personensuche ausserhalb des hier kuratierten Kreises: `$skill-personensuche-groupfind`

## Antwortstil

- Kurz und referenznah antworten
- Keine neuen Rollen, Zustaendigkeiten oder Meetingzwecke erfinden
- Unsicherheit explizit benennen, wenn eine Information hier nicht gepflegt ist

## Pflegehinweise

- Dieser Skill ist die zentrale Nachschlagequelle fuer `EKEK/1`-Orga-Infos.
- Neue Standardseiten, Websites oder wiederkehrende Termine zuerst hier eintragen.
- Allgemeine VOBES-Standardlinks duerfen weiterhin in `skill-important-pages-links-and-urls` liegen; fuer `EKEK/1`-relevante Nutzung soll dieser Skill zuerst gelesen werden.
- Fuer ergaenzende Dashboard-, HowTo- oder Zusatzlinks ist `skill-important-pages-links-and-urls` die naechste Referenz nach diesem Skill.
