---
name: skill-powerpoint-ppt-cli
description: PowerPoint-Dateien (.pptx) auf Windows aus einer Corporate-Vorlage (.potx) per lokalem `pptcli` erstellen und bearbeiten. Nutze diesen Skill fuer PowerPoint, PPTX, Folien, Praesentation, Deck, Unternehmensvorlage, Corporate Template, Volkswagen Brand, Volkswagen Group, potx, Folientext setzen, Chart einfuegen, Tabelle in Folie, Bullet-Liste, Deck bauen, COM-Automatisierung.
---

# Skill: PowerPoint mit pptcli

Reproduzierbare PPTX-Erzeugung aus einer Unternehmensvorlage — per lokalem `pptcli.exe` (COM-basiert, nutzt das installierte Microsoft PowerPoint). Keine direkte XML-Manipulation, keine Neuerfindung von Layouts.

## Wann verwenden

- neue Praesentation aus Corporate-Vorlage bauen
- Folien hinzufuegen / Text setzen / Tabellen / Bilder / Charts einfuegen
- bestehende `.pptx` gezielt bearbeiten (COM, keine XML-Hacks)
- Export nach PDF aus der fertigen `.pptx`

## Wann NICHT verwenden

- nur PPTX → PDF konvertieren ohne Aenderung → `$skill-file-converter`
- PPTX-Text aus SharePoint/OneDrive nur **lesen** → `$skill-m365-file-reader`
- Linux/Server-Umgebung (kein lokales PowerPoint) → `python-pptx` direkt

## Voraussetzungen

| Komponente | Pfad / Check |
|---|---|
| Microsoft PowerPoint (Desktop) | muss auf dem System installiert sein |
| .NET 9 Desktop Runtime + SDK 9.0.311 | user-lokal unter `%USERPROFILE%\.dotnet`, `dotnet --list-runtimes` muss `Microsoft.WindowsDesktop.App 9.x` enthalten |
| pptcli.exe | `C:\Daten\Programme\mcp-server-ppt\src\PptMcp.CLI\bin\Release\net9.0-windows\pptcli.exe` |
| Vorlagen-Ordner | `.agents/skills/skill-powerpoint-ppt-cli/Vorlagen/` (lokal, mit `.lnk` auf OneDrive) |

**Erst-Installation ohne Adminrechte:** Schritt-fuer-Schritt-Anleitung inkl. SDK-Install, Clone, Build und Alias siehe [scripts/README_pptcli_installation_windows_no_admin.md](./scripts/README_pptcli_installation_windows_no_admin.md). `dotnet tool install --global PptMcp.CLI` funktioniert aktuell **nicht** (Paket-Fehler) — Source-Build ist Pflicht.

## Arbeitsregeln (verpflichtend)

