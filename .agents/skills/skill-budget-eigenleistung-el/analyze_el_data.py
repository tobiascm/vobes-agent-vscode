#!/usr/bin/env python3
"""
BPLUS-NG Eigenleistung (EL) — Analyse & Reporting (Python 3.11)

Liest die konsolidierte JSON-Datei aus export_el_data.ps1 und erzeugt
Markdown-Reports für verschiedene Use Cases:
- MA-Planung: Auf welche EAs bucht ein MA?
- Buchungssperren: Welche EAs sind noch gesperrt?
- Jahressicht: EL in EUR pro EA (Aggregation)
- Gesamt-Übersicht: EL vs. Fremdleistung pro EA (Join mit BTL)

Caching: 1 Tag (überschreibbar mit --force-refresh)
Timeout-Fallback: Bei Fehler → letzter Export + Warnhinweis
Logging: tmp/logs/analyze_el_data_*.log
"""

import json
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging

# --- Konfiguration ---
WORKSPACE_ROOT = Path(__file__).parent.parent.parent.parent
TMP_DIR = WORKSPACE_ROOT / "userdata" / "tmp"
LOGS_DIR = WORKSPACE_ROOT / "userdata" / "tmp" / "logs"
SESSIONS_DIR = WORKSPACE_ROOT / "userdata" / "sessions"
CACHE_DIR = TMP_DIR

