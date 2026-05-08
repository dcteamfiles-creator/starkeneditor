"""
Claude Vision + Text Generation für SX Editor.

Stdlib-only HTTP (urllib) — kein 'anthropic' SDK nötig.
PDF-Support via pypdfium2 (PDF → erste Seite als PNG).

Funktionen:
  extract_from_image(image_bytes, mime_type) -> dict
  extract_from_pdf(pdf_bytes) -> dict
  generate_section_texts(strengths_per_section, vorname, nachname, system_prompt=None) -> dict
  generate_header_alternatives(strengths_per_section, vorname) -> list[dict]
  smart_default_mapping(extracted) -> dict
"""
from __future__ import annotations

import base64
import io
import json
import os
import urllib.error
import urllib.request
from pathlib import Path


# ─── ENV LOADING ──────────────────────────────────────────────────────────
def _load_env():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

_load_env()

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-5-20250929"


def _api_call(payload: dict, timeout: int = 90) -> dict:
    if not API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY nicht gesetzt — bitte in Render Environment hinterlegen.")
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Anthropic API HTTP {e.code}: {body[:300]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Anthropic API Netzwerk-Fehler: {e}") from e


def _extract_text_from_response(resp: dict) -> str:
    blocks = resp.get("content", [])
    for b in blocks:
        if b.get("type") == "text":
            return b.get("text", "")
    return ""


def _extract_json_from_text(text: str):
    """Robustes JSON-Parsing aus LLM-Output."""
    text = text.strip()
    # Markdown-Codeblöcke entfernen
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    # Erste { oder [ bis letztes } oder ] extrahieren (entfernt führende/trailing Erklärungen)
    if text and text[0] not in "{[":
        # Suche das erste { oder [
        for i, c in enumerate(text):
            if c in "{[":
                text = text[i:]
                break
    if text and text[-1] not in "}]":
        for i in range(len(text) - 1, -1, -1):
            if text[i] in "}]":
                text = text[:i+1]
                break
    return json.loads(text)


# ─── 1. VISION ─────────────────────────────────────────────────────────────
VISION_PROMPT = """\
Du analysierst ein Stärkenkompass-Auswertungs-Bild (Wortwolke mit Stärken in 4 Dimensionen).

Die 4 Dimensionen heißen:
- AE = Auftreten und Erscheinung
- ED = Einstellung und Denken
- SH = Sprechen und Handeln
- WK = Wissen und Können

Pro Dimension werden bis zu 10 Stärken angezeigt. Die Größe der Schrift gibt das Ranking
wieder: GROSSE Wörter = Top-Stärken, kleinere = niedriger im Ranking.

Identifiziere ALLE sichtbaren Stärken pro Dimension und liste sie in absteigender
Reihenfolge ihrer visuellen Größe (= Wichtigkeit).

Antworte NUR mit gültigem JSON:

{
  "vorname": "<Vorname falls erkennbar, sonst leer>",
  "nachname": "<Nachname falls erkennbar, sonst leer>",
  "AE": ["staerke1", "staerke2", ...],
  "ED": ["staerke1", "staerke2", ...],
  "SH": ["staerke1", "staerke2", ...],
  "WK": ["staerke1", "staerke2", ...]
}

Keine Markdown-Codeblöcke, nur das JSON."""


def extract_from_image(image_bytes: bytes, mime_type: str = "image/png") -> dict:
    img_b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    payload = {
        "model": MODEL,
        "max_tokens": 1024,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image",
                 "source": {"type": "base64", "media_type": mime_type, "data": img_b64}},
                {"type": "text", "text": VISION_PROMPT},
            ],
        }],
    }
    resp = _api_call(payload, timeout=90)
    data = _extract_json_from_text(_extract_text_from_response(resp))
    return {
        "vorname": data.get("vorname", "").strip(),
        "nachname": data.get("nachname", "").strip(),
        "AE": list(data.get("AE", [])),
        "ED": list(data.get("ED", [])),
        "SH": list(data.get("SH", [])),
        "WK": list(data.get("WK", [])),
    }