1. **Vorlage vom User bestaetigen lassen.** Nie einfach eine Default-Vorlage waehlen. Liste via:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .agents/skills/skill-powerpoint-ppt-cli/scripts/select_template.ps1
   ```
   Gibt JSON mit allen verfuegbaren `.potx`/`.pptx` aus; User entscheidet.
2. **Original-Vorlage nie direkt aendern.** Immer erst nach `userdata/powerpoint/drafts/<deck>.pptx` kopieren.
3. **Layouts/Placeholders auslesen** bevor Inhalte geschrieben werden. Nur vorhandene Corporate-Layouts nutzen.
4. **Bei Fehlern kein XML-Hack** — COM-/CLI-Fehler sauber melden und zurueck an User.
5. **Dateisperren pruefen** — wenn die `.pptx` in PowerPoint geoeffnet ist, vorher schliessen.

## Standard-Pfade

| Zweck | Pfad |
|---|---|
| Vorlagen | `.agents/skills/skill-powerpoint-ppt-cli/Vorlagen/*.potx` |
| Entwuerfe | `userdata/powerpoint/drafts/` |
| Exporte (PDF) | `userdata/powerpoint/exports/` |
| Bilder fuer Folien | `userdata/powerpoint/images/` |

## Workflow

```powershell
# 1. Vorlagen listen und User auswaehlen lassen
powershell -ExecutionPolicy Bypass -File .agents/skills/skill-powerpoint-ppt-cli/scripts/select_template.ps1

# 2. 5-Folien-POC aus gewaehlter Vorlage bauen
powershell -ExecutionPolicy Bypass -File .agents/skills/skill-powerpoint-ppt-cli/scripts/build_deck_poc.ps1 `
    -TemplatePath ".agents/skills/skill-powerpoint-ppt-cli/Vorlagen/Volkswagen Brand.potx" `
    -OutputPath "userdata/powerpoint/drafts/poc_corporate_deck.pptx"

# 3. Manuelle Pruefung in PowerPoint:
#    - Corporate-Design uebernommen?
#    - Layouts/Placeholders korrekt belegt?
```

Direkte `pptcli`-Aufrufe (Schema wird nach Verifikation aus `pptcli --help` hier ergaenzt):

```powershell
$pptcli = "C:\Daten\Programme\mcp-server-ppt\src\PptMcp.CLI\bin\Release\net9.0-windows\pptcli.exe"
& $pptcli --help
& $pptcli layouts --file "userdata/powerpoint/drafts/poc_corporate_deck.pptx"
```

> **TODO nach Runtime-Install:** Reale Befehlsliste aus `pptcli --help` hier eintragen. Bis dahin dient `build_deck_poc.ps1` als Referenz.

## Fehlerbehandlung

| Fehler | Ursache | Fix |
|---|---|---|
| `You must install .NET to run this application` | .NET 9 Runtime fehlt | SDK 9.0.311 user-lokal installieren, siehe `scripts/README_pptcli_installation_windows_no_admin.md` |
| `dotnet tool install --global PptMcp.CLI` schlaegt fehl | NuGet-Paket fehlerhaft | Source-Build statt NuGet, siehe Installationsanleitung |
| `pptcli` nicht auf PATH | user-lokale `.dotnet` noch nicht im aktuellen Terminal | `$env:PATH = "$env:USERPROFILE\.dotnet;$env:PATH"` oder Alias per PowerShell-Profil setzen |
| `file is locked` / `access denied` | Deck oder Vorlage in PowerPoint offen | In PowerPoint schliessen, erneut versuchen |
| `layout not found` | Layout-Name nicht in Vorlage | Layout-Namen via `pptcli slide list --session <id>` (Feld `layoutName`) ermitteln, nicht via `master list-layouts` |
| `master list-layouts` schlaegt fehl (RuntimeBinderException `SlideMasters`) | Known bug in pptcli 0.1.0 (Source-Build) | Workaround: `slide list` nutzen — das liefert `layoutName` je Folie |
| `InvalidOperationException: Failed to create session ... COM HRESULT` beim Oeffnen einer `.pptx`, die aus `.potx` per `Copy-Item` umbenannt wurde | `.potx`-Rohdaten sind keine gueltige `.pptx` fuer COM | `.potx` per PowerPoint COM `Presentations.Open` + `SaveAs(path, 24)` als echte `.pptx` instantiieren (siehe `build_deck_poc.ps1`) |
| COM-HResult `0x800A03EC` | PowerPoint-Instanz inkonsistent | PowerPoint beenden (`taskkill /IM POWERPNT.EXE /F`), retry |

## Abhaengigkeiten

- lokales Microsoft PowerPoint (Desktop, Windows)
- .NET 9 Desktop Runtime
- `pptcli.exe` aus `trsdn/mcp-server-ppt` (lokal gebaut, Pfad siehe oben)

## Hinweise

- **Nicht serverfaehig** — COM erfordert Windows-Desktop mit PowerPoint.
- `.potx`-Vorlagen werden beim Kopieren direkt als `.pptx` ins Draft-Verzeichnis gelegt (nicht in-place bearbeiten).
- `ppt-mcp` (MCP-Server-Modus) ist Nebenpfad fuer explorative Aufgaben und aktuell **nicht** in `.vscode/mcp.json` registriert. CLI ist Hauptpfad.

## Mapping (neu)

- Fuer robuste Placeholder-Befuellung (Titel/Subtitel/Haupttext, Zweispalter, Bild+Text, Diagramm/Tabelle) ist ein layout-spezifisches Mapping vorhanden:
  - `.agents/skills/skill-powerpoint-ppt-cli/mappings/volkswagen_brand.layout_mapping.json`
- Beispiel-Builder mit Mapping:
  - `.agents/skills/skill-powerpoint-ppt-cli/scripts/_build_test_email_prompt_deck.ps1`
  - liest Inhalte aus `.agents/skills/skill-powerpoint-ppt-cli/scripts/data/test_email_prompt_content.json`
- Umlaute werden ueber JSON (`Get-Content -Encoding UTF8` + `ConvertFrom-Json`) stabil geladen.
- Slot-Typen im Content-JSON:
  - Text-Slots: `title`, `subtitle`, `main_text`, `left_text`, `right_text`, `caption`
  - Medien-Slot: `image` (String-Pfad oder `{ "path": "..." }`, relativ zur Content-Datei erlaubt)
  - Tabellen-Slot: `table` mit `{ "headers": [...], "rows": [[...], ...] }` oder `table: "pfad/zur/datei.csv"`
- Beispiel fuer erweiterte Layouts (Zweispalter, Bild+Text, Tabelle):
  - `.agents/skills/skill-powerpoint-ppt-cli/scripts/data/test_layout_features_content.json`
