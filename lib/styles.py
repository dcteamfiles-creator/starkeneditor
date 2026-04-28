"""
Stärken-Exposé style tokens — extracted from Beispiel-PDF (01 Example.pdf).
All colors RGB. Print/digital target: RGB.
"""
from reportlab.lib.colors import Color


def rgb(hex_str: str) -> Color:
    h = hex_str.lstrip("#")
    return Color(int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255)


# Brand palette extracted from the example
COLOR_NAVY        = rgb("#1b3f6a")   # primary dark blue: titles, names, section bold heads, labels
COLOR_TEAL        = rgb("#3ea1d7")   # secondary cyan-blue: english subtitles after "//"
COLOR_CORAL       = rgb("#d25066")   # red/coral: "//" separator, accents
COLOR_BODY        = rgb("#231f20")   # body text gray-black
COLOR_WAX_RED     = rgb("#b7112a")   # wax seal deep red
COLOR_WHITE       = rgb("#ffffff")
COLOR_TITLE_BG    = rgb("#1b3f6a")   # blue title block bg

# Fonts (registered names match Type-1 PostScript names that pdf-lib/reportlab use)
FONT_HEAD_BOLD     = "Montserrat-Bold"
FONT_HEAD_SEMI     = "Montserrat-SemiBold"
FONT_HEAD_REG      = "Montserrat-Regular"
FONT_BODY          = "OpenSans-Regular"

# Fallbacks if Montserrat/OpenSans aren't bundled (locally available)
FALLBACK_BOLD = "Poppins-Bold"
FALLBACK_SEMI = "Poppins-Medium"
FALLBACK_REG  = "Poppins-Regular"
FALLBACK_BODY = "DejaVuSans"


# Font sizes (pt) — derived from bbox heights * 0.85 cap-height ratio
SIZE_TITLE_BIG       = 17.0   # "Stärken-Exposé" in title block
SIZE_NAME_BIG        = 16.0   # "First Name Last Name" header
SIZE_SUBTITLE        = 10.0   # "Basierend auf Multi-Source-Feedback / gemäß ..."
SIZE_LABEL_TINY      = 7.0    # "ID-Type-Person:"
SIZE_META_LABEL      = 7.5    # "Dokumententyp:" bold labels
SIZE_META_VALUE      = 7.5    # "Offizielles Gutachten" body
SIZE_HEADER_HUGE     = 17.0   # "Firstname - Ultrashort affirmation Header"
SIZE_SECTION_HEAD    = 8.0    # "Positionierung // Authentic Value Proposition"
SIZE_BODY            = 7.0    # all 7 textblocks
SIZE_DATE_LABEL      = 7.5
SIZE_DATE_VALUE      = 7.5
SIZE_SCHIRM_LABEL    = 8.0    # "Wissenschaftliche Schirmherrschaft"
SIZE_SCHIRM_NAME     = 8.0    # "Prof. Dr. Claudia Gerhardt"
SIZE_SCHIRM_TITLE    = 7.5    # title of schirmherr
SIZE_QR_LABEL        = 7.5    # "QR-Code - für Echtzeit-Verifizierung:"
SIZE_STATUS          = 7.5    # "Status: validiert..."