def extract_from_pdf(pdf_bytes: bytes) -> dict:
    """Konvertiere PDF erste Seite zu PNG, dann via Vision."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        raise RuntimeError("pypdfium2 ist nicht installiert — bitte requirements.txt prüfen.")
    pdf = pdfium.PdfDocument(io.BytesIO(pdf_bytes))
    if len(pdf) == 0:
        raise RuntimeError("PDF ist leer.")
    page = pdf[0]
    img = page.render(scale=2).to_pil()  # ~150 DPI, gut für Vision
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return extract_from_image(buf.getvalue(), mime_type="image/png")


# ─── 2. TEXT GENERATION ────────────────────────────────────────────────────
SECTION_LABELS = {
    "positionierung":     ("Positionierung",                   "Authentic Value Proposition"),
    "alleinstellung":     ("Alleinstellung",                   "Unfair Advantage"),
    "fuehrungsstil":      ("Führungsstil",                     "Leadership-Impact-Matrix"),
    "einsatzgebiete":     ("Einsatzgebiete",                   "Areas of Personal excellence & flow"),
    "belastbarkeit":      ("Belastbarkeit",                    "Resilience-Profile"),
    "zukunftskompetenz":  ("Zukunftskompetenz (KI-Resilienz)", "Future Skills"),
    "unternehmenskultur": ("Unternehmenskultur",               "Culture-Fit Analysis"),
}

SECTION_LIMITS = {
    "positionierung":     400,
    "alleinstellung":     320,
    "fuehrungsstil":      280,
    "einsatzgebiete":     320,
    "belastbarkeit":      280,
    "zukunftskompetenz":  360,
    "unternehmenskultur": 280,
}

# Default-System-Prompt (vom User editierbar im Editor)
DEFAULT_SYSTEM_PROMPT = """Du bist ein Experte für strategisches Personal-Branding und "Strengths-Storytelling". Deine Aufgabe ist es, ein validiertes Fremdbild-Gutachten für eine Person zu erstellen.

Leitplanken für das Ergebnis:

1. Vermeide Redundanzen in den sieben Kategorien — Teile die vorhandenen Stärken optimal auf die sieben Felder auf, um die Person so zutreffend wie möglich zu beschreiben.
2. Länge: ca. 40 Wörter plus minus 5.
3. Essenz: Verdichte die Schnittmenge aus Wissen, Handeln und Auftreten.
4. Tonalität: Professionell, glaubwürdig, menschlich und "emotional aktivierend".
5. Strategie: Vermeide leere Floskeln. Nutze die Daten, um ein hohes Maß an Glaubwürdigkeit zu vermitteln.
6. Vorgabe: Schreibe in der 3. Person.
7. Kein Bullshit-Bingo mit vielen Adjektiven und Buzzwords, die nach viel klingen, aber nichts aussagen.
8. Erzähle, welche Vorteile einzelne Stärken für die Person entfalten und welche emotionalen Wirkungen die Person durch ihre Stärken erzielt.
9. Das Element "Positionierung" ist die Zusammenfassung/Bündelung der sechs anderen Elemente — Verdichtung der aggregierten Fremdbild-Feedbacks auf ihre Essenz (Elevator Pitch). Die Schnittmenge aus Fähigkeiten, Beziehungsstärke und Mindset. Nutzen extern: valide und strategische Positionierung. Nutzen intern: emotionale Selbstwertbestätigung und optimierte Selbstführung.

10. DIMENSIONS-DISZIPLIN (Hard Rule): Die Stärken stammen aus 4 Dimensionen — AE (Auftreten/Erscheinung), ED (Einstellung/Denken), SH (Sprechen/Handeln), WK (Wissen/Können). Stärken aus der Dimension AE (z. B. "präsent", "dynamisch", "lächeln", "kultiviert", "natürlich", "strahlend", "lebendig", "sportlich") sind ausschließlich für die Sektionen "Positionierung" und "Führungsstil" zulässig. Sie dürfen NIEMALS in Alleinstellung, Einsatzgebiete, Belastbarkeit, Zukunftskompetenz oder Unternehmenskultur erscheinen. Alleinstellung baut sich aus seltenen Kombinationen der Substanz-Dimensionen WK + ED. Einsatzgebiete = WK. Belastbarkeit = ED. Zukunftskompetenz = WK + ED. Unternehmenskultur = ED + SH.

11. FACHSPRACHE-LIMIT (Hard Rule): Maximal ZWEI Fachbegriffe pro gesamtem SX (über alle 7 Sektionen zusammen). Verboten in Häufung: "pivoting", "high-stakes", "laterale Allianzen", "Stakeholder-Choreografie", "Resilienz-Architektur", "Stakeholder-Orchestrierung", "Transformation-Pivot". Substanz vor Buzzword. Wenn ein deutsches Wort denselben Inhalt trägt — deutsches Wort wählen. Anglizismen sind die Ausnahme, nicht die Regel.

