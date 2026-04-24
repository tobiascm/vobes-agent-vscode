# Knowledge Record – PowerPoint-Agent in VS Code mit GitHub Copilot

## Zweck
Dieses Dokument hält die zentralen Erkenntnisse aus der Recherche und den Entscheidungen fest, damit das Wissen später schnell wiederverwendet werden kann.

## Kontext
Ziel ist ein Setup, mit dem PowerPoint-Präsentationen auf einem Windows-Rechner aus einer Unternehmensvorlage heraus per Prompt erstellt oder bearbeitet werden können.

Rahmenbedingungen:
- Arbeit konsequent in **VS Code**
- Agent primär **GitHub Copilot**
- PowerPoint lokal installiert auf **Windows**
- Präsentationen sollen aus einer **Corporate-/Unternehmensvorlage** erzeugt und bearbeitet werden
- Fokus auf **möglichst hohe Vorlagentreue**

---

# 1. Kernentscheidung

## Entscheidung
Für den beschriebenen Use Case ist **`trsdn/mcp-server-ppt`** die beste Hauptlösung.

Innerhalb dieser Lösung ist für den täglichen Einsatz mit **VS Code + GitHub Copilot** der Skill **`ppt-cli`** der primäre Modus.

Der Skill **`ppt-mcp`** bleibt zusätzlich sinnvoll, aber eher als ergänzender Pfad für explorative oder stärker chat-orientierte Aufgaben.

## Kurzbegründung
- arbeitet mit **echtem Microsoft PowerPoint über COM**
- dadurch deutlich bessere Eignung für **Unternehmensvorlagen, Layouts, Placeholders, Masters und PowerPoint-nahe Bearbeitung**
- ist explizit auf **Windows + PowerPoint lokal** ausgelegt
- die offizielle Ausrichtung passt gut zu **GitHub Copilot / Coding-Agents**
- `ppt-cli` ist für **skriptartige, agentische, kompakte und wiederholbare** Arbeit der passendste Modus

---

# 2. Wichtigste Abgrenzung

## `trsdn/mcp-server-ppt` vs. `ppt-cli`
Das sind **keine konkurrierenden Produkte**.

`trsdn/mcp-server-ppt` ist das **Gesamtprojekt**.
Darin enthalten sind unter anderem:
- der **MCP-Server**
- die **CLI**
- der Skill **`ppt-cli`**
- der Skill **`ppt-mcp`**

### Praktische Bedeutung
Die eigentliche Architekturentscheidung lautet daher nicht:
- „`mcp-server-ppt` oder `ppt-cli`?“

Sondern:
- **`trsdn/mcp-server-ppt` als Plattform**
- darin **`ppt-cli` als Hauptarbeitsmodus**
- **`ppt-mcp` ergänzend**

---

# 3. Warum COM hier wichtig ist

## COM-basierte Bearbeitung
COM bedeutet hier: Steuerung des **echten installierten PowerPoint** statt nur Manipulation einer `.pptx`-Datei auf XML-/Dateiebene.

### Vorteil für den Use Case
Für Unternehmensvorlagen ist COM besonders wertvoll, weil:
- bestehende **Layouts** zuverlässiger genutzt werden können
- **Placeholders** näher am echten Verhalten von PowerPoint bearbeitet werden
- **Slide Master / Theme / Transitions / Notes / Export** besser abgedeckt sind
- die Gefahr sinkt, dass eine Datei zwar formal korrekt ist, aber visuell oder funktional von der Vorlage abweicht

### Preis dafür
- nur **Windows**
- **PowerPoint muss installiert sein**
- Desktop-/UI-naher Betrieb, also weniger „headless serverartig“

Für den konkreten lokalen Windows-Agenten ist dieser Preis akzeptabel und sogar passend.

---

# 4. Bewertung der wichtigsten Optionen

## A. `trsdn/mcp-server-ppt`
### Stärken
- COM-basiert, arbeitet mit echtem PowerPoint
- sehr gute Passung für **Corporate Templates**
- gute Abdeckung von PowerPoint-spezifischen Funktionen
- sinnvoll für **Agent + VS Code + Copilot**
- `ppt-cli` besonders gut für wiederholbare, skriptartige Arbeitsweise

