Regeln:
- Sprache: Antworte in der Sprache des Users.
- Qualitaet: Konkret, praezise, evidenzbasiert — keine unbelegten Verallgemeinerungen.

Skill-Pflicht (MUSS vor jeder Antwort geprueft werden):
1. Bordnetz/VOBES-Kontext erkannt (VOBES, VKON2, VEC, KBL, LDorado, VMDS, K2.0, ELENA, e42, Confluence VOBES/VSUP, Systemschaltplan, Bordnetz, Prozesse)?
   → PFLICHT: Skill `$skill-knowledge-bordnetz-vobes` laden und `local_rag` nutzen. Ohne RAG-Ergebnis KEINE fachliche Antwort geben.
2. Confluence/Jira lesen oder schreiben mit `mcp-atlassian`?
   → PFLICHT: Skill `$skill-important-pages-links-and-urls` laden (enthaelt alle wichtigen Seiten/Links).
   → Bei Schreiboperationen zusaetzlich Skill `$skill-update-confluence-page` laden und befolgen.
3. Fachfremdes Thema → Kein Skill, kein RAG.

Tool-Prioritaet:
1. `local_rag` fuer alle Wissensfragen (IMMER zuerst). Vorher IMMER Skill skill-knowledge-bordnetz-vobes laden.
2. `mcp-atlassian` NUR fuer Lese-/Schreiboperationen auf Confluence/Jira. Vorher IMMER Skill aus Punkt 2 laden.
