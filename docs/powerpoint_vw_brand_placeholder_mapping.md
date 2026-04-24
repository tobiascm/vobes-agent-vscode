# Volkswagen Brand: Placeholder-Mapping (COM-Auswertung)

Stand: 2026-04-25  
Quelle: `Volkswagen Brand.potx` direkt per PowerPoint COM ausgelesen.

## Kernerkenntnis

Im Layout **`Titel und Text`** gibt es **zwei** Text-Placeholder mit `phType=2`:

1. oberes Feld (eher Untertitel/Lead): `top=48.9`, `height=28.4`
2. Haupttextfeld: `top=108.4`, `height=124.4`

Wenn nur "erstes `phType=2`" gewählt wird, landet Inhalt im falschen Feld.

## Auszug Layout-Felder

### `Titelfolie weißer Text`

| Shape | phType | Left | Top | Width | Height | Bedeutung |
|---|---:|---:|---:|---:|---:|---|
| `Titel 1` | 3 | 111.5 | 198.0 | 737.0 | 52.3 | Titel |
| `Subtitle 2` | 4 | 111.5 | 257.6 | 737.0 | 52.3 | Untertitel |
| `Text Placeholder 5` | 2 | 23.6 | 504.2 | 117.9 | 14.5 | Metadaten (unten links) |
| `Text Placeholder 14` | 2 | 426.0 | 504.2 | 108.1 | 14.5 | Metadaten (unten mittig) |

### `Titel und Text`

| Shape | phType | Left | Top | Width | Height | Bedeutung |
|---|---:|---:|---:|---:|---:|---|
| `Title 1` | 1 | 23.6 | 20.5 | 912.8 | 28.4 | Titel |
| `Textplatzhalter 7` | 2 | 23.6 | 48.9 | 912.8 | 28.4 | Lead/Untertitel |
| `Text Placeholder 7` | 2 | 23.6 | 108.4 | 912.8 | 124.4 | Haupttext |
| `Footer Placeholder 6` | 15 | 211.5 | 515.9 | 623.6 | 12.1 | Footer |
| `Slide Number Placeholder 9` | 13 | 149.4 | 515.9 | 59.5 | 12.1 | Seitennummer |

## Empfehlung

Mapping pro **Vorlage + Layout** verwenden (nicht nur pro Vorlage).  
Konfigurierbare Slots:

- `title`
- `subtitle`
- `main_text`
 - `left_text` / `right_text` (Zweispalter)
 - `image` (Bild-Placeholder, z. B. `phType=18`)
 - `table` (echte PPT-Tabelle; falls kein `phType=12` vorhanden ist, in den groessten Content-Bereich einsetzen)

mit Regeln auf `placeholder_type`, `top`, `height`, optional `exclude_name_regex`.
