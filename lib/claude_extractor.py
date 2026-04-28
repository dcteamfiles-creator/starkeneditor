"""
Claude Vision + Text Generation für SX Editor.

Stdlib-only HTTP (urllib) — kein 'anthropic' SDK nötig.

Funktionen:
  extract_from_image(image_bytes, mime_type) -> dict
      Vision-Extraktion: erkennt Vorname, Nachname und Top 40 Stärken
      gegliedert in 4 Dimensionen (AE, ED, SH, WK).

  generate_section_texts(strengths_per_section, person_first_name, custom_prompt=None) -> dict
      7 Text-Bausteine basierend auf den ausgewählten Stärken pro Sektion.

  generate_header_alternatives(strengths_per_section, vorname, custom_prompt=None) -> list[dict]
      3 Header-Varianten (descriptiv / attribut-fokussiert / metaphorisch).
"""
from __future__ import annotations

import base64
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
MODEL = "claude-sonnet-4-5-20250929"   # Vision-fähig + sehr gut im Schreiben


def _api_call(payload: dict, timeout: int = 60) -> dict:
    """Sendet ein Anthropic-API-Request via urllib."""
    if not API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY nicht gesetzt (.env prüfen)")
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
    """Holt den Text aus dem ersten content-Block."""
    blocks = resp.get("content", [])
    for b in blocks:
        if b.get("type") == "text":
            return b.get("text", "")
    return ""


def _extract_json_from_text(text: str) -> dict | list:
    """Robustes JSON-Parsing aus LLM-Output (entfernt ```json … ```)."""
    text = text.strip()
    if text.startswith("```"):
        # entferne ```json ... ```
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)


# ─── 1. VISION: Stärken aus Auswertung extrahieren ─────────────────────────
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

Antworte NUR mit gültigem JSON in genau diesem Format:

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
    """Extrahiere Vorname/Nachname + 4-Dimensionen-Stärken aus Auswertungs-Bild.

    Returns dict: {vorname, nachname, AE: [...], ED: [...], SH: [...], WK: [...]}
    """
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
    text = _extract_text_from_response(resp)
    data = _extract_json_from_text(text)
    # Normalisierung
    return {
        "vorname": data.get("vorname", "").strip(),
        "nachname": data.get("nachname", "").strip(),
        "AE": list(data.get("AE", [])),
        "ED": list(data.get("ED", [])),
        "SH": list(data.get("SH", [])),
        "WK": list(data.get("WK", [])),
    }


# ─── 2. TEXT GENERATION: 7 Sektions-Texte ──────────────────────────────────
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
    "positionierung":     320,
    "alleinstellung":     320,
    "fuehrungsstil":      280,
    "einsatzgebiete":     320,
    "belastbarkeit":      280,
    "zukunftskompetenz":  360,
    "unternehmenskultur": 280,
}

DEFAULT_SX_PROMPT = """\
Schreibe für ein Stärken-Exposé (SX) den Text für die folgenden 7 Sektionen.
Jeder Text soll professionell, prägnant und in der dritten Person über die Person geschrieben sein.
Tonalität: wertschätzend, sachlich, mit konkretem Bezug auf die genannten Stärken.
Maximal so viele Zeichen wie angegeben (NICHT überschreiten — kürze lieber).

Vorname der Person: {vorname}
Nachname: {nachname}

Sektionen mit den fokussierten Stärken pro Sektion:
{section_strengths_block}

Antworte NUR mit gültigem JSON:

{{
  "positionierung":     "<Text>",
  "alleinstellung":     "<Text>",
  "fuehrungsstil":      "<Text>",
  "einsatzgebiete":     "<Text>",
  "belastbarkeit":      "<Text>",
  "zukunftskompetenz":  "<Text>",
  "unternehmenskultur": "<Text>"
}}

Keine Markdown-Codeblöcke, nur das JSON."""


