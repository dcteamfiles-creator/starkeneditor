"""
Build the static base PDF by overlaying the never-changing components
1 + 3 + 4 + 5 + 7  →  public/assets/base.pdf

The base contains: background gradient, watermark, blue title-pill, white textfield,
red wax seal, trustbar at bottom. Everything else (text, names, signatures, sponsor,
QR, schirmherren, content) is drawn at render time.
"""
import os
import sys
from pathlib import Path

import pikepdf

ROOT = Path(__file__).resolve().parent.parent
COMP = ROOT / "public" / "assets" / "sx-components"
OUT  = ROOT / "public" / "assets" / "base.pdf"

# Order matters: bottom layer first
LAYERS = [
    "1 Background.pdf",
    "4 Watermark.pdf",
    "3 Title.pdf",
    "7 WhitebackgroundTextfield_redwax.pdf",
    "5 Trustelements.pdf",
]


def main():
    base = pikepdf.open(COMP / LAYERS[0])
    base_page = base.pages[0]

    for layer_name in LAYERS[1:]:
        layer = pikepdf.open(COMP / layer_name)
        layer_page = layer.pages[0]
        base_page.add_overlay(layer_page)

    base.save(OUT)
    print(f"Wrote {OUT}  ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
