# Regeln

- Sprache: Antworte in der Sprache des Users.
- Qualitaet: Konkret, praezise, evidenzbasiert — keine unbelegten Verallgemeinerungen.
- Zahlenauswertung, Summen und Aggregationen IMMER per PowerShell oder Python berechnen, NIE manuell.
- Bei Budget, Finanz, Beauftragungs, Abruf Themen  **IMMER** eine neue Auswertung erzeugen, nie eine vorhandene Auswertung bzw. .md-Datei verwenden.

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
- UA-Leiter | Unterabteilungsleiter / Leitung einer OE finden  
→ PFLICHT: Skill `$skill-budget-ua-leiter` laden und befolgen.
- EA-Uebersicht | EA-Stammdaten / EA-Nummern / Laufzeiten / Projektfamilien / DevOrders aus BPLUS-NG abrufen  
→ PFLICHT: Skill `$skill-budget-ea-uebersicht` laden und befolgen.
- Eigenleistung | EL-Planung | Mitarbeiter-EL-Buchung (auf welche EA bucht ein MA) | Buchungssperren | Jahressicht EL | EL vs. Fremdleistung  
→ PFLICHT: Skill `$skill-budget-eigenleistung-el` laden und befolgen.