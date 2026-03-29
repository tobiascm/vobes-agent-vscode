# Regeln

- Sprache: Antworte in der Sprache des Users.
- Qualitaet: Konkret, praezise, evidenzbasiert — keine unbelegten Verallgemeinerungen.
- Zahlenauswertung, Summen und Aggregationen IMMER per PowerShell oder Python berechnen, NIE manuell.
- Bei Budget, Finanz, Beauftragungs, Abruf Themen  **IMMER** eine neue Auswertung erzeugen, nie eine vorhandene Auswertung bzw. .md-Datei verwenden.
- Git Commit IMMER ueber Skill `$git-commit` ausfuehren, NIEMALS manuell `git commit` aufrufen.
- Git Push IMMER ueber Skill `$git-push` ausfuehren, NIEMALS manuell `git push` aufrufen.

# Skill-Pflicht (MUSS vor jeder Antwort geprueft werden):

1. Bordnetz/VOBES-Kontext erkannt (VOBES, VKON2, VEC, KBL, LDorado, VMDS, K2.0, ELENA, e42, Confluence VOBES/VSUP, Systemschaltplan, Bordnetz, Prozesse)?
  → PFLICHT: Skill `$skill-knowledge-bordnetz-vobes` laden und `local_rag` nutzen. Ohne RAG-Ergebnis KEINE fachliche Antwort geben.
2. Confluence/Jira lesen oder schreiben mit `mcp-atlassian`?
  → PFLICHT: Skill `$skill-important-pages-links-and-urls` laden (enthaelt alle wichtigen Seiten/Links).  
   → Bei Schreiboperationen zusaetzlich Skill `$skill-update-confluence-page` laden und befolgen.
3. Fachfremdes Thema → Kein Skill, kein RAG.

# Tool-Prioritaet

1. `local_rag` fuer alle Wissensfragen (IMMER zuerst). Vorher IMMER Skill skill-knowledge-bordnetz-vobes laden.
2. `mcp-atlassian` NUR fuer Lese-/Schreiboperationen auf Confluence/Jira. Vorher IMMER Skill aus Punkt 2 laden.

# Modus-Erkennung (MCP-Verfuegbarkeit)

Bevor ein Skill geladen wird, der einen MCP-Server benoetigt, MUSS geprueft werden, ob die MCP-Tools verfuegbar sind.

# Fehlerfälle

## Plan-Modus aktiv
 Falls ein MCP-Tools nicht verfuegbar prüfe über aufruf  `tool_search_tool_regex` mit dem passenden Pattern. Liefert die Suche KEINE Ergebnisse, sind die MCP-Tools nicht verfuegbar (z.B. weil der Plan-Modus aktiv ist). Wenn Ergebnis = leer → **SOFORT** folgende Meldung ausgeben und die Aufgabe abbrechen:

> ⚠️ Ich bin aktuell im **Plan-Modus** und habe keinen Zugriff auf den MCP-Server `{server_name}`, der fuer diese Aufgabe benoetigt wird.
>
> **Loesung:** Bitte wechsle in den **Agent-Modus** (ueber das Modus-Dropdown oben im Chat) und stelle die Frage dort erneut.


# Use-Cases

- Protokoll erstellen | ueberarbeiten und in Confluence speichern  
→ PFLICHT: Skill `$skill-protokoll-confluence` laden und befolgen.  
→ Zusaetzlich Skills `$skill-important-pages-links-and-urls` und `$skill-update-confluence-page` laden.
- TE Regelwerk durchsuchen | Prozessstandard / Arbeitsanweisung finden, laden oder lesen  
→ PFLICHT: Skill `$skill-te-regelwerk` laden und befolgen.
- BPLUS-NG Export | Vorgangsuebersicht / Abrufuebersicht / BM-Uebersicht als CSV oder Excel herunterladen  
→ PFLICHT: Skill `$skill-budget-bplus-export` laden und befolgen.
- Firma | Lieferant | Dienstleister | Partner → auf welche EA / DevOrder gebucht / zugeordnet / welche Vorgaenge hat Firma X  
→ PFLICHT: Skill `$skill-budget-bplus-export` laden und befolgen.
- Stundensaetze | OE-Stundensaetze / Kostenstellen-Saetze aus BPLUS-NG abrufen  
→ PFLICHT: Skill `$skill-budget-stundensaetze` laden und befolgen.
- Person suchen | Chef | Vorgesetzter | Kollegen | Organigramm | OE-Struktur | Mitarbeiter finden | userId | wer ist | wer leitet | Telefonnummer | Kontaktdaten  
→ PFLICHT: Skill `$skill-personensuche-groupfind` laden und befolgen. Erster Skill fuer alle Personensuchen und Hierarchie-Fragen.
- UA-Leiter | OE-Mail-Zuordnung fuer Budget-Kontext (welche Mail gehoert zu einer OE)  
→ PFLICHT: Skill `$skill-budget-ua-leiter` laden und befolgen. NUR fuer Budget-spezifische OE→Mail-Zuordnung, NICHT fuer Personensuche (dafuer `$skill-personensuche-groupfind`).
- EA-Uebersicht | EA-Stammdaten / EA-Nummern / Laufzeiten / Projektfamilien / DevOrders aus BPLUS-NG abrufen  
→ PFLICHT: Skill `$skill-budget-ea-uebersicht` laden und befolgen.
- Eigenleistung | EL-Planung | Mitarbeiter-EL-Buchung (auf welche EA bucht ein MA) | Buchungssperren | Jahressicht EL | EL vs. Fremdleistung  
→ PFLICHT: Skill `$skill-budget-eigenleistung-el` laden und befolgen.
- Plausibilisierung | Begruendung | BM-Text | Aufwandsplausibilisierung | Nachfrage Controller | warum wird X benoetigt | Aufwaende begruenden  
→ PFLICHT: Skill `$skill-budget-plausibilisierung` laden und befolgen.
- Webseite oeffnen | Intranet-Seite durchsuchen | Screenshot von Seite | Daten von Webseite extrahieren | Formular auf Webseite ausfuellen (per Playwright MCP, nicht dev-browser)  
→ PFLICHT: Skill `$skill-browse-intranet` laden und befolgen.
- Deep Research | Recherchiere systematisch | Untersuche systematisch | Multi-Source-Recherche | evidence-backed research across portals  
→ PFLICHT: Skill `$skill-deep-research` laden und befolgen. Fuer mehrstufige, quellenuebergreifende Recherchen mit Evidenzsammlung und strukturiertem Abschlussbericht. Delegiert alle Browser-Interaktionen an `skill-browse-intranet`.
- M365 Copilot Search | SharePoint durchsuchen | Dokument in SharePoint finden | OneDrive durchsuchen | M365 Suche | Copilot Suche | finde Datei in SharePoint  
→ PFLICHT: Skill `$skill-copilot-search` laden und befolgen. Nutzt Graph Beta API ueber Playwright NAA-Token.
- M365 Copilot Chat | frage Copilot | schicke diesen Prompt an Copilot | lasse M365 Copilot das beantworten  
→ PFLICHT: Skill `$skill-m365-copilot-chat` laden und befolgen.
- M365 Datei lesen | Inhalt einer SharePoint-Datei | PPTX aus OneDrive lesen | Excel aus SharePoint als CSV | PDF aus SharePoint extrahieren | Bild aus OneDrive herunterladen | was steht in der Datei  
→ PFLICHT: Skill `$skill-m365-file-reader` laden und befolgen. Liest PPTX, XLSX, DOCX, PDF und Bilder ueber Graph API.