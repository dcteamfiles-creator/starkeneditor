# Stärkenkompass · SX Content App (Bulk-Queue Edition)

Web-App zur Vorbereitung von **Stärken-Exposés** für die Massenproduktion via **Canva Bulk Create**.

**Architektur**: Die App ist der Daten-Builder, Canva ist der pixel-perfekte Renderer.

---

## Workflow

```
content.staerkenkompass.de        Canva Pro
┌────────────────────┐            ┌──────────────────────┐
│ 1. Editor          │            │ 4. Bulk Create       │
│    SX-Daten        │   CSV +    │    CSV hochladen,    │
│    eingeben        │   Bild-    │    Variablen verbin- │
│ 2. In Bulk-Queue   │   URLs     │    den, generieren   │
│    legen           │ ─────────► │                      │
│ 3. CSV-Export      │            │ 5. PDFs downloaden   │
└────────────────────┘            └──────────────────────┘
```

---

## Setup (lokal)

```bash
cd sx-content-app
python3 server_stdlib.py
# → http://localhost:8000
```

Logins: `Content1/ToHa01` … `Content9/ToHa09`

Stdlib-only — keine Pip-Installation nötig.

---

## Was die App kann

| Feature | Status |
|---|---|
| 9 Login-Accounts | ✅ |
| Editor mit 11 Variablen + Live-HTML-Vorschau | ✅ |
| Längen-Validation pro Sektion (Live-Counter) | ✅ |
| QR-Pool: claim-PRN holt nächste freie Prüfnummer | ✅ |
| Sponsor-Pool: einmal hochladen, wiederverwenden | ✅ |
| Schirmherren-Defaults (Gerhardt/Bogs/Schacht) | ✅ |
| Bild-Uploads (Sponsor, Signaturen, Logos) | ✅ |
| Bulk-Queue: SX sammeln vor Export | ✅ |
| CSV-Export mit allen Variablen + öffentlichen Bild-URLs | ✅ |
| Audit-Log: alle exportierten SX | ✅ |
| Verifizierungs-Seite `/verify.html?id=…` | ✅ |

---

## Schritt-für-Schritt-Anleitung

### A) SX vorbereiten (jeder Content-Mitarbeiter)

1. Login auf `content.staerkenkompass.de`
2. Editor → "Nächste freie PRN holen" (System reserviert eine Prüfnummer im Google-Sheet-Pool)
3. Person-Name, Header, 7 Sektions-Texte ausfüllen (Live-Counter zeigt Limits)
4. Sponsor wählen: aus Pool oder neu hochladen
5. Schirmherren stehen auf Defaults — pro SX austauschbar
6. Klick **"In Bulk-Queue legen"**
7. Wiederhole für alle Personen (1, 10, 100 …)

### B) CSV exportieren (1× pro Bulk-Lauf)

1. Klick **"Bulk-Queue"** in der Navigation
2. Übersicht aller wartenden SX wird angezeigt
3. Klick **"CSV für Canva exportieren"** → CSV downloaded mit allen Spalten + Bild-URLs
4. Status wird automatisch auf "exportiert" gesetzt
5. Audit-Log erhält Eintrag pro exportiertem SX

### C) In Canva rendern (einmaliges Setup pro SX-Design)

1. **Canva Pro Account** abschließen (~€110/Jahr)
2. Dein bestehendes SX-Design öffnen
3. **Setup pro Design** (einmal):
   - Pro Variablen-Text rechtsklick → "Connect Data" → CSV-Spaltenname eintragen
   - Pro Bild-Frame (Sponsor, Signaturen, Logos) → "Bulk Image" Frame → CSV-Spalte zuweisen
   - QR-Code: Variable `qr_url` mit Canva's QR-Code-App verbinden (oder CSV-Spalte mit URL)
4. **Bulk Create starten**:
   - Apps → Bulk Create → CSV hochladen → "Continue"
   - "Generate Designs" → ein Design pro Zeile
5. **Download**:
   - Download → PDF Print → ZIP wird heruntergeladen
6. PDFs nutzen oder weiter verteilen

---

## CSV-Schema (für Canva-Connect-Mapping)

Die exportierte CSV enthält folgende Spalten — exakt diese Namen müssen im Canva-Design via "Connect Data" gemappt werden:

