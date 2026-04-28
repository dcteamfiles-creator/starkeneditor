"""
SX Layout — Hybrid: Original-Positionen + Spec-Constraints + 0.9° Rotation.

KOORDINATEN-SYSTEM:
  - Innen: PDF-Punkte (1 pt = 1/72 inch). Top-left origin (y wächst nach unten).
  - Conversion: 1 mm = 2.8346 pt.

CONTAINER (White Field):
  - 170 × 257 mm, zentriert auf A4.
  - Page-Position: top-left (20, 20) mm.
  - Center: (105, 148.5) mm.
  - Rotation: 0.9° CCW um Container-Center → angewendet auf ALLE Container-Inhalte.

GRID (innerhalb Container):
  - 2 Spalten à 80 mm, 10 mm Gutter.
  - Linke Spalte: container-X 0..80 mm (page-X 20..100 mm).
  - Rechte Spalte: container-X 90..170 mm (page-X 110..190 mm).

SAFETY:
  - Bottom-Boundary: page-Y ≤ 260 mm.
  - Min-Padding zwischen Boxen: 5 mm.
"""
MM_TO_PT = 72.0 / 25.4
mm = lambda v: v * MM_TO_PT

PAGE_W_MM, PAGE_H_MM = 210.0, 297.0
PAGE_W = PAGE_W_MM * MM_TO_PT
PAGE_H = PAGE_H_MM * MM_TO_PT

# Container
CONTAINER_X_MM = 20.0
CONTAINER_Y_MM = 20.0
CONTAINER_W_MM = 170.0
CONTAINER_H_MM = 257.0
CONTAINER_CX_MM = 105.0
CONTAINER_CY_MM = 148.5
CONTAINER_ROTATION_DEG = 0.9   # CCW positive

# Grid (page-absolute X positions in mm)
LEFT_COL_X_MM   = 20.0   # = CONTAINER_X
COL_W_MM        = 80.0
GUTTER_MM       = 10.0
RIGHT_COL_X_MM  = LEFT_COL_X_MM + COL_W_MM + GUTTER_MM   # = 110

BOTTOM_BOUNDARY_MM = 260.0


# ─── PAGE-ABSOLUTE Y-POSITIONEN (mm, top-left origin) ─────────────────────
# Top-Meta (page-globale, NICHT mit-rotiert)
TOP_META_NAME_LABEL_Y_MM = 8.5
TOP_META_NAME_Y_MM       = 12.0
TOP_META_SUBTITLE_1_Y_MM = 19.0
TOP_META_SUBTITLE_2_Y_MM = 22.5
TOP_META_LABEL_X_MM      = 5.5

# Linke Meta-Spalte
META_LEFT_X_MM = 7.5
META_LEFT_Y_MM = (33, 36.5, 40, 43.5, 47, 50.5, 54)   # Dokumententyp, val1, val2, Instanz, val, ZID, val

# Mittlere Meta-Spalte (Beschreibung)
META_MID_X_MM = 78.0
META_MID_Y_START_MM = 33.0
META_MID_LINE_H_MM = 3.2

# Rechts: Status + QR
META_RIGHT_X_MM   = 134.0
STATUS_LINE1_Y_MM = 33.0
STATUS_LINE2_Y_MM = 36.5
QR_X_MM           = 134.0
QR_Y_MM           = 41.0
QR_SIZE_MM        = 18.0
QR_LABEL_X_MM     = 156.0
QR_LABEL_Y_MM     = (41, 44.5, 48)

# Sponsor pill (in base.png integriert) - x≈383-560pt, y=50-86pt

# Container content (Y in mm page-absolute)
HEADER             = dict(x=20,  y=87,  w=170, h=11)        # full width
SEC_POS_HEAD       = dict(x=20,  y=105, w=170, h=4.5)
SEC_POS_BODY       = dict(x=20,  y=110, w=170, h=12)        # full width

SEC_ALL_HEAD       = dict(x=20,  y=125, w=80,  h=4.5)
SEC_ALL_BODY       = dict(x=20,  y=130, w=80,  h=27)        # links: 27mm = 9 Zeilen
SEC_FUE_HEAD       = dict(x=110, y=125, w=80,  h=4.5)
SEC_FUE_BODY       = dict(x=110, y=130, w=80,  h=22)        # rechts: kürzer

SEC_EIN_HEAD       = dict(x=20,  y=160, w=80,  h=4.5)
SEC_EIN_BODY       = dict(x=20,  y=165, w=80,  h=27)
SEC_BEL_HEAD       = dict(x=110, y=160, w=80,  h=4.5)
SEC_BEL_BODY       = dict(x=110, y=165, w=80,  h=22)

SEC_ZUK_HEAD       = dict(x=20,  y=195, w=80,  h=4.5)
SEC_ZUK_BODY       = dict(x=20,  y=200, w=80,  h=30)        # links darf am tiefsten
SEC_UNT_HEAD       = dict(x=110, y=195, w=80,  h=4.5)
SEC_UNT_BODY       = dict(x=110, y=200, w=72,  h=20)        # rechts: schmal (Wachs-Vermeidung)

DATE_BLOCK         = dict(x=110, y=225, w=80, h=8)

# ─── SCHIRMHERREN (page-globale, NICHT mit-rotiert) ───────────────────────
SCHIRM_LABELS_Y_MM = 234.0
SCHIRM_COL_CX_MM   = (42.0, 105.0, 168.0)
SCHIRM_LABEL_TEXT  = ("Wissenschaftliche Schirmherrschaft",
                      "Wissenschaftliche Schirmherrschaft",
                      "Herausgebende Instanz")
SIGN_BOX_MM = {
    0: (15.0,  237.0, 60.0,  248.0),
    1: (78.0,  237.0, 132.0, 248.0),
    2: (143.0, 237.0, 195.0, 248.0),
}
SCHIRM_NAME_Y_MM   = 250.5
SCHIRM_TITLE_Y_MM  = 254.5
LOGO_BOX_MM = {
    0: (18.0,  259.0, 65.0,  268.0),
    1: (82.0,  259.0, 128.0, 268.0),
    2: (147.0, 259.0, 195.0, 268.0),
}


def page_pt(x_mm, y_mm):
    """mm (page-absolute) → pt (page-absolute, top-left)."""
    return (x_mm * MM_TO_PT, y_mm * MM_TO_PT)