12. STÄRKEN-LITERAL (Hard Rule): Die im Stärkenkompass-Wiki definierten Wortlaute (z. B. "Sicherheit gebend", "schnell im Kopf", "Talente freisetzen", "Innovationen beschleunigen", "Netzwerke gestalten", "behält den Überblick", "argumentationsstark", "konzeptionsstark", "durchsetzungsstark", "organisationsstark", "kundenorientiert", "vertrauenswürdig") sind als Substantivierungen oder feststehende Phrasen zu respektieren. Nicht umformulieren in "stark im Argumentieren" — sondern direkt: "argumentationsstark". Wo das Wiki ein Substantiv-Verb-Paar nutzt ("Talente freisetzen"), darf es als Halbsatz im Text bleiben.

13. SCHNITTMENGEN-LOGIK (Hard Rule): Jede Sektion soll 2–3 fokussierte Stärken in Schnittmenge bündeln, nicht alle 4–6 verfügbaren auflisten. Lieber zwei Stärken in einem präzisen Satz verzahnt als sechs in einer Aufzählung verloren.

Strukturelle Vorgaben für "Positionierung":
- Essenz-Regel: max. 45 Wörter.
- 3-Säulen-Integration: Schnittmenge aus Fach-Exzellenz (Professionalität), Resonanz-Fähigkeit (Beziehung) und Wachstums-Orientierung (Mindset).
- Wirkungs-Fokus: Schreibe nicht, was die Person ist, sondern was sie im System bewirkt. Nutze aktive Transformationstermini (z. B. "aktiviert", "navigiert", "strukturiert", "katalysiert").
- Tonalität: Analytisch-präzise, frei von Superlativen und werblichen Floskeln. Es muss klingen wie ein unbestechliches Experten-Urteil.

Psychologisches Ziel:
- Extern: Der Leser muss denken: "Diese spezifische Wirkungslücke in meiner Organisation ist mit diesem Profil geschlossen."
- Intern: Die Person muss sich in ihrer tiefsten Wirksamkeit erkannt fühlen und daraus Kraft für die Selbstführung ziehen.