### Schwächen
- Windows-only
- lokales PowerPoint nötig
- COM-Umgebung ist potenziell fragiler als rein dateibasierte Tools

### Gesamturteil
**Beste Hauptlösung für den aktuellen Use Case.**

---

## B. `anthropics/skills` – `pptx`
### Stärken
- generischer, dateibasierter PPTX-Skill
- gut zum **Lesen, Analysieren, Transformieren** und auch für QA-nahe Workflows
- nicht auf echtes PowerPoint angewiesen

### Schwächen
- arbeitet nicht über das echte PowerPoint-Objektmodell
- für strenge Unternehmensvorlagen tendenziell weniger treu als COM
- eher Ergänzung als Primärlösung für Corporate-Template-Bearbeitung

### Gesamturteil
**Guter Ergänzungsskill**, aber **nicht erste Wahl** als Hauptpfad für das beschriebene Windows-/Corporate-Szenario.

---

## C. Andere COM-basierte PowerPoint-MCPs
### `ykuwai/ppt-mcp`
- technisch interessant
- stark für Live-/WYSIWYG-Steuerung
- wirkte in der Recherche aber reifeseitig noch jünger als `trsdn`

### `socamalo/PPT_MCP_Server`
- eher minimal / experimentell
- kein bevorzugter Kandidat für produktionsnahe Nutzung

### `jenstangen1/pptx-xlsx-mcp`
- interessant als Python-/Hack-Basis
- aber nicht meine erste Wahl für robusten Corporate-Template-Betrieb

### Gesamturteil
**`trsdn` bleibt die stärkste COM-Option für den konkreten Use Case.**

---

# 5. Warum `ppt-cli` besser zu GitHub Copilot passt als `ppt-mcp`

## `ppt-cli`
Geeignet für:
- **Coding-Agents**
- kompakte, klare, wiederholbare Befehlsfolgen
- Batch-Änderungen
- Skript-/Automationsstil
- Repo-zentriertes Arbeiten in VS Code

## `ppt-mcp`
Geeignet für:
- stärker **explorative Chat-Nutzung**
- Tool-Discovery
- offene, unscharfe, dialogorientierte Arbeitsweise

## Bewertung für den konkreten Wunsch
Da der gewünschte Arbeitsstil ist:
- konsequent in VS Code
- mit GitHub Copilot
- PowerPoints per Prompt erstellen und bearbeiten

passt **`ppt-cli` als Hauptmodus besser**.

`ppt-mcp` ist trotzdem nützlich, wenn erst analysiert oder exploriert werden soll.

---

# 6. Empfohlene Zielarchitektur

## Primärarchitektur
1. **VS Code** als zentrale Arbeitsumgebung
2. **GitHub Copilot** als primärer Agent
3. **`trsdn/mcp-server-ppt`** als PowerPoint-Plattform
4. **`ppt-cli`** als Standard-Skill/Arbeitsmodus
5. **Unternehmensvorlage** als feste Grundlage

## Arbeitsprinzip
Der Agent soll möglichst **nicht frei gestalten**, sondern:
- aus einer vorhandenen Vorlage arbeiten
- nur definierte Layouts nutzen
- vorhandene Placeholders gezielt befüllen
- Texte, Bilder, Tabellen, Charts und Notizen kontrolliert einfügen oder ändern
- am Ende eine visuelle und strukturelle Prüfung durchführen

---

# 7. Empfohlene Arbeitsweise für den Agenten

## Grundregel
Der Agent arbeitet **template-first**, nicht design-first.

## Gute Arbeitslogik
1. Vorlage öffnen oder kopieren
2. verfügbare Layouts / Masters / Placeholders analysieren
3. Zielstruktur der Präsentation planen
4. Folien in passender Reihenfolge anlegen oder bestehende ändern
5. Inhalte befüllen
6. abschließend prüfen:
   - Titel vorhanden
   - Bullet-Ebenen korrekt
   - keine abgeschnittenen Texte
   - Bilder nicht verzerrt
   - Corporate-Layout eingehalten
   - Notes / Sections / Export wenn nötig

---

# 8. Sinnvolle Copilot-Instruktionen im Repo

Für das Repo sollten dauerhafte Instruktionen hinterlegt werden.

