# Installation von `pptcli` (`trsdn/mcp-server-ppt`) unter Windows ohne Adminrechte

Diese Anleitung beschreibt den bereinigten und getesteten Erfolgsweg, um `pptcli.exe` aus `trsdn/mcp-server-ppt` unter Windows lokal zu bauen und zu nutzen — ohne Administratorrechte.

Getesteter Zielpfad:

```text
C:\Daten\Programme\mcp-server-ppt
```

Ziel nach Abschluss:

```powershell
pptcli --help
```

oder direkt:

```powershell
& "C:\Daten\Programme\mcp-server-ppt\src\PptMcp.CLI\bin\Release\net9.0-windows\pptcli.exe" --help
```

---

## 1. Voraussetzungen

Benötigt:

- Windows 10/11
- PowerShell
- Git
- Internetzugang
- lokal installiertes Microsoft PowerPoint
- keine Administratorrechte

Git prüfen:

```powershell
git --version
```

---

## 2. Warum nicht `dotnet tool install`?

Diese Befehle haben im Test nicht funktioniert:

```powershell
dotnet tool install --global PptMcp.CLI
dotnet tool install --global PptMcp.McpServer
```

Fehlerbild:

```text
DotnetToolSettings.xml wurde nicht im Paket gefunden
```

Bewertung:

Die NuGet-Pakete sind aktuell nicht korrekt als `.NET Tool` installierbar.

Daher wird `pptcli` aus dem GitHub-Repository lokal gebaut.

---

## 3. .NET SDK ohne Adminrechte installieren

Das Repository verlangt über `global.json` aktuell exakt:

```text
.NET SDK 9.0.311
```

`.NET 8` reicht nicht aus.

Installation ins Benutzerprofil:

```powershell
Invoke-WebRequest https://dot.net/v1/dotnet-install.ps1 -OutFile "$env:TEMP\dotnet-install.ps1"

& "$env:TEMP\dotnet-install.ps1" `
  -Version 9.0.311 `
  -InstallDir "$env:USERPROFILE\.dotnet"
```

Aktuelle PowerShell-Session vorbereiten:

```powershell
$env:DOTNET_ROOT = "$env:USERPROFILE\.dotnet"
$env:PATH = "$env:USERPROFILE\.dotnet;$env:USERPROFILE\.dotnet\tools;$env:PATH"
```

Prüfen:

```powershell
dotnet --list-sdks
dotnet --info
```

Erwartung:

```text
9.0.311 [C:\Users\<USER>\.dotnet\sdk]
```

---

## 4. .NET dauerhaft für den Benutzer setzen

```powershell
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$dotnetPaths = "$env:USERPROFILE\.dotnet;$env:USERPROFILE\.dotnet\tools"

if ($userPath -notlike "*$env:USERPROFILE\.dotnet*") {
    [Environment]::SetEnvironmentVariable(
        "Path",
        "$userPath;$dotnetPaths",
        "User"
    )
}

[Environment]::SetEnvironmentVariable(
    "DOTNET_ROOT",
    "$env:USERPROFILE\.dotnet",
    "User"
)
```

Danach PowerShell oder VS Code neu öffnen.

---

## 5. Repository klonen

```powershell
New-Item -ItemType Directory -Force C:\Daten\Programme | Out-Null

git clone https://github.com/trsdn/mcp-server-ppt.git C:\Daten\Programme\mcp-server-ppt

cd C:\Daten\Programme\mcp-server-ppt
```

Projektdateien prüfen:

```powershell
Get-ChildItem . -Recurse -Filter *.csproj | Select-Object FullName
```

Wichtig ist diese Datei:

```text
C:\Daten\Programme\mcp-server-ppt\src\PptMcp.CLI\PptMcp.CLI.csproj
```

---

## 6. `pptcli` bauen

Nicht diesen Standard-Befehl verwenden:

```powershell
dotnet build .\src\PptMcp.CLI\PptMcp.CLI.csproj -c Release
```