Formel-Vorschlag (optional): "[NAME] ist der/die [ADJEKTIV + SUBSTANTIV], der/die durch [STÄRKE A & B] komplexe [Herausforderung] in nachhaltige [Resultat/Kultur] transformiert."
"""


# ─── WIKI LOADER ────────────────────────────────────────────────────────────
_WIKI_CACHE: dict | None = None

def _wiki() -> dict:
    """Lazy-load das Stärken-Wiki (kanonische Definitionen + Stilkanon)."""
    global _WIKI_CACHE
    if _WIKI_CACHE is not None:
        return _WIKI_CACHE
    p = Path(__file__).resolve().parent / "strengths_wiki.json"
    if not p.exists():
        _WIKI_CACHE = {}
        return _WIKI_CACHE
    try:
        _WIKI_CACHE = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        _WIKI_CACHE = {}
    return _WIKI_CACHE


def _wiki_lookup(strength: str) -> dict | None:
    """Finde Wiki-Eintrag — robust gegen Kapitalisierung, Bindestriche, Umlaute."""
    if not strength:
        return None
    key = (
        strength.lower()
        .replace("­", "")  # soft hyphen
        .replace("-", "")
        .replace(" ", "")
        .replace("ü", "ue").replace("ö", "oe").replace("ä", "ae").replace("ß", "ss")
    )
    return _wiki().get(key)


def _build_data_block(section_strengths: dict, vorname: str, nachname: str) -> str:
    """Datenteil des Prompts — wird KONKATENIERT, nicht als Format-String genutzt.
    Injiziert für JEDE in einer Sektion gelistete Stärke ihre kanonische Wiki-Kurzdefinition,
    damit Claude den Stärkenkompass-Stil und die exakte Bedeutung kennt."""
    lines = []
    wiki_used: set[str] = set()
    for key, (de, en) in SECTION_LABELS.items():
        strengths = section_strengths.get(key, [])
        limit = SECTION_LIMITS[key]
        lines.append(f"- {de} // {en} (max {limit} Zeichen):")
        if strengths:
            lines.append(f"  Fokus-Stärken: {', '.join(strengths)}")
            # Wiki-Definitionen für diese Stärken anhängen
            for s in strengths:
                entry = _wiki_lookup(s)
                if entry and entry["name"] not in wiki_used:
                    wiki_used.add(entry["name"])
                    short = entry["short"][:600]
                    lines.append(f"    · WIKI \"{entry['name']}\": {short}")
        else:
            lines.append("  Fokus-Stärken: (keine ausgewählt — frei generieren)")
    block = "\n".join(lines)

    # Output-Format-Spezifikation (separat, NICHT vom User-Prompt-Format-String betroffen)
    output_spec = '''
Antworte NUR mit gültigem JSON in genau diesem Format (keine Markdown-Codeblöcke):

{"positionierung": "<text>", "alleinstellung": "<text>", "fuehrungsstil": "<text>", "einsatzgebiete": "<text>", "belastbarkeit": "<text>", "zukunftskompetenz": "<text>", "unternehmenskultur": "<text>"}'''

    style_anker = (
        "STIL-ANKER (aus dem Stärkenkompass-Wiki): Die WIKI-Definitionen oben zeigen "
        "den exakten Stärkenkompass-Schreibstil — nüchtern, substantivierend, präzise. "
        "Übernimm die literalen Wortlaute der Stärken (z. B. \"argumentationsstark\" "
        "nicht \"stark im Argumentieren\"). Verwende die WIKI-Definitionen als "
        "semantischen Anker — nicht abschreiben, sondern in das Fremdbild-Gutachten "
        "in der 3. Person verdichten."
    )

    return (
        f"Person: {vorname} {nachname}\n\n"
        f"Sektionen mit fokussierten Stärken (inkl. WIKI-Definition zur Bedeutung):\n{block}\n\n"
        f"{style_anker}\n\n"
        f"Schreibe für JEDE der 7 Sektionen einen passenden Text gemäß den Leitplanken oben.\n"
        f"{output_spec}"
    )


def generate_section_texts(
    section_strengths: dict[str, list[str]],
    vorname: str = "",
    nachname: str = "",
    system_prompt: str | None = None,
) -> dict[str, str]:
    """Generiere 7 Sektions-Texte. system_prompt ist der User-editierbare Anweisungstext."""
    sys_part = (system_prompt or DEFAULT_SYSTEM_PROMPT).strip()
    data_part = _build_data_block(section_strengths, vorname or "(unbekannt)", nachname or "")

    full_prompt = sys_part + "\n\n---\n\nKonkrete Aufgabe:\n\n" + data_part

    payload = {
        "model": MODEL,
        "max_tokens": 2500,
        "messages": [{"role": "user", "content": full_prompt}],
    }
    resp = _api_call(payload, timeout=120)
    data = _extract_json_from_text(_extract_text_from_response(resp))
    out = {}
    for key in SECTION_LABELS:
        v = (data.get(key) or "").strip()
        out[key] = v[:SECTION_LIMITS[key]]
    return out


# ─── 3. HEADER ALTERNATIVES ─────────────────────────────────────────────────
def generate_header_alternatives(
    section_strengths: dict[str, list[str]],
    vorname: str,
) -> list[dict]:
    all_strengths = []
    seen = set()
    for sk in SECTION_LABELS:
        for s in section_strengths.get(sk, []):
            if s not in seen:
                seen.add(s)
                all_strengths.append(s)

    # Concat-only, no .format() to avoid User-Prompt-Crash
    prompt = (
        f"Schreibe 3 Vorschläge für den Affirmation-Header eines Stärken-Exposés (SX).\n"
        f"Format jedes Vorschlags: \"Vorname — kurze, prägnante Beschreibung mit 2-4 Wörtern\".\n"
        f"Max 70 Zeichen pro Header.\n\n"
        f"Vorname: {vorname or 'Person'}\n"
        f"Top-Stärken: {', '.join(all_strengths[:12]) if all_strengths else '(keine)'}\n\n"
        f"3 Stilrichtungen:\n"
        f"1. STIL \"descriptiv\": z. B. \"Vorname — der inspirierende Strategie-Macher\"\n"
        f"2. STIL \"attribut\": z. B. \"Vorname — argumentationsstark & charismatisch\"\n"
        f"3. STIL \"metaphorisch\": z. B. \"Vorname — Brücke zwischen Idee und Markt\"\n\n"
        f"Antworte NUR mit gültigem JSON-Array:\n"
        f'[{{"style":"descriptiv","text":"..."}},{{"style":"attribut","text":"..."}},{{"style":"metaphorisch","text":"..."}}]\n'
        f"Keine Markdown-Codeblöcke."
    )
    payload = {
        "model": MODEL,
        "max_tokens": 512,
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = _api_call(payload, timeout=60)
    data = _extract_json_from_text(_extract_text_from_response(resp))
    if not isinstance(data, list):
        return []
    return [{"style": d.get("style", "?"), "text": d.get("text", "").strip()[:80]} for d in data[:3]]


# ─── 4. SMART DEFAULT MAPPING ───────────────────────────────────────────────
# Heuristik: welche Dimensionen liefern Material für welche Sektion?
# AE (Auftreten/Erscheinung) ist NICHT Substanz — nur in Positionierung & Führungsstil
# zulässig, weil dort Wirkung nach außen Teil des Bildes ist.
# Alleinstellung, Einsatzgebiete, Belastbarkeit, Zukunftskompetenz, Unternehmenskultur
# müssen aus Substanz-Dimensionen WK / ED / SH gespeist werden.
DIMENSION_TO_SECTION = {
    "positionierung":     ["WK", "ED", "SH"],   # Synthese — keine reine AE
    "alleinstellung":     ["WK", "ED"],         # Substanz pur (kein AE!)
    "fuehrungsstil":      ["SH", "AE"],         # Wirkung nach außen — AE darf hier
    "einsatzgebiete":     ["WK"],               # Können / Wissen
    "belastbarkeit":      ["ED"],               # Innere Haltung
    "zukunftskompetenz":  ["WK", "ED"],         # Lernen + Denken (kein SH-Vorrang mehr)
    "unternehmenskultur": ["ED", "SH"],         # Werte + Interaktion (kein AE)
}


# Reihenfolge für die Stärken-Vergabe: erst die Sektionen mit der schmalsten
# Dimensions-Auswahl bekommen ihre Top-Stärken, danach die breiteren. So vermeiden wir,
# dass Positionierung (nimmt aus WK+ED+SH) bereits alle WK-Top-Stärken aufgebraucht hat,
# bevor Einsatzgebiete (nur WK) drankommt.
SECTION_PICK_ORDER = (
    "einsatzgebiete",     # WK pur — bekommt zuerst die WK-Spitze
    "belastbarkeit",      # ED pur — bekommt zuerst die ED-Spitze
    "fuehrungsstil",      # SH+AE — SH-Spitze + erste AE
    "alleinstellung",     # WK+ED — verbleibende Substanz-Spitze
    "zukunftskompetenz",  # WK+ED — nächste Substanz-Schicht
    "unternehmenskultur", # ED+SH — verbleibende
    "positionierung",     # WK+ED+SH — Synthese, darf wiederverwenden
)


def smart_default_mapping(extracted: dict, max_per_section: int = 3) -> dict[str, list[str]]:
    """Verteilt die Top-Stärken pro Dimension auf die 7 Sektionen — ohne dass
    sich die Sektionen ihre Top-Picks gegenseitig wegnehmen.

    Strategie: Wir gehen die Sektionen in `SECTION_PICK_ORDER` durch und entfernen
    bereits vergebene Stärken aus dem Pool — bis auf "positionierung", die als
    Synthese die Top-Stärken wiederverwenden darf.
    """
    used: set[str] = set()
    out: dict[str, list[str]] = {s: [] for s in DIMENSION_TO_SECTION}

    for section in SECTION_PICK_ORDER:
        dims = DIMENSION_TO_SECTION[section]
        is_synthesis = section == "positionierung"

        if is_synthesis:
            # Positionierung = echte Synthese: Top-1 pro Dimension (WK + ED + SH)
            # → Schnittmenge aus Substanz, Mindset und Wirkung — kein Klon einer
            # anderen Sektion.
            chosen: list[str] = []
            seen_local: set[str] = set()
            for d in dims:
                for s in extracted.get(d, []):
                    if s in seen_local:
                        continue
                    seen_local.add(s)
                    chosen.append(s)
                    break  # nur die Top-1 dieser Dimension nehmen
                if len(chosen) >= max_per_section:
                    break
            out[section] = chosen[:max_per_section]
            continue

        candidates: list[str] = []
        seen_local = set()
        for d in dims:
            for s in extracted.get(d, []):
                if s in seen_local or s in used:
                    continue
                seen_local.add(s)
                candidates.append(s)
        chosen = candidates[:max_per_section]
        out[section] = chosen
        used.update(chosen)

    return out
