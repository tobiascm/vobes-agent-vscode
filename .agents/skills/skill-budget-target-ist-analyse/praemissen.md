## Prämissen

### Zuordnung Firma → Aufgabenbereich
- EDAG, Bertrandt → Systemschaltpläne
- GroupServices (ex T-Systems) → CATIA-Bibliothek
- FES, FEV → Projektbüro / Prüfbüro
- SEBN → Pilot und Anwendertest VOBES2025
- Voitas → RuleChecker (ab Q3/2026 durch 4soft, daher Start_Q=3 in target.csv)

### Split-Firmen
- **4soft:** BM-Titel enthält `TE-PMT`/`Bordnetz`/`Konzeptentw`/`Integration` → SW-Entwicklung VOBES2025; Rest → Vorentwicklung
- **Thiesen:** Split nach Gewerk-Nummern im BM-Text: nur Gewerk `#2` (Stückpreis-Abruf) → Spez. und Test VOBES2025; mehrere Gewerke (`#1,#2,#3,#5` + `#4` FPs) → Bordnetz Support/RollOut

### Feste Werte
- AUDI Bibliotheksarbeiten: **344 T€** (in EDAG-BMs integriert, separat ausgewiesen)
- BordnetzGPT: entfällt ab 2026 (war MSG)
- SYS-Flow: entfällt ab 2026 (war PEC)
- Voitas: Ende 2025 raus → RuleChecker geht ab Q3/2026 an 4soft (Soll Q1-2 = 0)

### Referenzwerte
- 2025-Werte: aus Vorjahresplanung (fest, siehe target.csv)
- 2026-Target: aus Budgetplanung (fest, siehe target.csv)

### Budget-Tracking durch Finanz
- Die **Targetsumme** muss komplett in BPLUS als Summe aller Vorgänge eingetragen sein (Spalte „Ist").
- Jedoch darf pro Quartal nur die jeweilige **Quartalssumme** im Status „im Durchlauf" + „bestellt" stehen.
- Die Finanz trackt das Target auf Quartalsebene — d.h. DIFF Q1-x zeigt, ob das Quartalsbudget eingehalten wird.

---

### Hardcoded im Script (report_massnahmenplan.py)
- Firma→Aufgabenbereich Mapping (classify_bm-Funktion): welche Firma zu welchem Bereich gehört
- Split-Keywords für 4soft: `TE-PMT`, `BORDNETZ`, `KONZEPTENTW`, `INTEGRATION`
- Split-Logik für Thiesen: Gewerk-Nummern aus BM-Text (`#2` only → Spez.; multi-Gewerk → Bordnetz Support)
- AUDI-Korrektur: fester Abzug vom Systemschaltplan-Bereich, Wert aus target.csv
- AUDI_KEY: "AUDI - Bibliotheksarbeiten (Audi)" als Sonder-Kategorie

### Vom Agent zu beachten
- Maßnahmen-Spalte NIE automatisch befüllen — User entscheidet
- Bei neuen Firmen oder geänderten Zuordnungen: `classify_bm()` im Script anpassen
- Bei neuen Aufgabenbereichen: Zeile in `target.csv` ergänzen
- Bei geänderten Split-Keywords (z.B. neue BM-Titel bei 4soft/Thiesen): Script anpassen
- 2026-Ist: BPLUS-NG live-Sync