## Inhaltlich empfohlen
- Nutze für PowerPoint-Aufgaben bevorzugt **`ppt-cli`**
- Arbeite immer aus der **Unternehmensvorlage**
- Verwende nur bekannte **Layouts und Placeholders**
- Vermeide freie Layout-Neugestaltung, wenn nicht ausdrücklich gefordert
- Führe zusammenhängende Änderungen möglichst **gebündelt** aus
- Prüfe die Präsentation vor Abschluss strukturell und visuell
- Änderungslogik zuerst planen, dann ausführen

## Ziel
Damit wird Copilot reproduzierbarer und arbeitet konsistenter mit der Firmenvorlage.

---

# 9. Empfohlene Rollentrennung der Tools

## Hauptwerkzeug
### `trsdn` + `ppt-cli`
Verwendung für:
- neue Präsentation aus Vorlage erzeugen
- Folien hinzufügen/löschen
- Texte ändern
- Bilder/Tabellen/Charts befüllen
- Serienänderungen
- Export / Abschlussbearbeitung

## Ergänzungswerkzeug
### `anthropics/skills` `pptx`
Verwendung für:
- bestehende `.pptx` analysieren
- dateibasierte Transformations- oder Prüfpfade
- zusätzliche QA / Parsing / Dokumentstruktur-Analyse

### Empfehlung
`anthropics/pptx` ist **ergänzend nützlich**, aber **nicht der primäre Bearbeitungspfad**.

---

# 10. Finale Entscheidung

## Hauptempfehlung
**Installiere und nutze `trsdn/mcp-server-ppt` in VS Code.**

## Primärer Skill
**Nutze `ppt-cli` als Standardmodus für GitHub Copilot.**

## Sekundärer Skill
**Lass `ppt-mcp` zusätzlich verfügbar**, aber eher für explorative Sonderfälle.

## Ergänzender Skill
**`anthropics/skills` `pptx` nur ergänzend** für Analyse-/Datei-Workflows.

---

# 11. Kompakte Entscheidungsformel

Wenn das Ziel ist:
- Windows
- VS Code
- GitHub Copilot
- Unternehmensvorlage
- PowerPoints per Prompt erstellen oder ändern

Dann ist die richtige Wahl:

**`trsdn/mcp-server-ppt` + `ppt-cli` als Hauptpfad**

und optional:

**`ppt-mcp` + `anthropics/pptx` als Ergänzung**

---

# 12. Offene nächste Schritte

## Empfohlen
1. `trsdn/mcp-server-ppt` in VS Code installieren
2. Test mit einer echten Unternehmensvorlage machen
3. herausfinden:
   - welche Layouts es gibt
   - welche Placeholders stabil nutzbar sind
   - welche Präsentationsarten regelmäßig erzeugt werden sollen
4. Repo-Custom-Instructions für Copilot hinterlegen
5. einen kleinen Standardworkflow definieren, z. B.:
   - Titel-Folie
   - Agenda
   - 3 Content-Folien
   - Summary-Folie
6. erst danach optional erweitern um:
   - Export
   - Notes
   - Charts
   - wiederverwendbare Prompt-Vorlagen

---

# TL;DR
Für den gewünschten Arbeitsstil ist die beste Kombination:

**`trsdn/mcp-server-ppt` als Plattform + `ppt-cli` als Hauptmodus in VS Code mit GitHub Copilot.**

**`ppt-mcp` bleibt ergänzend nützlich.**

**`anthropics/skills` `pptx` ist ein guter Zusatz für Analyse und dateibasierte Workflows, aber nicht der primäre Weg für Corporate-Template-Bearbeitung auf Windows.**

---

# Umsetzung (Stand 2026-04-24)

## Skill angelegt

- `.agents/skills/skill-powerpoint-ppt-cli/` — SKILL.md, Vorlagen/, scripts/
- Triggers in `AGENTS.md` und `CLAUDE.md` eingetragen
- VS-Code-Tasks `pptcli: help` und `pptcli: list PowerPoint templates` in `.vscode/tasks.json`
- Vorlagen lokal unter `.agents/skills/skill-powerpoint-ppt-cli/Vorlagen/`: `Volkswagen Brand.potx`, `Volkswagen Group.potx`, `Volkswagen Group tcm.potx`