def generate_section_texts(
    section_strengths: dict[str, list[str]],
    vorname: str = "",
    nachname: str = "",
    custom_prompt: str | None = None,
) -> dict[str, str]:
    """Generiere 7 Sektions-Texte basierend auf gewählten Stärken pro Sektion.

    section_strengths: {"positionierung": ["argumentationsstark", "strategisch"], ...}
    """
    block_lines = []
    for key, (de, en) in SECTION_LABELS.items():
        strengths = section_strengths.get(key, [])
        limit = SECTION_LIMITS[key]
        block_lines.append(
            f"  - {de} // {en} (max {limit} Zeichen):\n    Fokus-Stärken: {', '.join(strengths) or '(keine ausgewählt)'}"
        )
    section_block = "\n".join(block_lines)

    template = custom_prompt or DEFAULT_SX_PROMPT
    prompt = template.format(
        vorname=vorname or "(unbekannt)",
        nachname=nachname or "",
        section_strengths_block=section_block,
    )

    payload = {
        "model": MODEL,
        "max_tokens": 2048,
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = _api_call(payload, timeout=120)
    text = _extract_text_from_response(resp)
    data = _extract_json_from_text(text)
    # Truncate to limits if Claude overshoots
    out = {}
    for key in SECTION_LABELS:
        v = (data.get(key) or "").strip()
        out[key] = v[:SECTION_LIMITS[key]]
    return out


# ─── 3. HEADER ALTERNATIVES ─────────────────────────────────────────────────
HEADER_PROMPT = """\
Schreibe 3 Vorschläge für den "Affirmation-Header" eines Stärken-Exposés (SX).
Format jedes Vorschlags: "Vorname — kurze, prägnante Beschreibung mit 2-4 Wörtern".
Max 70 Zeichen pro Header.

Vorname: {vorname}
Top-Stärken (alle Dimensionen kombiniert): {top_strengths}

Generiere 3 unterschiedliche Stilrichtungen:
1. STIL "descriptiv": "Vorname — der/die <Rolle/Funktion>" (z.B. "der inspirierende Strategie-Macher")
2. STIL "attribut": "Vorname — <Adjektiv> & <Adjektiv>" (z.B. "argumentationsstark & charismatisch")
3. STIL "metaphorisch": "Vorname — <Bildhafte Metapher>" (z.B. "Brücke zwischen Idee und Markt")

Antworte NUR mit gültigem JSON:

[
  {{"style": "descriptiv",   "text": "..."}},
  {{"style": "attribut",     "text": "..."}},
  {{"style": "metaphorisch", "text": "..."}}
]

Keine Markdown-Codeblöcke."""


def generate_header_alternatives(
    section_strengths: dict[str, list[str]],
    vorname: str,
) -> list[dict]:
    # Collect top strengths across all sections (deduplicated, max 12)
    all_strengths = []
    seen = set()
    for sk in SECTION_LABELS:
        for s in section_strengths.get(sk, []):
            if s not in seen:
                seen.add(s)
                all_strengths.append(s)
            if len(all_strengths) >= 12:
                break
        if len(all_strengths) >= 12:
            break

    prompt = HEADER_PROMPT.format(
        vorname=vorname or "Person",
        top_strengths=", ".join(all_strengths) if all_strengths else "(keine)",
    )
    payload = {
        "model": MODEL,
        "max_tokens": 512,
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = _api_call(payload, timeout=60)
    text = _extract_text_from_response(resp)
    data = _extract_json_from_text(text)
    if not isinstance(data, list):
        return []
    return [{"style": d.get("style", "?"), "text": d.get("text", "").strip()[:80]} for d in data[:3]]


# ─── 4. SMART DEFAULT MAPPING (Dimension → Sektion) ─────────────────────────
# Konzept: jede der 7 SX-Sektionen bekommt initial Stärken aus passenden Dimensionen.

DIMENSION_TO_SECTION = {
    "positionierung":     ["WK"],            # Wissen + Können = Kern-Wertversprechen
    "alleinstellung":     ["AE", "WK"],      # Auftreten + Wissen = Differenzierung
    "fuehrungsstil":      ["SH"],            # Sprechen + Handeln
    "einsatzgebiete":     ["WK"],            # Wo wirkt diese Person
    "belastbarkeit":      ["ED"],            # Einstellung + Denken
    "zukunftskompetenz":  ["SH", "ED"],      # Zwischenmenschlich + reflexiv
    "unternehmenskultur": ["ED"],            # Werte + Denkmuster
}


def smart_default_mapping(
    extracted: dict,
    max_per_section: int = 5,
) -> dict[str, list[str]]:
    """Verteile die Top 40 Stärken vorausgewählt auf 7 Sektionen."""
    out = {}
    for section, dims in DIMENSION_TO_SECTION.items():
        candidates = []
        for d in dims:
            candidates.extend(extracted.get(d, []))
        out[section] = candidates[:max_per_section]
    return out