```
person_name                  → Header-Text "Vorname Nachname"
header                       → "Firstname - Affirmation Header"
pruefnummer                  → "#EU-DE-2026-XXXX-XX" (2x im Design verlinken)
feedback_count               → "3" (Zahl in Beschreibungstext)
date                         → "26.04.2026"

body_positionierung          → 7 Sektions-Body-Texte
body_alleinstellung
body_fuehrungsstil
body_einsatzgebiete
body_belastbarkeit
body_zukunftskompetenz
body_unternehmenskultur

qr_url                       → URL die in QR-Code codiert werden soll
sponsor_image_url            → URL zum Sponsor-Logo (oder leer)
sponsor_name                 → "Die Techniker"

schirmherr_1_signature_url   → URL zur Signatur (Gerhardt)
schirmherr_1_name            → "Prof. Dr. Claudia Gerhardt"
schirmherr_1_title           → "Leiterin Psychology School / Studiendekanin Wirtschaftspsychologie"
schirmherr_1_logo_url        → URL zum Logo (Fresenius)
schirmherr_2_signature_url   → (Bogs)
schirmherr_2_name
schirmherr_2_title
schirmherr_2_logo_url
schirmherr_3_signature_url   → (Schacht)
schirmherr_3_name
schirmherr_3_title
schirmherr_3_logo_url
```

---

## Wichtig: Bild-URLs müssen öffentlich erreichbar sein

Canva lädt die Bilder direkt von der URL. Wenn die App lokal läuft, sind die URLs `http://localhost:8000/...` — das funktioniert NICHT für Canva.

Setze daher `SX_PUBLIC_URL` als Env-Variable beim Deployment:

```bash
SX_PUBLIC_URL=https://content.staerkenkompass.de python3 server_stdlib.py
```

Bei Render.com / Netlify Functions wird das im Dashboard gesetzt.

---

## Deployment

### Render.com (empfohlen)

1. Repo auf GitHub pushen
2. Render Dashboard → "New +" → "Blueprint" (`render.yaml` ist dabei)
3. Custom Domain `content.staerkenkompass.de` einrichten
4. Env-Variable `SX_PUBLIC_URL=https://content.staerkenkompass.de` setzen

### Manuelles Deployment

`server_stdlib.py` läuft mit Python 3.10+ ohne Dependencies. Hosting-Optionen:
- Render.com Web Service
- Railway
- Fly.io
- Eigene VM mit systemd-Service

---

## Spätere Vollautomatisierung (Top-40-Pipeline)

Wenn die Top-40-Stärken-Pipeline JSON liefert:

1. Top-40-Service ruft `POST /api/bulk-queue` mit JSON-Payload pro Person
2. Cron-Job (z. B. nightly) ruft `GET /api/export-csv` und triggert via Canva Connect API einen Bulk-Create-Run
3. Canva produziert PDFs → Webhook → Drive/E-Mail
4. Audit-Log automatisch aktualisiert

→ Die App ist bereits darauf vorbereitet (gleiches Schema, gleiche Endpoints).

---

## Architektur

```
sx-content-app/
├── server_stdlib.py         # Stdlib-only HTTP server (production-ready)
├── server.py                # Flask alternative (optional, für Render etc.)
├── public/
│   ├── login.html           # Login-Seite
│   ├── editor.html          # SX-Editor mit Live-HTML-Preview
│   ├── bulk-queue.html      # Queue-Übersicht + CSV-Export
│   ├── overview.html        # Audit-Log
│   ├── verify.html          # PRN-Verifizierung (öffentlich)
│   ├── css/app.css
│   ├── js/editor.js
│   └── assets/
│       ├── defaults/        # Schirmherren-Signaturen + Logos
│       ├── fonts/           # Montserrat + OpenSans (für HTML-Preview)
│       └── sx-template.pdf  # InDesign-Template (Referenz)
├── data/                    # Runtime: Queue, Records, QR-Pool, Sponsors
├── README.md                # Diese Datei
└── BRIEFING_RESET.md        # Doku zur Strategie-Entscheidung
```

---

## Was NICHT mehr drin ist

- **PDF-Renderer in Python** (`lib/pdf_renderer.py`) — durch Canva Bulk Create ersetzt. Stub bleibt für Backwards-Compat.
- **Live-PDF-Preview** — durch HTML-Mockup ersetzt (Editor zeigt SX-Layout als HTML, gut genug zur Validierung)

---

## Lizenz / Verantwortung

Stärkenkompass intern. Keine Garantien. Bei Problemen mit Canva-Setup: Canva Support oder Bulk Create Doku konsultieren.

---

*Letzte Aktualisierung: 2026-04-26 nach Migration zu Canva Bulk Create.*