## Installation gewählter Weg (kein Admin)

`dotnet tool install --global PptMcp.CLI` **funktioniert NICHT** — das NuGet-Paket enthält keine gültige `DotnetToolSettings.xml`. Stattdessen Source-Build:

1. `.NET SDK 9.0.311` user-lokal in `%USERPROFILE%\.dotnet` (per `dotnet-install.ps1`)
2. Repo `trsdn/mcp-server-ppt` nach `C:\Daten\Programme\mcp-server-ppt` geklont
3. Build mit `-p:TreatWarningsAsErrors=false -p:NuGetAudit=false` (wegen Scriban-NuGet-Audit-Warnungen)
4. Binary: `C:\Daten\Programme\mcp-server-ppt\src\PptMcp.CLI\bin\Release\net9.0-windows\pptcli.exe`

Vollständige Anleitung: [scripts/README_pptcli_installation_windows_no_admin.md](../.agents/skills/skill-powerpoint-ppt-cli/scripts/README_pptcli_installation_windows_no_admin.md).

## Erkenntnisse aus dem 5-Folien-POC

POC-Ziel: 5 Folien aus `Volkswagen Brand.potx` erzeugen.
Ergebnis: `userdata/powerpoint/drafts/poc_corporate_deck.pptx` (1.5 MB, 83 Folien — 78 aus Vorlage + 5 eingefügt).

### Was funktioniert
- `session open` + `slide create --position N --layout-name <name>` + `placeholder set-text` + `session close --save` — Standard-Workflow für Folien-Erzeugung.
- `slide list` liefert zuverlässig `layoutName`, `masterName`, `shapeCount` pro Folie — **das ist der praktische Weg, um verfügbare Layouts zu lernen**.
- `.potx` über PowerPoint COM (`Presentations.Open` + `SaveAs(path, 24)`) korrekt als `.pptx` instantiieren.

### Was NICHT funktioniert (pptcli 0.1.0, Source-Build)
- `master list-layouts` → `RuntimeBinderException: System.__ComObject does not contain a definition for 'SlideMasters'` — **bekannter Bug** in der getesteten Version. Workaround: Layout-Namen via `slide list` aus einer Referenzfolie ablesen.
- `Copy-Item <template.potx> <ziel.pptx>` produziert keine gültige `.pptx` — pptcli wirft beim `session open` einen unspezifischen COM-HRESULT.

### Layout-Namen im Volkswagen Brand Template (Auszug)
`Titelfolie weißer Text`, `Titelfolie new horizon`, `Titelfolie mit dunklem Bild 1`, `Agenda dark blue`, `Agenda new horizon`, `Agenda weiß`, `Kapiteltrennfolie`, `Kapiteltrennfolie new horizon`, `Titel und Text`, `Titel und Text (zweispaltig)`, `Titel und Text (DC)`, `Titel und Text (NH)`, `Nur Titel`, `Statement dunkelblau`, `Statement new horizon`, `Statement und dunkles Bild`, `Bild und Statement dark blue`, `Bild vollflächig hell`, `Bild und Text`, `Zwei Bilder und Bullets`, `Drei Bilder und Bullets`, `Titel und Diagramm`, `Kontakt`.

Die Vorlage bringt **bereits ein komplettes Musterdeck** mit — sie ist nicht leer, sondern Referenz-Content. Für frische Decks sollte der POC-Builder die Musterfolien entweder ersetzen oder entfernen, bevor neue Folien eingefügt werden.

## Offene Punkte

1. **POC-Builder verbessern:** vor dem Einfügen neuer Folien die Referenz-Folien aus der Vorlage wegschneiden (`slide delete --slide-index N` in umgekehrter Reihenfolge), damit ein 5-Folien-Deck am Ende tatsächlich nur 5 Folien enthält.
2. **Layout-Discovery robuster machen:** `master list-layouts` Bug upstream melden; vorerst `slide list` + Dedup-Logik nutzen.
3. **MCP-Modus:** `ppt-mcp` aktuell nicht in `.vscode/mcp.json` registriert — optional nachträglich, wenn conversational Flows gebraucht werden.