Der Build kann aktuell wegen NuGet-Audit/Scriban-Warnungen fehlschlagen:

```text
NU1904: Warnung als Fehler: Das Paket "Scriban" ...
NU1902: Warnung als Fehler: Das Paket "Scriban" ...
```

Auch dieser Versuch war im Test fehlerhaft:

```powershell
-p:WarningsNotAsErrors=NU1901,NU1902,NU1903,NU1904
```

Fehlerbild:

```text
MSBUILD : error MSB1006: Die Eigenschaft ist ungültig.
Schalter: NU1902
```

Erfolgreich war dieser Build-Befehl:

```powershell
cd C:\Daten\Programme\mcp-server-ppt

dotnet build .\src\PptMcp.CLI\PptMcp.CLI.csproj `
  -c Release `
  "-p:TreatWarningsAsErrors=false" `
  "-p:NuGetAudit=false"
```

Erwartung:

```text
PptMcp.CLI Erfolgreich → src\PptMcp.CLI\bin\Release\net9.0-windows\pptcli.dll
Erstellen von Erfolgreich
```

---

## 7. `pptcli.exe` finden

```powershell
Get-ChildItem .\src\PptMcp.CLI\bin\Release -Recurse -Filter *.exe |
  Select-Object FullName
```

Erwarteter Pfad:

```text
C:\Daten\Programme\mcp-server-ppt\src\PptMcp.CLI\bin\Release\net9.0-windows\pptcli.exe
```

---

## 8. `pptcli` testen

Direktaufruf:

```powershell
& "C:\Daten\Programme\mcp-server-ppt\src\PptMcp.CLI\bin\Release\net9.0-windows\pptcli.exe" --help
```

Wenn Hilfe angezeigt wird, ist der Build erfolgreich.

---

## 9. Alias für aktuelle PowerShell-Session

```powershell
Set-Alias pptcli "C:\Daten\Programme\mcp-server-ppt\src\PptMcp.CLI\bin\Release\net9.0-windows\pptcli.exe"

pptcli --help
```

---

## 10. Alias dauerhaft setzen

PowerShell-Profil öffnen:

```powershell
notepad $PROFILE
```

Falls Datei oder Ordner noch nicht existieren:

```powershell
New-Item -ItemType File -Force $PROFILE
notepad $PROFILE
```

Diese Zeile einfügen:

```powershell
Set-Alias pptcli "C:\Daten\Programme\mcp-server-ppt\src\PptMcp.CLI\bin\Release\net9.0-windows\pptcli.exe"
```

PowerShell neu öffnen und testen:

```powershell
pptcli --help
```

---

## 11. Häufige Fehler und Lösungen

### Fehler: `dotnet` wird nicht erkannt

Session setzen:

```powershell
$env:DOTNET_ROOT = "$env:USERPROFILE\.dotnet"
$env:PATH = "$env:USERPROFILE\.dotnet;$env:USERPROFILE\.dotnet\tools;$env:PATH"
```

Dann prüfen:

```powershell
dotnet --info
```

---

### Fehler: SDK 9.0.311 fehlt

Fehlerbild:

```text
Requested SDK version: 9.0.311
A compatible .NET SDK was not found.
```

Lösung:

```powershell
& "$env:TEMP\dotnet-install.ps1" `
  -Version 9.0.311 `
  -InstallDir "$env:USERPROFILE\.dotnet"
```

---

### Fehler: NuGet-Audit / Scriban / Warnung als Fehler

Fehlerbild:

```text
NU1904: Warnung als Fehler: Das Paket "Scriban" ...
NU1902: Warnung als Fehler: Das Paket "Scriban" ...
```

Lösung:

```powershell
dotnet build .\src\PptMcp.CLI\PptMcp.CLI.csproj `
  -c Release `
  "-p:TreatWarningsAsErrors=false" `
  "-p:NuGetAudit=false"
```

---

### Fehler: `WarningsNotAsErrors` wird falsch interpretiert

