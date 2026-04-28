"""Full test render with all default schirmherren signatures + Stärkenkompass logo."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.pdf_renderer import render_to_file

DEF = ROOT / "public" / "assets" / "defaults"

payload = {
    "person_name": "Louisa-Michelle Eckhoff",
    "header": "Michelle - die engagierte Entscheiderin",
    "pruefnummer": "EU-DE-2026-7408-YC",
    "feedback_count": 3,
    "verify_url": "https://sx.staerkenkompass.de/verify.html?id=EU-DE-2026-7408-YC",
    "date": "23.04.2026",
    "sponsor_logo_path": str(DEF / "sponsor_TK_compact.png"),
    "sponsor_name": "Die Techniker",
    "sections": {
        "positionierung": (
            "Professionelle Netzwerke und tiefe Menschenkenntnis bilden den Kern ihres Wirkens. "
            "Michelle Eckhoff nutzt ihre beratende Kompetenz und hohe Selbstmotivation, um "
            "Kooperationen zielgerichtet zu entwickeln. Sie verbindet Fachwissen mit einer klaren "
            "Entscheidungskraft für belastbare Ergebnisse."
        ),
        "alleinstellung": (
            "Ihr Vorteil ist die Verbindung von leidenschaftlicher Energie und bodenständiger "
            "Disziplin. Sie agiert zugleich nahbar und durchsetzungsstark, wodurch sie komplexe "
            "Dynamiken intuitiv steuert. Diese Präsenz gepaart mit verantwortungsbewusster Haltung "
            "macht sie zur natürlichen Leitfigur."
        ),
        "fuehrungsstil": (
            "Sie führt durch ein engagiertes Vorbild und eine aufmerksame, fürsorgliche "
            "Grundhaltung. Ihr Leadership Impact basiert auf einer mitreißenden Dynamik und der "
            "Fähigkeit, Talente durch Wertschätzung freizusetzen. Sie motiviert Teams zu "
            "diszipliniertem und verantwortungsbewusstem Handeln."
        ),
        "einsatzgebiete": (
            "Sie ist die organisationsstarke Gestalterin für die Strukturierung komplexer "
            "Projekte. Ihre Stärken liegen im Aufbau von Netzwerken und der überzeugenden "
            "Präsentation von Lösungen. Partner profitieren von ihrer Problemlösungsfähigkeit und "
            "ihrem strukturierten Vorgehen in dynamischen Prozessen."
        ),
        "belastbarkeit": (
            "Optimismus und hohe Belastbarkeit machen sie zum stabilen Ankerpunkt unter Hochdruck. "
            "Sie bleibt energievoll und sichert durch ihre zuverlässige, strukturierte Art die "
            "Handlungsfähigkeit des Teams. Ihre reflektierte Art stabilisiert das Umfeld in "
            "kritischen Phasen."
        ),
        "zukunftskompetenz": (
            "Intuitive Menschenkenntnis und reflektierte Urteilskraft sichern ihre Relevanz in "
            "einer digitalisierten Arbeitswelt. Michelle Eckhoff nutzt soziale Intelligenz, um "
            "Netzwerke organisch zu moderieren. Ihre authentische Herzlichkeit schafft eine "
            "Vertrauensbasis, die technologische Automatisierung nicht ersetzen kann."
        ),
        "unternehmenskultur": (
            "Sie bereichert Kulturen, die auf Ehrlichkeit, Bodenständigkeit und gegenseitige "
            "Hilfsbereitschaft setzen. Ihr aufgeschlossenes Wesen ermöglicht es ihr, sofort "
            "organische Bindungen in Teams aufzubauen. Sie stärkt Organisationen durch "
            "sympathische Verlässlichkeit und ein integrierendes Miteinander."
        ),
    },
    "schirmherren": [
        {
            "name": "Prof. Dr. Claudia Gerhardt",
            "title_lines": ["Leiterin Psychology School /",
                            "Studiendekanin Wirtschaftspsychologie"],
            "signature_path": str(DEF / "signature_CL_Gerhardt.png"),
            "logo_path": str(DEF / "logo_fresenius.png"),
        },
        {
            "name": "Dr. Nicolas Bogs",
            "title_lines": ["TANGRON Talent & Insight"],
            "signature_path": str(DEF / "signature_NB_Bogs.png"),
            "logo_path": str(DEF / "logo_tangron.png"),
        },
        {
            "name": "Torben Schacht",
            "title_lines": ["Geschäftsführender Gesellschafter"],
            "signature_path": str(DEF / "signature_TS_Schacht.png"),
            "logo_path": str(DEF / "staerkenkompass_logo.png"),
        },
    ],
}

out = ROOT / "debug-renders" / "test_full.pdf"
render_to_file(payload, out, with_bleed=False)
print(f"Wrote {out}")

# Render preview
import pypdfium2 as pdfium
pdf = pdfium.PdfDocument(str(out))
img = pdf[0].render(scale=2).to_pil()
img.save(ROOT / "debug-renders" / "test_full.png")
print("Wrote test_full.png")