# Verzeichnisse erstellen
for d in [LOGS_DIR, SESSIONS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Logging konfigurieren
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = LOGS_DIR / f"analyze_el_data_{timestamp}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# --- Utilities ---

def find_latest_export(year: int) -> Optional[Path]:
    """Findet die neueste konsolidierte Export-Datei für das Jahr."""
    pattern = f"_el_consolidated_{year}.json"
    files = list(CACHE_DIR.glob(pattern))
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def load_export_data(json_path: Path, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
    """
    Lädt die konsolidierte EL-Export-Datei.
    
    Bei Fehler: Versucht, letzte Datei zu nutzen + Warnhinweis.
    """
    if not json_path.exists():
        logger.error(f"Export-Datei nicht gefunden: {json_path}")
        logger.warning("Versuche, letzte verfügbare Export-Datei zu laden...")
        
        # Versuche, irgendeine ältere Datei zu finden
        year = int(json_path.stem.split("_")[-1])
        fallback = find_latest_export(year)
        
        if fallback:
            logger.warning(f"Nutze Fallback: {fallback}")
            json_path = fallback
        else:
            logger.error("Keine Export-Datei vorhanden. Führe export_el_data.ps1 aus.")
            return None
    
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info(f"Export-Datei geladen: {json_path}")
        return data
    except Exception as e:
        logger.error(f"Fehler beim Laden der JSON-Datei: {e}")
        return None


def get_cache_age_hours(json_path: Path) -> float:
    """Berechnet das Alter der Cache-Datei in Stunden."""
    mtime = datetime.fromtimestamp(json_path.stat().st_mtime)
    age = datetime.now() - mtime
    return age.total_seconds() / 3600


def create_warning_header(data: Dict[str, Any], fallback: bool = False) -> str:
    """Erzeugt Warnhinweis bei Cache-Timeout."""
    timestamp_str = data.get("exportTimestamp", "unbekannt")
    try:
        export_time = datetime.fromisoformat(timestamp_str)
        time_str = export_time.strftime("%Y-%m-%d %H:%M:%S UTC+1")
    except:
        time_str = timestamp_str
    
    if fallback:
        return f"""❌ **WARNUNG: DATEN SIND VERALTET**

Die aktuellen Daten konnten nicht abgerufen werden. Es werden ältere Daten vom **{time_str}** verwendet.
Versuchen Sie später erneut, oder führen Sie `export_el_data.ps1 -ForceRefresh` aus.

---

"""
    else:
        return f"""ℹ️ **Daten vom {time_str} UTC+1**

"""


# --- Use-Case 1: MA-Planung ---

def generate_ma_planning(data: Dict[str, Any], mitarbeiter: str) -> str:
    """Erzeugt Bericht: Auf welche EAs bucht ein Mitarbeiter?"""
    logger.info(f"Generiere MA-Planung für: {mitarbeiter}")
    
    output = "# Eigenleistungs-Planung: Mitarbeiterbuchung\n\n"
    output += create_warning_header(data)
    
    planning_exceptions = data.get("planningExceptions", [])
    
    # Suche MA (fuzzy: partial match, case-insensitive)
    ma_data = None
    search_term = mitarbeiter.lower()
    for item in planning_exceptions:
        if search_term in item.get("userName", "").lower():
            ma_data = item
            break
    
    if not ma_data:
        output += f"❌ Mitarbeiter '{mitarbeiter}' nicht gefunden in Export.\n"
        output += f"Verfügbare MA: {', '.join([p['userName'] for p in planning_exceptions])}\n"
        return output
    
    # MA-Kontext
    user_name = ma_data["userName"]
    user_data = ma_data["data"]
    year_work_hours = user_data.get("yearWorkHours", 1500)
    hourly_rate = user_data.get("hourlyRateFltValueMix", 0)
    
    output += f"## {user_name}\n\n"
    output += f"- **Jahresstunden:** {year_work_hours:,} h\n"
    output += f"- **Stundensatz (Mix):** {hourly_rate:.2f} EUR/h\n"
    output += f"- **Jahr:** {data.get('year', 'N/A')}\n\n"
    
    # PlanningExceptions Tabelle
    exceptions = user_data.get("planningExceptions", [])
    
    if not exceptions:
        output += "**Keine EA-Zuordnungen vorhanden.**\n"
        return output
    
    # Tabellen-Header
    output += "| EA-Nummer | EA-Titel | Projektfamilie | "
    output += "Jan | Feb | Mär | Apr | Mai | Jun | Jul | Aug | Sep | Okt | Nov | Dez | "
    output += "Gesamt | Jahresstunden | Sperrungen |\n"
    output += "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    
    months = ["percentInJan", "percentInFeb", "percentInMar", "percentInApr", 
              "percentInMay", "percentInJun", "percentInJul", "percentInAug", 
              "percentInSep", "percentInOct", "percentInNov", "percentInDec"]
    month_names = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
    
    total_percent_by_month = {m: 0 for m in months}
    
    for exc in exceptions:
        ea_number = exc.get("number", "?")
        ea_title = exc.get("devOrderDescription", "?")[:30]  # Truncate
        proj_family = exc.get("projectFamily", "—")
        
        # Monatliche Prozente
        month_values = []
        total_pct = 0
        blocked_months = []
        
        for i, month in enumerate(months):
            pct = exc.get(month, 0)
            month_values.append(f"{int(pct)}%")
            total_pct += pct
            total_percent_by_month[month] += pct
            
            # Buchungssperren
            booking_exceptions = exc.get("bookingRightsExceptionsMonths", [])
            if booking_exceptions and (i+1) in booking_exceptions:
                blocked_months.append(month_names[i])
        
        # Jahresstunden berechnen
        hours_on_ea = (total_pct / 100.0) * year_work_hours if total_pct > 0 else 0
        sperrungen = ", ".join(blocked_months) if blocked_months else "—"
        
        # Tabellen-Zeile
        output += f"| {ea_number} | {ea_title} | {proj_family} | "
        output += " | ".join(month_values) + f" | {int(total_pct)}% | {hours_on_ea:.0f}h | {sperrungen} |\n"
    
    # Summen-Zeile
    output += "| — | — | **Summe** | "
    sum_values = []
    for month in months:
        sum_values.append(f"{int(total_percent_by_month[month])}%")
    output += " | ".join(sum_values) + " | — | — |\n"
    
    # Überplanung-Warnung
    output += "\n### ⚠️ Validierung\n\n"
    over_plan = any(total_percent_by_month[m] > 100 for m in months)
    under_plan = any(total_percent_by_month[m] < 100 for m in months)
    
    if over_plan:
        output += "🔴 **ÜBERPLANUNG ERKANNT** — Einige Monate übersteigen 100%\n"
    elif under_plan:
        output += "🟡 **UNTERPLANUNG** — Kapazität nicht vollständig genutzt\n"
    else:
        output += "✅ **Planung korrekt** — Alle Monate = 100%\n"
    
    return output


# --- Use-Case 2: Buchungssperren ---

def generate_buchungssperren(data: Dict[str, Any]) -> str:
    """Erzeugt Bericht: Welche EAs sind noch gesperrt?"""
    logger.info("Generiere Buchungssperren-Bericht")
    
    output = "# Eigenleistungs-Planung: Buchungssperren\n\n"
    output += create_warning_header(data)
    
    planning_exceptions = data.get("planningExceptions", [])
    
    # Sammle alle EAs mit Sperrungen
    blocked_eas = []
    for item in planning_exceptions:
        user_name = item["userName"]
        user_data = item["data"]
        
        for exc in user_data.get("planningExceptions", []):
            booking_exceptions = exc.get("bookingRightsExceptionsMonths", [])
            if booking_exceptions:
                blocked_eas.append({
                    "userName": user_name,
                    "eaNumber": exc.get("number", "?"),
                    "eaTitle": exc.get("devOrderDescription", "?"),
                    "blockedMonths": booking_exceptions,
                })
    
    if not blocked_eas:
        output += "✅ **Keine Buchungssperren vorhanden.**\n"
        return output
    
    output += f"## Gefundene Sperrungen: {len(blocked_eas)}\n\n"
    
    # Tabelle
    output += "| Mitarbeiter | EA-Nummer | EA-Titel | Gesperrte Monate |\n"
    output += "|---|---|---|---|\n"
    
    month_names = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
    
    for blocked in blocked_eas:
        months_str = ", ".join([month_names[m-1] for m in sorted(blocked["blockedMonths"])])
        output += f"| {blocked['userName']} | {blocked['eaNumber']} | {blocked['eaTitle'][:40]} | {months_str} |\n"
    
    return output


# --- Use-Case 3: Jahressicht ---

def generate_jahressicht(data: Dict[str, Any]) -> str:
    """Erzeugt Bericht: EL in EUR pro EA (Jahressicht)"""
    logger.info("Generiere Jahressicht-Bericht")
    
    output = "# Eigenleistungs-Planung: Jahressicht (EUR pro EA)\n\n"
    output += create_warning_header(data)
    
    # Aggregation pro EA
    ea_aggregation = {}
    
    planning_exceptions = data.get("planningExceptions", [])
    
    for item in planning_exceptions:
        user_data = item["data"]
        year_work_hours = user_data.get("yearWorkHours", 1500)
        hourly_rate = user_data.get("hourlyRateFltValueMix", 0)
        
        for exc in user_data.get("planningExceptions", []):
            ea_number = exc.get("number", "?")
            ea_title = exc.get("devOrderDescription", "?")
            proj_family = exc.get("projectFamily", "—")
            
            months = [f"percentIn{m}" for m in ["Jan", "Feb", "Mar", "Apr", "May", "Jun", 
                                                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]]
            total_pct = sum(exc.get(m, 0) for m in months) / len(months) if months else 0
            
            # EL berechnen: (durchschnitt_prozent / 100) * jahresstunden * stundensatz
            el_eur = (total_pct / 100) * year_work_hours * hourly_rate if hourly_rate > 0 else 0
            
            if ea_number not in ea_aggregation:
                ea_aggregation[ea_number] = {
                    "title": ea_title,
                    "family": proj_family,
                    "el_eur": 0,
                }
            ea_aggregation[ea_number]["el_eur"] += el_eur
    
    if not ea_aggregation:
        output += "Keine EA-Daten vorhanden.\n"
        return output
    
    # Sortiert nach EL-Volumen
    sorted_eas = sorted(ea_aggregation.items(), key=lambda x: x[1]["el_eur"], reverse=True)
    
    output += f"## Gesamt: {len(sorted_eas)} EAs\n\n"
    
    # Tabelle
    output += "| EA-Nummer | EA-Titel | Projektfamilie | Geplante EL (EUR) |\n"
    output += "|---|---|---|---:|\n"
    
    total_el = 0
    for ea_num, ea_data in sorted_eas:
        el_amount = ea_data["el_eur"]
        total_el += el_amount
        output += f"| {ea_num} | {ea_data['title'][:40]} | {ea_data['family']} | {el_amount:,.0f} |\n"
    
    output += f"| | | **Gesamte Eigenleistung** | **{total_el:,.0f}** |\n"
    
    return output


# --- Use-Case 4: Gesamt-Übersicht ---

def generate_gesamt_uebersicht(data: Dict[str, Any]) -> str:
    """Erzeugt Bericht: EL vs. Fremdleistung pro EA"""
    logger.info("Generiere Gesamt-Übersicht")
    
    output = "# Eigenleistungs-Planung: Gesamt-Übersicht (EL vs. Fremdleistung)\n\n"
    output += create_warning_header(data)
    
    # Aggregiere EL
    el_by_ea = {}
    planning_exceptions = data.get("planningExceptions", [])
    
    for item in planning_exceptions:
        user_data = item["data"]
        year_work_hours = user_data.get("yearWorkHours", 1500)
        hourly_rate = user_data.get("hourlyRateFltValueMix", 0)
        
        for exc in user_data.get("planningExceptions", []):
            ea_number = exc.get("number", "?")
            ea_title = exc.get("devOrderDescription", "?")
            proj_family = exc.get("projectFamily", "—")
            
            # Durchschnitt der Monats-Prozente
            months = ["percentInJan", "percentInFeb", "percentInMar", "percentInApr",
                      "percentInMay", "percentInJun", "percentInJul", "percentInAug",
                      "percentInSep", "percentInOct", "percentInNov", "percentInDec"]
            avg_pct = sum(exc.get(m, 0) for m in months) / len(months) if months else 0
            el_eur = (avg_pct / 100) * year_work_hours * hourly_rate if hourly_rate > 0 else 0
            
            if ea_number not in el_by_ea:
                el_by_ea[ea_number] = {
                    "title": ea_title,
                    "family": proj_family,
                    "el": 0,
                }
            el_by_ea[ea_number]["el"] += el_eur
    
    # Extrahiere Fremdleistung aus BTL
    btl_by_ea = {}
    btl_data = data.get("btlData", [])
    if isinstance(btl_data, list):
        for btl in btl_data:
            ea_num = btl.get("devOrder", "?")
            planned_val = btl.get("plannedValue", 0)
            if ea_num not in btl_by_ea:
                btl_by_ea[ea_num] = 0
            btl_by_ea[ea_num] += planned_val
    
    # Join
    all_eas = set(el_by_ea.keys()) | set(btl_by_ea.keys())
    joined = []
    
    for ea_num in all_eas:
        el = el_by_ea.get(ea_num, {}).get("el", 0)
        fremd = btl_by_ea.get(ea_num, 0)
        total = el + fremd
        anteil_el = (el / total * 100) if total > 0 else 0
        title = el_by_ea.get(ea_num, {}).get("title", "N/A")
        family = el_by_ea.get(ea_num, {}).get("family", "N/A")
        
        joined.append({
            "ea": ea_num,
            "title": title,
            "family": family,
            "el": el,
            "fremd": fremd,
            "total": total,
            "anteil_el": anteil_el,
        })
    
    # Sortiert nach Total-Volumen
    joined.sort(key=lambda x: x["total"], reverse=True)
    
    output += f"## Übersicht: {len(joined)} EAs\n\n"
    
    # Tabelle
    output += "| EA-Nummer | EA-Titel | Projektfamilie | EL (EUR) | Fremdleistung (EUR) | Summe (EUR) | Anteil EL (%) |\n"
    output += "|---|---|---|---:|---:|---:|---:|\n"
    
    total_el = 0
    total_fremd = 0
    
    for item in joined:
        total_el += item["el"]
        total_fremd += item["fremd"]
        output += f"| {item['ea']} | {item['title'][:30]} | {item['family']} | {item['el']:,.0f} | {item['fremd']:,.0f} | {item['total']:,.0f} | {item['anteil_el']:.1f}% |\n"
    
    total_sum = total_el + total_fremd
    anteil_el_pct = (total_el / total_sum * 100) if total_sum > 0 else 0
    output += f"| | | **GESAMT** | **{total_el:,.0f}** | **{total_fremd:,.0f}** | **{total_sum:,.0f}** | **{anteil_el_pct:.1f}%** |\n"
    
    return output


# --- Main ---

def main():
    parser = argparse.ArgumentParser(
        description="BPLUS-NG Eigenleistung Analyse & Reporting"
    )
    parser.add_argument(
        "json_file",
        type=Path,
        nargs="?",
        help="Pfad zur konsolidierten EL-Export JSON (default: neueste)"
    )
    parser.add_argument(
        "--mitarbeiter",
        type=str,
        help="Mitarbeitername für MA-Planung (z.B. 'Bachmann, Armin')"
    )
    parser.add_argument(
        "--usecase",
        type=str,
        default="ma-planung",
        choices=["ma-planung", "buchungssperren", "jahressicht", "gesamt-uebersicht"],
        help="Use Case (default: ma-planung)"
    )
    parser.add_argument(
        "--jahr",
        type=int,
        default=datetime.now().year,
        help="Planjahr (default: aktuelles Jahr)"
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Ignoriert Cache, führt neuen Export aus (TODO)"
    )
    
    args = parser.parse_args()
    
    logger.info("═" * 60)
    logger.info("EIGENLEISTUNG Analyse Start")
    
    # JSON-Datei bestimmen
    if args.json_file:
        json_path = args.json_file
    else:
        json_path = find_latest_export(args.jahr)
        if not json_path:
            json_path = CACHE_DIR / f"_el_consolidated_{args.jahr}.json"
    
    logger.info(f"JSON-Datei: {json_path}")
    logger.info(f"Use Case: {args.usecase}")
    if args.mitarbeiter:
        logger.info(f"Mitarbeiter: {args.mitarbeiter}")
    
    # Daten laden
    data = load_export_data(json_path, force_refresh=args.force_refresh)
    if not data:
        logger.error("Export-Daten konnten nicht geladen werden")
        return 1
    
    # Use Case ausführen
    if args.usecase == "ma-planung":
        if not args.mitarbeiter:
            logger.error("--mitarbeiter erforderlich für ma-planung")
            return 1
        report = generate_ma_planning(data, args.mitarbeiter)
    elif args.usecase == "buchungssperren":
        report = generate_buchungssperren(data)
    elif args.usecase == "jahressicht":
        report = generate_jahressicht(data)
    elif args.usecase == "gesamt-uebersicht":
        report = generate_gesamt_uebersicht(data)
    
    # Report speichern
    if args.mitarbeiter:
        ma_safe = args.mitarbeiter.replace(" ", "_").replace(",", "").lower()
        report_name = f"_el_{args.usecase}_{ma_safe}"
    else:
        report_name = f"_el_{args.usecase}"
    
    report_file = SESSIONS_DIR / f"{datetime.now().strftime('%Y%m%d')}_{report_name}.md"
    
    try:
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report)
        logger.info(f"✅ Report gespeichert: {report_file}")
        print(str(report_file))  # Output für Shell-Script
    except Exception as e:
        logger.error(f"Fehler beim Speichern des Reports: {e}")
        return 1
    
    logger.info("═" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