Fehlerbild:

```text
MSBUILD : error MSB1006: Die Eigenschaft ist ungültig.
Schalter: NU1902
```

Lösung:

Diesen Ansatz nicht verwenden. Stattdessen:

```powershell
"-p:TreatWarningsAsErrors=false" `
"-p:NuGetAudit=false"
```

---

### Fehler: `dotnet tool install --global PptMcp.CLI` schlägt fehl

Fehlerbild:

```text
DotnetToolSettings.xml wurde nicht im Paket gefunden
```

Lösung:

Nicht NuGet verwenden, sondern aus Source bauen.

---

## 12. Kompletter Installationsblock

```powershell
# .NET SDK 9.0.311 ohne Adminrechte installieren
Invoke-WebRequest https://dot.net/v1/dotnet-install.ps1 -OutFile "$env:TEMP\dotnet-install.ps1"

& "$env:TEMP\dotnet-install.ps1" `
  -Version 9.0.311 `
  -InstallDir "$env:USERPROFILE\.dotnet"

# Aktuelle Session vorbereiten
$env:DOTNET_ROOT = "$env:USERPROFILE\.dotnet"
$env:PATH = "$env:USERPROFILE\.dotnet;$env:USERPROFILE\.dotnet\tools;$env:PATH"

# .NET dauerhaft fuer Benutzer setzen
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$dotnetPaths = "$env:USERPROFILE\.dotnet;$env:USERPROFILE\.dotnet\tools"

if ($userPath -notlike "*$env:USERPROFILE\.dotnet*") {
    [Environment]::SetEnvironmentVariable(
        "Path",
        "$userPath;$dotnetPaths",
        "User"
    )
}

[Environment]::SetEnvironmentVariable(
    "DOTNET_ROOT",
    "$env:USERPROFILE\.dotnet",
    "User"
)

# Repository klonen
New-Item -ItemType Directory -Force C:\Daten\Programme | Out-Null

git clone https://github.com/trsdn/mcp-server-ppt.git C:\Daten\Programme\mcp-server-ppt

cd C:\Daten\Programme\mcp-server-ppt

# CLI bauen
dotnet build .\src\PptMcp.CLI\PptMcp.CLI.csproj `
  -c Release `
  "-p:TreatWarningsAsErrors=false" `
  "-p:NuGetAudit=false"

# Test
& "C:\Daten\Programme\mcp-server-ppt\src\PptMcp.CLI\bin\Release\net9.0-windows\pptcli.exe" --help

# Alias fuer aktuelle Session
Set-Alias pptcli "C:\Daten\Programme\mcp-server-ppt\src\PptMcp.CLI\bin\Release\net9.0-windows\pptcli.exe"

pptcli --help
```

---

## 13. Optional: PowerShell-Profil dauerhaft ergänzen

```powershell
New-Item -ItemType File -Force $PROFILE
notepad $PROFILE
```

Einfügen:

```powershell
Set-Alias pptcli "C:\Daten\Programme\mcp-server-ppt\src\PptMcp.CLI\bin\Release\net9.0-windows\pptcli.exe"
```

Danach neue PowerShell öffnen:

```powershell
pptcli --help
```

---

## TL;DR

Nicht verwenden:

```powershell
dotnet tool install --global PptMcp.CLI
dotnet tool install --global PptMcp.McpServer
```

Stattdessen:

1. `.NET SDK 9.0.311` user-lokal installieren
2. Repository nach `C:\Daten\Programme\mcp-server-ppt` klonen
3. Build ausführen mit:

```powershell
dotnet build .\src\PptMcp.CLI\PptMcp.CLI.csproj `
  -c Release `
  "-p:TreatWarningsAsErrors=false" `
  "-p:NuGetAudit=false"
```

4. Testen mit:

```powershell
& "C:\Daten\Programme\mcp-server-ppt\src\PptMcp.CLI\bin\Release\net9.0-windows\pptcli.exe" --help
```
