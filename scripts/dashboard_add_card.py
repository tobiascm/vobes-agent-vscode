"""
Fügt eine Aura-Card-Kachel in eine bestimmte Sektion des EKEK/1 Dashboards ein.

Verwendung:
  python scripts/dashboard_add_card.py <content_json> <output_file> --marker <marker_text> --card <card_json>

Argumente:
  content_json   Pfad zur JSON-Datei mit dem Confluence-Seiteninhalt
                 (aus mcp_mcp-atlassian_confluence_get_page mit convert_to_markdown=false)
  output_file    Pfad für die modifizierte HTML-Ausgabe

Optionen:
  --marker       Eindeutiger Text einer bestehenden Kachel in der Zielsektion
                 (z.B. "EHD Chatbot (Eddy)" für KI-Tools)
  --card         JSON-String der neuen Kachel, z.B.:
                 '{"title":"Mein Tool","body":"Beschreibung","color":"#66afff",
                   "icon":"faDesktop","href":"https://example.com",
                   "hrefType":"link","hrefTarget":"_blank"}'

Sektionen und passende Marker:
  VOBES 2025                  -> "VOBES 2025 Ziele und Vision"
  VOBESplus (inkl. SYS)       -> "SYS-Flow Klickanleitung"
  Kommunikation               -> "Regeltermine"
  Prozesse und Regelungen     -> "Führungskräfteordner"
  Fahrzeugprojekte            -> "Migrationsübersicht (ausstehend)"
  Budget                      -> "Planungs-Auswertungs-Excel"
  KI-Tools und Chatbots       -> "EHD Chatbot (Eddy)"

Beispiel:
  python scripts/dashboard_add_card.py page.json out.html \
    --marker "EHD Chatbot (Eddy)" \
    --card '{"title":"Presenting","body":"Präsentationstool","color":"#66afff","icon":"faDesktop","href":"https://presenting.thecloud.vwapps.run/start","hrefType":"link","hrefTarget":"_blank"}'
"""

import argparse
import json
import sys

# Unsplash-Bilder, die im Dashboard rotierend verwendet werden
DEFAULT_IMAGES = [
    "https://images.unsplash.com/photo-1540979388789-6cee28a1cdc9?ixlib=rb-1.2.1&amp;ixid=eyJhcHBfaWQiOjEyMDd9&amp;auto=format&amp;fit=crop&amp;w=934&amp;q=100",
    "https://images.unsplash.com/photo-1571254531817-83275b6b6411?ixlib=rb-1.2.1&amp;ixid=eyJhcHBfaWQiOjEyMDd9&amp;auto=format&amp;fit=crop&amp;w=881&amp;q=100",
    "https://images.unsplash.com/photo-1483683804023-6ccdb62f86ef?ixlib=rb-1.2.1&amp;auto=format&amp;fit=crop&amp;w=975&amp;q=100",
    "https://images.unsplash.com/photo-1473580044384-7ba9967e16a0?ixlib=rb-1.2.1&amp;ixid=eyJhcHBfaWQiOjEyMDd9&amp;auto=format&amp;fit=crop&amp;w=1950&amp;q=80",
    "https://images.unsplash.com/photo-1476231682828-37e571bc172f?ixid=MnwxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8&amp;ixlib=rb-1.2.1&amp;auto=format&amp;fit=crop&amp;w=1567&amp;q=80",
    "https://images.unsplash.com/photo-1520242279429-1f64b18816ef?ixid=MnwxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8&amp;ixlib=rb-1.2.1&amp;auto=format&amp;fit=crop&amp;w=1650&amp;q=80",
]


def main():
    parser = argparse.ArgumentParser(description="Aura-Card in EKEK/1 Dashboard einfügen")
    parser.add_argument("content_json", help="Pfad zur JSON-Datei mit Confluence-Seiteninhalt")
    parser.add_argument("output_file", help="Pfad für die modifizierte HTML-Ausgabe")
    parser.add_argument("--marker", required=True, help="Eindeutiger Text einer Kachel in der Zielsektion")
    parser.add_argument("--card", required=True, help="JSON-String der neuen Kachel")
    args = parser.parse_args()

    # Card JSON parsen und validieren
    try:
        card = json.loads(args.card)
    except json.JSONDecodeError as e:
        print(f"ERROR: Ungültiges Card-JSON: {e}", file=sys.stderr)
        sys.exit(1)

    required_fields = ["title", "href", "hrefType"]
    for field in required_fields:
        if field not in card:
            print(f"ERROR: Pflichtfeld '{field}' fehlt in der Card-Definition", file=sys.stderr)
            sys.exit(1)

    # Defaults setzen
    card.setdefault("body", "")
    card.setdefault("color", "#66afff")
    card.setdefault("icon", "faLink")
    card.setdefault("hrefTarget", "_blank")
    card.setdefault("imageType", "link")
    if "image" not in card:
        # Rotierendes Bild basierend auf Titel-Hash
        img_idx = hash(card["title"]) % len(DEFAULT_IMAGES)
        card["image"] = DEFAULT_IMAGES[img_idx]

    # Confluence-Seiteninhalt laden
    with open(args.content_json, encoding="utf-8") as f:
        data = json.loads(f.read())

    result = json.loads(data["result"])
    content_html = result["metadata"]["content"]["value"]
    version = result["metadata"]["version"]
    print(f"Seiten-Version: {version}")

    # Marker suchen
    idx = content_html.find(args.marker)
    if idx == -1:
        print(f"ERROR: Marker '{args.marker}' nicht im Seiteninhalt gefunden!", file=sys.stderr)
        sys.exit(1)
    print(f"Marker '{args.marker}' gefunden an Index: {idx}")

    # Ende des cardsCollection-Arrays finden ("}]" nach Marker)
    end_bracket = content_html.find("}]", idx)
    if end_bracket == -1:
        print("ERROR: Array-Ende '}]' nach Marker nicht gefunden!", file=sys.stderr)
        sys.exit(1)
    print(f"Array-Ende an Index: {end_bracket}")

    # Prüfen ob Kachel bereits existiert
    if card["title"] in content_html:
        print(f"WARNUNG: Kachel '{card['title']}' existiert bereits auf der Seite!", file=sys.stderr)
        sys.exit(2)

    # Card-JSON für Confluence-Storage-Format serialisieren
    card_json = json.dumps(card, ensure_ascii=False, separators=(",", ":"))
    insert_str = "," + card_json

    # Einfügen nach dem letzten "}" und vor "]"
    modified = content_html[: end_bracket + 1] + insert_str + content_html[end_bracket + 1 :]

    # Verifikation
    if card["title"] not in modified:
        print(f"ERROR: Kachel '{card['title']}' nach Einfügen nicht auffindbar!", file=sys.stderr)
        sys.exit(1)

    print(f"Kachel '{card['title']}' eingefügt")
    print(f"Originallänge: {len(content_html)}")
    print(f"Neue Länge:    {len(modified)}")

    # Ausgabe schreiben
    with open(args.output_file, "w", encoding="utf-8") as f:
        f.write(modified)

    print(f"OK -> {args.output_file}")


if __name__ == "__main__":
    main()
