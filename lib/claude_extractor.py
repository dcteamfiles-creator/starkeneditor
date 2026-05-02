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


def _build_data_block(section_strengths: dict, vorname: str, nachname: str) -> str:
    """Datenteil des Prompts — wird KONKATENIERT, nicht als Format-String genutzt."""
    lines = []
    for key, (de, en) in SECTION_LABELS.items():
        strengths = section_strengths.get(key, [])
        limit = SECTION_LIMITS[key]
        lines.append(
            f"- {de} // {en} (max {limit} Zeichen):\n  Fokus-Stärken: {', '.join(strengths) or '(keine ausgewählt — frei generieren)'}"
        )
    block = "\n".join(lines)

    # Output-Format-Spezifikation (separat, NICHT vom User-Prompt-Format-String betroffen)
    output_spec = '''
Antworte NUR mit gültigem JSON in genau diesem Format (keine Markdown-Codeblöcke):

{"positionierung": "<text>", "alleinstellung": "<text>", "fuehrungsstil": "<text>", "einsatzgebiete": "<text>", "belastbarkeit": "<text>", "zukunftskompetenz": "<text>", "unternehmenskultur": "<text>"}'''

    return (
        f"Person: {vorname} {nachname}\n\n"
        f"Sektionen mit fokussierten Stärken pro Sektion:\n{block}\n\n"
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
DIMENSION_TO_SECTION = {
    "positionierung":     ["WK", "ED", "SH"],   # alle Dimensionen — Positionierung ist Synthese
    "alleinstellung":     ["AE", "WK"],
    "fuehrungsstil":      ["SH"],
    "einsatzgebiete":     ["WK"],
    "belastbarkeit":      ["ED"],
    "zukunftskompetenz":  ["SH", "ED"],
    "unternehmenskultur": ["ED", "AE"],
}


def smart_default_mapping(extracted: dict, max_per_section: int = 4) -> dict[str, list[str]]:
    out = {}
    for section, dims in DIMENSION_TO_SECTION.items():
        candidates = []
        for d in dims:
            candidates.extend(extracted.get(d, []))
        # Deduplicate while preserving order
        seen = set()
        uniq = [s for s in candidates if not (s in seen or seen.add(s))]
        out[section] = uniq[:max_per_section]
    return out
